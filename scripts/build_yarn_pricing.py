"""
build_yarn_pricing.py — Phase C: Yarn Pricing Waterfall Engine

Computes daily yarn-level price pressure indices for tracked yarn specs in
dim_yarn_master, using a 4-tier waterfall:

  Tier 0 - Internal Rayon procurement records (yarn_costs table)
  Tier 1 - Turkish supplier quotes (fact_supplier_quotes)
  Tier 2 - Global b2b platform reference prices
  Tier 3 - International wholesale references
  Tier 4 - SunSirs/ICE upstream commodity benchmark + spinning_markup model

Each yarn_id is priced via the highest-tier evidence available, with fallback
chain. Result written to fact_yarn_price_pressure (one row per yarn_id per
calc_date).

Architecture per Phase C design (May 2026):
  * spinning_markups.json (config, version-controlled) — config-driven markups.
  * dim_material.upstream_benchmark_slug — primary anchor mapping (DB).
  * Multi-fiber blend logic computed here in code, NOT in DB columns.
  * Two trigger modes: scheduled daily (08:00 UTC via GitHub Actions),
    on-demand via /admin/recompute_pricing FastAPI endpoint.

Usage:
    python scripts/build_yarn_pricing.py                    # daily scheduled
    python scripts/build_yarn_pricing.py --backfill 30      # last 30 days
    python scripts/build_yarn_pricing.py --yarn-id 7        # single yarn
    python scripts/build_yarn_pricing.py --dry-run          # no DB write

Module structure:
    1. Config loader               (load_markup_config)
    2. Data loaders                (load_active_yarns, load_*_evidence)
    3. Tier-specific pricers       (price_via_tier_0..4)
    4. Waterfall orchestrator      (compute_yarn_price)
    5. Blend / proxy adjusters     (compute_weighted_blend, apply_proxy_premium)
    6. Pressure / signal           (compute_pressure_7d, classify_signal)
    7. Persister                   (write_to_fact_table)
    8. Main driver                 (main, daily_run)
"""

from __future__ import annotations
import os
import json
import logging
import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, Literal, Any
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# ---------------------------------------------------------------------------
# Constants and config paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
MARKUP_CONFIG_PATH = PROJECT_ROOT / "config" / "spinning_markups.json"

# Confidence calibration (per architectural review)
TIER_CONFIDENCE = {
    "tier_0_internal":         "high",    # 1.0 — direct procurement
    "tier_1_turkish_quote":    "high",    # 0.85
    "tier_2_global":           "medium",  # 0.65
    "tier_3_b2b":              "medium",  # 0.55
    "tier_4_benchmark_proxy":  "low",     # 0.45
}

# Pressure signal thresholds (7-day % change)
PRESSURE_THRESHOLDS = {
    "rising":  3.0,    # >+3% over 7 days
    "falling": -3.0,   # <-3% over 7 days
    # otherwise "stable"
}

# Fiber → upstream commodity benchmark (used for blend secondary fibers).
# This is the IN-CODE map for resolving non-anchor fibers in blends.
# Anchor fibers are looked up via dim_material.upstream_benchmark_slug.
FIBER_TO_BENCHMARK_SLUG = {
    "PES":      "polyester_yarn",
    "VIS":      "rayon_yarn",
    "MOD":      "rayon_yarn",         # proxy: modal ≈ viscose
    "COT":      "cotton_yarn",
    "PA":       "polyamide_fdy",
    "PA66":     "polyamide_fdy",
    "PA6":      "polyamide_fdy",
    "ELASTANE": None,                  # priced as flat premium, not commodity
    "RCY_PES":  "polyester_yarn",     # base + recycled premium
    "RCY_COT":  "cotton_yarn",        # base + recycled premium
}

# Elastane flat premium per kg (corespun integration)
ELASTANE_PREMIUM_USD_PER_KG = 0.40


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class YarnSpec:
    """Active tracked yarn from dim_yarn_master."""
    yarn_id: int
    yarn_code: str
    fiber_family: str
    denier: Optional[int]
    filament_count: Optional[int]
    blend_ratio_json: Optional[dict]
    primary_driver_slug: str             # e.g., "polyester_staple"
    upstream_benchmark_slug: Optional[str]  # e.g., "polyester_yarn"
    pricing_basis: Optional[str]
    spec_confidence: str
    # spinning system + ply derived in code from yarn_code or evidence sheet


@dataclass
class PricingResult:
    yarn_id: int
    calc_date: date
    driver_price_usd: Decimal
    estimated_index: Decimal
    pricing_method: str   # 'tier_0_internal' / 'tier_4_benchmark_proxy' / etc.
    confidence: str       # 'high' / 'medium' / 'low'
    pressure_7d: Optional[Decimal] = None
    pressure_signal: Optional[str] = None
    debug_notes: list[str] = None


# ---------------------------------------------------------------------------
# 1. Config loader
# ---------------------------------------------------------------------------

def load_markup_config() -> dict[str, Any]:
    """Load spinning_markups.json. Fail-loud if missing or malformed."""
    # TODO: implement
    pass


# ---------------------------------------------------------------------------
# 2. Data loaders
# ---------------------------------------------------------------------------

def load_active_yarns(conn) -> list[YarnSpec]:
    """
    Pull all active yarns from dim_yarn_master, joined with dim_material
    for upstream_benchmark_slug lookup.

    SELECT
        ym.yarn_id, ym.yarn_code, ym.fiber_family, ym.denier,
        ym.filament_count, ym.blend_ratio_json, ym.pricing_basis,
        ym.spec_confidence,
        -- primary_driver_slug from sheet sync (TBD: source pending)
        ...
    FROM dim_yarn_master ym
    LEFT JOIN dim_material dm ON dm.slug = <primary_driver_slug>
    WHERE ym.is_active_tracked = TRUE;
    """
    # TODO: implement after deciding how primary_driver_slug propagates from
    # evidence sheet -> dim_yarn_master (Phase C+1 sheet sync, or manual seed)
    pass


def load_tier_0_evidence(conn, yarn_id: int, on_date: date):
    """Internal Rayon procurement (yarn_costs table)."""
    # TODO: query yarn_costs WHERE material_key matches yarn_id
    # Return latest landed cost USD/kg and date
    pass


def load_tier_1_evidence(conn, yarn_id: int, on_date: date):
    """Turkish supplier quotes (fact_supplier_quotes table)."""
    # TODO: filter to Turkish suppliers, recent quote
    pass


def load_tier_4_benchmark(conn, benchmark_slug: str, on_date: date):
    """
    Latest SunSirs/ICE benchmark price for an upstream commodity.

    Joins price_metrics_daily or similar to retrieve latest USD/kg
    benchmark (RMB/ton converted).
    """
    # TODO: query price_metrics_daily for slug=benchmark_slug, latest row
    pass


# ---------------------------------------------------------------------------
# 3. Tier-specific pricers
# ---------------------------------------------------------------------------

def price_via_tier_0(conn, yarn: YarnSpec, on_date: date) -> Optional[PricingResult]:
    """Direct internal procurement record. Highest confidence."""
    # TODO
    pass


def price_via_tier_1(conn, yarn: YarnSpec, on_date: date) -> Optional[PricingResult]:
    """Turkish supplier quote (recent, single fiber). High confidence."""
    # TODO
    pass


def price_via_tier_4(conn, yarn: YarnSpec, on_date: date,
                     markup_config: dict) -> PricingResult:
    """
    Benchmark + spinning markup proxy pricing. ALWAYS RETURNS a result
    (last-resort fallback). Confidence: low.

    Steps:
      1. Resolve primary upstream benchmark price (from dim_material.upstream_benchmark_slug).
      2. If yarn is a blend (blend_ratio_json populated), compute weighted-avg
         primary + secondary fiber prices via FIBER_TO_BENCHMARK_SLUG.
      3. Apply proxy premiums (modal_over_rayon, recycled premiums).
      4. Apply spinning markup from config (family_base_markup * adjustments).
      5. Add elastane premium if corespun.
      6. Return PricingResult.
    """
    # TODO: implement skeleton below
    notes = []
    benchmark_price = load_tier_4_benchmark(
        conn, yarn.upstream_benchmark_slug, on_date
    )
    # ...
    pass


# ---------------------------------------------------------------------------
# 4. Waterfall orchestrator
# ---------------------------------------------------------------------------

def compute_yarn_price(conn, yarn: YarnSpec, on_date: date,
                       markup_config: dict) -> PricingResult:
    """Run waterfall: try Tier 0 -> 1 -> 2 -> 3 -> 4. First hit wins."""
    for pricer in (price_via_tier_0, price_via_tier_1):
        result = pricer(conn, yarn, on_date)
        if result is not None:
            return result
    # Fallback always succeeds (Tier 4 is the catch-all)
    return price_via_tier_4(conn, yarn, on_date, markup_config)


# ---------------------------------------------------------------------------
# 5. Blend / proxy adjusters (called from price_via_tier_4)
# ---------------------------------------------------------------------------

def compute_weighted_blend(conn, blend_ratio: dict[str, float],
                            on_date: date) -> Decimal:
    """
    Weighted-average upstream commodity price for a multi-fiber blend.

    Args:
        blend_ratio: e.g., {"PES": 65, "VIS": 35} or
                     {"PES": 63, "VIS": 34, "ELASTANE": 3}
        on_date:     pricing date

    Algorithm:
        For each fiber in blend_ratio:
            pct = ratio / 100
            if fiber == 'ELASTANE':
                contribution = pct * ELASTANE_PREMIUM_USD_PER_KG
            else:
                benchmark_slug = FIBER_TO_BENCHMARK_SLUG[fiber]
                benchmark_price = load_tier_4_benchmark(...)
                contribution = pct * benchmark_price
            apply proxy premiums (modal, recycled) per fiber type
        return sum(contributions)
    """
    # TODO
    pass


def apply_proxy_premium(fiber: str, base_price: Decimal,
                          premium_config: dict) -> Decimal:
    """E.g., MOD -> add modal_over_rayon premium, RCY_PES -> add recycled premium."""
    # TODO
    pass


def apply_spinning_markup(yarn: YarnSpec, family_key: str,
                           markup_config: dict) -> Decimal:
    """
    Look up family_base_markup[family_key][spinning_system_base] and
    apply spec_adjustments (ply, compact, combed, color, specialty)
    plus count_band_modifier. Compounded.
    """
    # TODO
    pass


# ---------------------------------------------------------------------------
# 6. Pressure / signal
# ---------------------------------------------------------------------------

def compute_pressure_7d(conn, yarn_id: int, current_index: Decimal,
                         on_date: date) -> Optional[Decimal]:
    """
    Look up estimated_index from fact_yarn_price_pressure for date - 7,
    return % change. NULL if no historical data (cold-start).
    """
    # TODO
    pass


def classify_signal(pressure_7d: Optional[Decimal]) -> str:
    """Map pressure % to enum: rising / stable / falling / no_data."""
    if pressure_7d is None:
        return "no_data"
    if float(pressure_7d) > PRESSURE_THRESHOLDS["rising"]:
        return "rising"
    if float(pressure_7d) < PRESSURE_THRESHOLDS["falling"]:
        return "falling"
    return "stable"


# ---------------------------------------------------------------------------
# 7. Persister
# ---------------------------------------------------------------------------

def write_to_fact_table(conn, results: list[PricingResult], dry_run: bool):
    """
    Bulk INSERT into fact_yarn_price_pressure.

    Idempotency:
      Append-only by design. (calc_date, yarn_id) is logically unique;
      duplicate runs for same date should be DELETE+INSERT or UPSERT.
      Default behavior: DELETE existing rows for (calc_date, yarn_id IN ...)
      then bulk INSERT. Wrap in transaction.
    """
    if dry_run:
        # TODO: log results, no DB write
        return
    # TODO: implement
    pass


# ---------------------------------------------------------------------------
# 8. Main driver
# ---------------------------------------------------------------------------

def daily_run(conn, on_date: date, dry_run: bool = False,
              yarn_id_filter: Optional[int] = None) -> list[PricingResult]:
    """Run pricing waterfall for all active yarns on given date."""
    markup_config = load_markup_config()
    yarns = load_active_yarns(conn)
    if yarn_id_filter:
        yarns = [y for y in yarns if y.yarn_id == yarn_id_filter]

    results = []
    for yarn in yarns:
        result = compute_yarn_price(conn, yarn, on_date, markup_config)
        result.pressure_7d = compute_pressure_7d(
            conn, yarn.yarn_id, result.estimated_index, on_date
        )
        result.pressure_signal = classify_signal(result.pressure_7d)
        results.append(result)

    write_to_fact_table(conn, results, dry_run=dry_run)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", type=int, default=0,
                        help="Number of past days to backfill (default: 0 = today only)")
    parser.add_argument("--yarn-id", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        if args.backfill > 0:
            # TODO: loop over past N days
            pass
        else:
            results = daily_run(conn, date.today(), args.dry_run, args.yarn_id)
            logging.info(f"Computed {len(results)} yarn prices for {date.today()}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
