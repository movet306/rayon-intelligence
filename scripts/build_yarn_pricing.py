"""
build_yarn_pricing.py — Phase C: Yarn Pricing Waterfall Engine

Computes daily yarn-level price index for tracked yarns in dim_yarn_master,
using a 4-tier waterfall (Tier 0/1 implementations deferred; Tier 4 active):

  Tier 0  - Internal Rayon procurement (yarn_costs)            [STUB]
  Tier 1  - Turkish supplier quotes (fact_supplier_quotes)     [STUB]
  Tier 4  - Upstream commodity benchmark + spinning markup     [ACTIVE]

Each tracked yarn is priced via the highest-tier evidence available, falling
back to Tier 4 (always succeeds). Result row written to fact_yarn_price_pressure
per (calc_date, yarn_id).

Architecture (per Phase C design, May 2026):
  * scripts/pricing/driver_inference.py       — YarnSpec -> driver_slug rules
  * config/spinning_markups.json              — version-controlled markup config
  * dim_material.upstream_benchmark_slug      — granular driver -> commodity
  * Multi-fiber blend logic computed in code, NOT in DB.
  * Proxy fallback flag: pricing_method = "tier_4_proxy_fallback" for the
    10 of 12 drivers without authoritative benchmarks (modal, polyester_staple,
    polyamide_staple, all blends, recycled).

Usage:
    python scripts/build_yarn_pricing.py                 # daily run for today
    python scripts/build_yarn_pricing.py --backfill 30   # last 30 days
    python scripts/build_yarn_pricing.py --yarn-id 7     # single yarn
    python scripts/build_yarn_pricing.py --dry-run       # log only, no DB write
"""

from __future__ import annotations
import os
import sys
import json
import logging
import argparse
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Optional, Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

# Ensure pricing/ is on path when run as script
sys.path.insert(0, str(Path(__file__).parent))
from pricing.driver_inference import (
    YarnSpec as InferenceYarnSpec,
    InferenceResult,
    infer_driver_slug,
    write_audit_log,
)

# Decimal precision for monetary calculations
getcontext().prec = 12

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants and config paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "spinning_markups.json"
AUDIT_LOG_DIR = PROJECT_ROOT / "logs" / "pricing_inference"

# Confidence calibration (per architectural review).
TIER_CONFIDENCE_LABEL = {
    "tier_0_internal":          "high",
    "tier_1_turkish_quote":     "high",
    "tier_2_global":            "medium",
    "tier_3_b2b":               "medium",
    "tier_4_benchmark_proxy":   "low",
    "tier_4_proxy_fallback":    "low",
}

PRESSURE_THRESHOLDS = {"rising": 3.0, "falling": -3.0}

# Authoritative drivers (driver_slug ≈ semantic-equivalent of upstream).
# All others use tier_4_proxy_fallback even when benchmark data is available.
AUTHORITATIVE_DRIVERS = {
    # Existing commodity drivers (no Phase B5 entry)
    "polyester_fdy", "polyester_dty", "polyester_poy", "polyamide_fdy",
    "cotton_yarn", "cotton_lint", "rayon_yarn", "polyester_yarn",
    "pa6_chip", "pa66_chip", "pta", "adipic_acid",
    # Phase B5 yarn drivers with semantic match to upstream
    "viscose_staple",   # rayon_yarn = viscose, semantically aligned
    "cotton_staple",    # cotton_yarn aligned
}

# Fiber → upstream commodity slug (used for blend secondary fibers and recycled).
FIBER_TO_BENCHMARK_SLUG = {
    "PES":      "polyester_yarn",
    "VIS":      "rayon_yarn",
    "MOD":      "rayon_yarn",       # proxy: modal ≈ viscose + premium
    "COT":      "cotton_yarn",
    "PA":       "polyamide_fdy",
    "PA66":     "polyamide_fdy",
    "PA6":      "polyamide_fdy",
    "ELASTANE": None,                # priced as flat premium, not commodity
    "RCY_PES":  "polyester_yarn",   # virgin + recycled premium
    "RCY_COT":  "cotton_yarn",      # virgin + recycled premium
    "RCY_VIS":  "rayon_yarn",
}

ELASTANE_PREMIUM_USD_PER_KG = Decimal("0.40")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class YarnRow:
    """Yarn loaded from dim_yarn_master + dim_material join."""
    yarn_id: int
    yarn_code: str
    fiber_family: str
    denier: Optional[int]
    filament_count: Optional[int]
    blend_ratio_json: Optional[dict]
    is_recycled: bool
    spec_confidence: str
    driver_slug: Optional[str] = None         # filled by inference
    inference_reason: Optional[str] = None
    upstream_benchmark_slug: Optional[str] = None  # filled after inference
    is_authoritative: bool = False


@dataclass
class PricingResult:
    yarn_id: int
    yarn_code: str
    calc_date: date
    driver_price_usd: Optional[Decimal]
    estimated_index: Optional[Decimal]
    pressure_7d: Optional[Decimal]
    pressure_signal: str
    confidence: str
    pricing_method: str
    debug_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 1. Config loader
# ---------------------------------------------------------------------------

def load_markup_config() -> dict[str, Any]:
    """Load spinning_markups.json. Fail-loud if missing or malformed."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Markup config missing at {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # Quick structural check
    for required_key in ("family_base_markup", "spec_adjustments",
                         "fiber_premium_over_benchmark", "count_band_modifier"):
        if required_key not in cfg:
            raise ValueError(f"Markup config missing top-level key: {required_key}")
    logger.info(f"Loaded markup config v{cfg.get('_metadata', {}).get('version', '?')}")
    return cfg


# ---------------------------------------------------------------------------
# 2. Data loaders
# ---------------------------------------------------------------------------

def load_active_yarns(conn) -> list[YarnRow]:
    """
    Load all market-common yarns from dim_yarn_master.

    Filter: is_market_common = TRUE (broader than is_active_tracked, which
    is currently FALSE for all 21 specs by default per Migration 009).
    """
    query = """
        SELECT
            yarn_id,
            yarn_code,
            fiber_family,
            denier,
            filament_count,
            blend_ratio_json,
            recycle_flag        AS is_recycled,
            spec_confidence
        FROM dim_yarn_master
        WHERE is_market_common = TRUE
        ORDER BY yarn_id;
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        rows = cur.fetchall()
    yarns = [YarnRow(
        yarn_id=r["yarn_id"],
        yarn_code=r["yarn_code"],
        fiber_family=r["fiber_family"],
        denier=r["denier"],
        filament_count=r["filament_count"],
        blend_ratio_json=r["blend_ratio_json"],
        is_recycled=bool(r["is_recycled"]),
        spec_confidence=r["spec_confidence"] or "medium",
    ) for r in rows]
    logger.info(f"Loaded {len(yarns)} market-common yarns from dim_yarn_master")
    return yarns


# Slug-specific unit-conversion factors to convert price_metrics_daily.price_usd
# into USD/kg. SunSirs commodities ship as USD/ton (RMB/ton converted),
# IndexMundi cotton ships as USD/lb, etc. Verified against May 2026 reference
# prices. When adding a new slug, set its factor here explicitly.
PRICE_USD_TO_USD_PER_KG_FACTOR = {
    # SunSirs polymer/fiber/yarn commodities: USD/ton -> /1000
    "polyester_fdy":            Decimal("0.001"),
    "polyester_dty":            Decimal("0.001"),
    "polyester_poy":            Decimal("0.001"),
    "polyester_yarn":           Decimal("0.001"),
    "polyester_staple_fiber":   Decimal("0.001"),
    "polyamide_fdy":            Decimal("0.001"),
    "rayon_yarn":               Decimal("0.001"),
    "cotton_yarn":              Decimal("0.001"),
    "cotton_lint":              Decimal("0.001"),
    "pa6_chip":                 Decimal("0.001"),
    "pa66_chip":                Decimal("0.001"),
    "pta":                      Decimal("0.001"),
    "adipic_acid":              Decimal("0.001"),
    # ICE Cotton futures + IndexMundi monthly: USD/lb -> *2.2046 (lb to kg)
    # but price_usd may already be normalized differently — investigate per-source.
    # Setting explicit factor when wool/cotton-monthly drivers are activated.
    "cotton_lint_futures":      Decimal("2.2046"),  # USD/lb -> USD/kg
    "cotton":                   Decimal("2.2046"),  # IndexMundi monthly cotton USD/lb
    "coarse_wool":              Decimal("0.001"),  # USD/ton (assumed; flag if wrong)
    "fine_wool":                Decimal("0.001"),
}


def load_tier_4_benchmark(conn, slug: str, on_date: date) -> Optional[dict]:
    """
    Latest USD/kg benchmark from price_metrics_daily for a commodity slug.

    Returns dict with price_usd_per_kg (normalized from raw price_usd via
    PRICE_USD_TO_USD_PER_KG_FACTOR) and change_7d (% change from row, no unit).
    Returns None if no row or no factor configured.
    """
    query = """
        SELECT material, metric_date, price_usd, change_7d, confidence_tier
        FROM price_metrics_daily
        WHERE material = %s
          AND metric_date <= %s
          AND price_usd IS NOT NULL
        ORDER BY metric_date DESC
        LIMIT 1;
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (slug, on_date))
        row = cur.fetchone()
    if not row:
        logger.warning(f"No benchmark for slug={slug} on/before {on_date}")
        return None
    factor = PRICE_USD_TO_USD_PER_KG_FACTOR.get(slug)
    if factor is None:
        logger.warning(
            f"No unit-conversion factor configured for slug={slug}; "
            f"raw price_usd will be returned as-is. ADD AN ENTRY TO "
            f"PRICE_USD_TO_USD_PER_KG_FACTOR."
        )
        factor = Decimal("1")
    raw_price_usd = Decimal(str(row["price_usd"]))
    price_usd_per_kg = (raw_price_usd * factor).quantize(Decimal("0.0001"))
    return {
        "material": row["material"],
        "metric_date": row["metric_date"],
        "price_usd": price_usd_per_kg,         # NORMALIZED to USD/kg
        "raw_price_usd": raw_price_usd,         # original value, for debug
        "unit_factor": factor,
        "change_7d": Decimal(str(row["change_7d"])) if row["change_7d"] is not None else None,
        "confidence_tier": row["confidence_tier"],
    }


def load_upstream_for_driver(conn, driver_slug: str) -> Optional[str]:
    """Look up upstream_benchmark_slug from dim_material for a yarn driver."""
    query = """
        SELECT upstream_benchmark_slug
        FROM dim_material
        WHERE slug = %s;
    """
    with conn.cursor() as cur:
        cur.execute(query, (driver_slug,))
        row = cur.fetchone()
    if not row:
        logger.warning(f"Driver slug not in dim_material: {driver_slug}")
        return None
    # If upstream is NULL, the driver itself IS upstream (e.g., polyester_yarn)
    return row[0] or driver_slug


# ---------------------------------------------------------------------------
# 3. Tier-specific pricers
# ---------------------------------------------------------------------------

def price_via_tier_0(conn, yarn: YarnRow, on_date: date) -> Optional[PricingResult]:
    """STUB: Internal Rayon procurement record (yarn_costs table).
    To be implemented when material_key linkage to yarn_id is established."""
    return None


def price_via_tier_1(conn, yarn: YarnRow, on_date: date) -> Optional[PricingResult]:
    """STUB: Turkish supplier quote (fact_supplier_quotes table).
    To be implemented when supplier quote enrichment runs against yarn_id."""
    return None


def price_via_tier_4(conn, yarn: YarnRow, on_date: date,
                      markup_config: dict) -> PricingResult:
    """
    Benchmark + spinning markup proxy pricing. Always returns a result;
    last-resort fallback when no Tier 0/1 evidence exists.
    """
    notes: list[str] = []

    # Step 1: Resolve primary upstream commodity benchmark price (USD/kg)
    if yarn.is_blend if False else _is_blend(yarn):
        # Blend: weighted-average of fiber commodity prices
        primary_price, blend_notes = compute_weighted_blend(
            conn, yarn.blend_ratio_json or {}, on_date, markup_config
        )
        notes.extend(blend_notes)
    else:
        # Single fiber: direct upstream lookup
        primary_price = _price_single_fiber(conn, yarn, on_date, markup_config, notes)

    if primary_price is None:
        return PricingResult(
            yarn_id=yarn.yarn_id, yarn_code=yarn.yarn_code, calc_date=on_date,
            driver_price_usd=None, estimated_index=None,
            pressure_7d=None, pressure_signal="no_data",
            confidence="low", pricing_method="tier_4_no_benchmark",
            debug_notes=notes + ["No upstream benchmark resolved"],
        )

    # Step 2: Apply spinning markup from JSON config
    markup = apply_spinning_markup(yarn, markup_config, notes)
    final_price = primary_price + markup

    # Step 3: Determine confidence + pricing_method label
    if yarn.is_authoritative:
        pricing_method = "tier_4_benchmark_proxy"
    else:
        pricing_method = "tier_4_proxy_fallback"
        notes.append(f"proxy_fallback (driver={yarn.driver_slug}, "
                     f"upstream={yarn.upstream_benchmark_slug})")
    confidence = TIER_CONFIDENCE_LABEL[pricing_method]

    return PricingResult(
        yarn_id=yarn.yarn_id, yarn_code=yarn.yarn_code, calc_date=on_date,
        driver_price_usd=primary_price.quantize(Decimal("0.0001")),
        estimated_index=final_price.quantize(Decimal("0.0001")),
        pressure_7d=None,  # filled later via compute_pressure_7d
        pressure_signal="no_data",
        confidence=confidence, pricing_method=pricing_method,
        debug_notes=notes,
    )


# ---------------------------------------------------------------------------
# 4. Waterfall orchestrator
# ---------------------------------------------------------------------------

def compute_yarn_price(conn, yarn: YarnRow, on_date: date,
                        markup_config: dict) -> PricingResult:
    """Run waterfall: try Tier 0 -> 1 -> 4. First hit wins."""
    for pricer in (price_via_tier_0, price_via_tier_1):
        result = pricer(conn, yarn, on_date)
        if result is not None:
            return result
    return price_via_tier_4(conn, yarn, on_date, markup_config)


# ---------------------------------------------------------------------------
# 5. Blend / proxy adjusters
# ---------------------------------------------------------------------------

def _is_blend(yarn: YarnRow) -> bool:
    if yarn.fiber_family == "blend":
        return True
    if not yarn.blend_ratio_json:
        return False
    return len([k for k in yarn.blend_ratio_json.keys() if not k.startswith("_")]) > 1


def _price_single_fiber(conn, yarn: YarnRow, on_date: date,
                         markup_config: dict, notes: list[str]) -> Optional[Decimal]:
    """Single-fiber upstream lookup with proxy-fallback premium application."""
    if not yarn.upstream_benchmark_slug:
        notes.append(f"No upstream_benchmark_slug for driver={yarn.driver_slug}")
        return None

    bench = load_tier_4_benchmark(conn, yarn.upstream_benchmark_slug, on_date)
    if bench is None:
        return None
    notes.append(f"upstream={yarn.upstream_benchmark_slug} "
                 f"price=${bench['price_usd']:.4f}/kg @ {bench['metric_date']}")

    price = bench["price_usd"]

    # Apply fiber-level proxy premium when applicable
    premiums = markup_config["fiber_premium_over_benchmark"]
    if yarn.driver_slug == "modal_staple":
        premium = Decimal(str(premiums["modal_over_rayon"]))
        price += premium
        notes.append(f"+modal_premium={premium:.4f}")
    elif yarn.driver_slug == "recycled_polyester_staple":
        premium = Decimal(str(premiums["recycled_polyester_over_polyester"]))
        price += premium
        notes.append(f"+recycled_polyester_premium={premium:.4f}")

    return price


def compute_weighted_blend(conn, blend_ratio: dict, on_date: date,
                            markup_config: dict) -> tuple[Optional[Decimal], list[str]]:
    """
    Weighted-average upstream commodity price for a multi-fiber blend.

    For each non-metadata fiber key:
      pct = ratio / 100
      if fiber == 'ELASTANE':
          contribution = pct * ELASTANE_PREMIUM
      else:
          slug = FIBER_TO_BENCHMARK_SLUG[fiber]
          benchmark = load_tier_4_benchmark(slug)
          contribution = pct * benchmark.price_usd
          + proxy premium (modal, recycled) if applicable
    Returns sum of contributions, or None if any required benchmark is missing.
    """
    notes: list[str] = []
    fibers = {k: v for k, v in blend_ratio.items() if not k.startswith("_")}
    if not fibers:
        return None, ["empty blend_ratio"]

    # Normalize ratios (in case they don't sum to 100)
    total = sum(Decimal(str(v)) for v in fibers.values())
    if total == 0:
        return None, ["blend_ratio sums to 0"]

    premiums = markup_config["fiber_premium_over_benchmark"]
    weighted_sum = Decimal("0")

    for fiber, pct_raw in fibers.items():
        pct = Decimal(str(pct_raw)) / total

        if fiber == "ELASTANE":
            contrib = pct * ELASTANE_PREMIUM_USD_PER_KG
            notes.append(f"ELASTANE×{pct:.4f}×${ELASTANE_PREMIUM_USD_PER_KG}=${contrib:.4f}")
            weighted_sum += contrib
            continue

        slug = FIBER_TO_BENCHMARK_SLUG.get(fiber)
        if slug is None:
            notes.append(f"Unknown fiber in blend: {fiber}")
            return None, notes

        bench = load_tier_4_benchmark(conn, slug, on_date)
        if bench is None:
            notes.append(f"No benchmark for fiber={fiber} slug={slug}")
            return None, notes

        fiber_price = bench["price_usd"]
        # Proxy premiums for specific fibers
        if fiber == "MOD":
            fiber_price += Decimal(str(premiums["modal_over_rayon"]))
            notes.append(f"  +modal_premium for MOD")
        elif fiber == "RCY_PES":
            fiber_price += Decimal(str(premiums["recycled_polyester_over_polyester"]))
            notes.append(f"  +recycled_polyester_premium for RCY_PES")
        elif fiber == "RCY_COT":
            fiber_price += Decimal(str(premiums["recycled_cotton_over_cotton"]))
            notes.append(f"  +recycled_cotton_premium for RCY_COT")

        contrib = pct * fiber_price
        notes.append(f"{fiber}×{pct:.4f}×${fiber_price:.4f}=${contrib:.4f}")
        weighted_sum += contrib

    return weighted_sum, notes


def apply_spinning_markup(yarn: YarnRow, markup_config: dict,
                           notes: list[str]) -> Decimal:
    """
    Look up family base + apply spec adjustments (multiplicative compounding).

    Decision logic:
      1. Pick family bucket from family_base_markup using yarn.driver_slug
         OR fallback by fiber_family.
      2. Pick spinning_system base (ring/vortex/open_end) by parsing yarn_code.
      3. Compound spec_adjustments: ply, compact, combed, color, specialty.
      4. Apply count_band_modifier based on Ne or denier_class.
    """
    family_buckets = markup_config["family_base_markup"]
    adjustments = markup_config["spec_adjustments"]
    count_bands = markup_config["count_band_modifier"]

    # Step 1: family bucket
    bucket_key = yarn.driver_slug
    if bucket_key not in family_buckets:
        # Fallback by fiber_family
        bucket_key = f"{yarn.fiber_family}_staple"
    bucket = family_buckets.get(bucket_key)
    if bucket is None:
        notes.append(f"No markup bucket for driver={yarn.driver_slug}; using 0")
        return Decimal("0")

    # Step 2: spinning system base
    code = yarn.yarn_code or ""
    if "_VORTEX" in code:
        sys_key = "vortex_base"
    elif "_OE" in code or "_OPEN_END" in code:
        sys_key = "open_end_base"
    else:
        sys_key = "ring_base"  # Default for staple yarns

    # For filament-based driver buckets (FDY, DTY, POY, GIPE), use 'base' key
    if "base" in bucket and sys_key not in bucket:
        sys_key = "base"

    base_value = bucket.get(sys_key)
    if base_value is None or base_value == "null":
        notes.append(f"No {sys_key} markup for {bucket_key}; falling back to ring_base")
        base_value = bucket.get("ring_base") or bucket.get("base") or 0

    base = Decimal(str(base_value))
    multiplier = Decimal("1")
    notes.append(f"family_base[{bucket_key}.{sys_key}]={base:.4f}")

    # Step 3: spec adjustments — ply
    ply = _extract_ply(code)
    ply_mult = Decimal(str(adjustments["ply"].get(str(ply), 1.0)))
    if ply_mult != 1:
        multiplier *= ply_mult
        notes.append(f"×ply[{ply}]={ply_mult}")

    # Compact / combed: not in code today; default to false. Future: read from
    # specialty_flags column in evidence sheet sync.

    # Color
    color = "ECRU"
    if "_BLACK" in code:
        color = "BLACK"
    elif "DOPE_DYED" in code:
        color = "DOPE_DYED"
    elif "_COLORED" in code:
        color = "COLORED"
    color_mult = Decimal(str(adjustments["color_state"].get(color, 1.0)))
    if color_mult != 1:
        multiplier *= color_mult
        notes.append(f"×color[{color}]={color_mult}")

    # Specialty
    specialty = None
    if "_CORESPUN" in code or "ELASTANE" in code:
        specialty = "corespun"
    if specialty:
        sp_mult = Decimal(str(adjustments["specialty"].get(specialty, 1.0)))
        if sp_mult != 1:
            multiplier *= sp_mult
            notes.append(f"×specialty[{specialty}]={sp_mult}")

    # Step 4: count band modifier
    ne = _extract_ne(code)
    if ne:
        if ne < 20:
            cb = count_bands["Ne_8_to_20"]
        elif ne < 30:
            cb = count_bands["Ne_20_to_30"]
        elif ne < 40:
            cb = count_bands["Ne_30_to_40"]
        elif ne < 60:
            cb = count_bands["Ne_40_to_60"]
        else:
            cb = count_bands["Ne_60_plus"]
        cb_mult = Decimal(str(cb))
        if cb_mult != 1:
            multiplier *= cb_mult
            notes.append(f"×count_band[Ne_{ne}]={cb_mult}")

    final_markup = base * multiplier
    notes.append(f"=markup={final_markup:.4f}")
    return final_markup


def _extract_ply(code: str) -> int:
    """Extract ply from yarn_code: NE30_1, NE40_2, etc."""
    import re
    m = re.search(r"NE\d+_(\d)", code)
    return int(m.group(1)) if m else 1


def _extract_ne(code: str) -> Optional[int]:
    """Extract Ne count from yarn_code."""
    import re
    m = re.search(r"NE(\d+)", code)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# 6. Pressure / signal
# ---------------------------------------------------------------------------

def compute_pressure_7d(conn, yarn_id: int, current_index: Decimal,
                         on_date: date) -> Optional[Decimal]:
    """
    7-day price change %. Looks up estimated_index from fact_yarn_price_pressure
    for date - 7. Returns None on cold start.
    """
    if current_index is None:
        return None
    query = """
        SELECT estimated_index
        FROM fact_yarn_price_pressure
        WHERE yarn_id = %s
          AND calc_date = %s::date - INTERVAL '7 days'
        LIMIT 1;
    """
    with conn.cursor() as cur:
        cur.execute(query, (yarn_id, on_date))
        row = cur.fetchone()
    if not row or row[0] is None:
        return None
    prev = Decimal(str(row[0]))
    if prev == 0:
        return None
    return ((current_index - prev) / prev * Decimal("100")).quantize(Decimal("0.01"))


def classify_signal(pressure_7d: Optional[Decimal]) -> str:
    if pressure_7d is None:
        return "no_data"
    val = float(pressure_7d)
    if val > PRESSURE_THRESHOLDS["rising"]:
        return "rising"
    if val < PRESSURE_THRESHOLDS["falling"]:
        return "falling"
    return "stable"


# ---------------------------------------------------------------------------
# 7. Persister
# ---------------------------------------------------------------------------

def write_to_fact_table(conn, results: list[PricingResult], dry_run: bool):
    """
    UPSERT into fact_yarn_price_pressure: DELETE existing rows for
    (calc_date, yarn_id) then bulk INSERT. Wrapped in transaction.
    """
    if not results:
        logger.info("No results to write")
        return

    if dry_run:
        for r in results:
            notes = " | ".join(r.debug_notes[:5])
            logger.info(
                f"[DRY] yarn_id={r.yarn_id} ({r.yarn_code}) date={r.calc_date} "
                f"index=${r.estimated_index} method={r.pricing_method} "
                f"conf={r.confidence} signal={r.pressure_signal} "
                f"pressure_7d={r.pressure_7d} | {notes}"
            )
        return

    calc_date = results[0].calc_date  # all results share one date in a daily run
    yarn_ids = [r.yarn_id for r in results]

    with conn.cursor() as cur:
        # Delete prior rows for this date+yarn_id set
        cur.execute(
            """
            DELETE FROM fact_yarn_price_pressure
            WHERE calc_date = %s AND yarn_id = ANY(%s);
            """,
            (calc_date, yarn_ids),
        )
        deleted = cur.rowcount
        # Bulk insert
        rows = [
            (
                r.calc_date, r.yarn_id, r.driver_price_usd, r.estimated_index,
                r.pressure_7d, r.pressure_signal, r.confidence, r.pricing_method,
            )
            for r in results
        ]
        execute_values(
            cur,
            """
            INSERT INTO fact_yarn_price_pressure
                (calc_date, yarn_id, driver_price_usd, estimated_index,
                 pressure_7d, pressure_signal, confidence, pricing_method)
            VALUES %s
            """,
            rows,
        )
    conn.commit()
    logger.info(f"Wrote {len(results)} pricing rows ({deleted} deleted first) "
                f"for {calc_date}")


# ---------------------------------------------------------------------------
# 8. Main driver
# ---------------------------------------------------------------------------

def daily_run(conn, on_date: date, dry_run: bool = False,
               yarn_id_filter: Optional[int] = None) -> list[PricingResult]:
    """Compute pricing for all market-common yarns on given date."""
    markup_config = load_markup_config()
    yarns = load_active_yarns(conn)
    if yarn_id_filter:
        yarns = [y for y in yarns if y.yarn_id == yarn_id_filter]
    if not yarns:
        logger.warning("No yarns found to price")
        return []

    # Step 1: driver inference for all yarns (collected for audit)
    inference_results: list[InferenceResult] = []
    for y in yarns:
        infer_input = InferenceYarnSpec(
            yarn_id=y.yarn_id,
            canonical_code=y.yarn_code,
            fiber_family=y.fiber_family,
            blend_ratio_json=y.blend_ratio_json,
            is_recycled=y.is_recycled,
        )
        result = infer_driver_slug(infer_input)
        y.driver_slug = result.inferred_driver_slug
        y.inference_reason = result.inference_reason
        y.upstream_benchmark_slug = load_upstream_for_driver(conn, y.driver_slug)
        y.is_authoritative = y.driver_slug in AUTHORITATIVE_DRIVERS
        inference_results.append(result)

    # Audit log
    audit_path = write_audit_log(inference_results, AUDIT_LOG_DIR)
    logger.info(f"Audit log: {audit_path}")

    # Step 2: pricing
    results = []
    for yarn in yarns:
        try:
            result = compute_yarn_price(conn, yarn, on_date, markup_config)
            result.pressure_7d = compute_pressure_7d(
                conn, yarn.yarn_id, result.estimated_index, on_date
            )
            result.pressure_signal = classify_signal(result.pressure_7d)
            results.append(result)
        except Exception as e:
            logger.exception(f"Pricing failed for yarn_id={yarn.yarn_id} "
                             f"({yarn.yarn_code}): {e}")

    # Step 3: persist
    write_to_fact_table(conn, results, dry_run=dry_run)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", type=int, default=0,
                        help="Number of past days to backfill (default: 0 = today)")
    parser.add_argument("--yarn-id", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        if args.backfill > 0:
            today = date.today()
            for i in range(args.backfill, -1, -1):
                run_date = today - timedelta(days=i)
                logger.info(f"=== Backfill day: {run_date} ===")
                daily_run(conn, run_date, args.dry_run, args.yarn_id)
        else:
            results = daily_run(conn, date.today(), args.dry_run, args.yarn_id)
            logger.info(f"Computed {len(results)} prices for {date.today()}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
