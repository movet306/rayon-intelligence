"""
Yarn driver slug inference module.

Single source of truth for mapping a YarnSpec (from dim_yarn_master) to its
primary_driver_slug used in the pricing waterfall. Inference is declarative
(prioritized rule list with regex + condition lambda + reason string), so
adding a new yarn family means adding ONE rule entry, not editing pricer code.

Every infer_driver_slug() call returns an InferenceResult that the orchestrator
collects and writes to a per-run audit CSV:

    yarn_id | canonical_code | inferred_driver_slug | inference_reason

Designed for Phase C / Phase B5 fair evidence integration. When the evidence
sheet -> dim_yarn_master sync (Phase C+1) is implemented, primary_driver_slug
will move to a DB column and this module becomes a fallback validator.

Usage:

    from pricing.driver_inference import (
        YarnSpec, InferenceResult, infer_driver_slug, write_audit_log
    )

    results = []
    for yarn in active_yarns:
        results.append(infer_driver_slug(yarn))
    write_audit_log(results, Path("logs/inference"))
"""

from __future__ import annotations
import re
import csv
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class YarnSpec:
    """
    Minimal yarn fields needed for driver inference. Populated from
    dim_yarn_master JOIN with any sheet-derived metadata in scope.
    """
    yarn_id: int
    canonical_code: str             # e.g., "PES_NE30_1_RING_STAPLE"
    fiber_family: str               # 'polyester' / 'viscose' / 'blend' etc.
    blend_ratio_json: Optional[dict]  # parsed from JSONB; None for single fiber
    color_state: Optional[str] = None
    is_recycled: bool = False


@dataclass
class InferenceResult:
    yarn_id: int
    canonical_code: str
    inferred_driver_slug: str
    inference_reason: str           # 'P{priority}:{rule_name}'


# ---------------------------------------------------------------------------
# Helper predicates
# ---------------------------------------------------------------------------

def _is_blend(yarn: YarnSpec) -> bool:
    """A yarn is a blend if family='blend' OR blend_ratio has multiple fibers."""
    if yarn.fiber_family == "blend":
        return True
    if yarn.blend_ratio_json is None:
        return False
    fibers = _blend_fibers(yarn)
    return len(fibers) > 1


def _blend_fibers(yarn: YarnSpec) -> set[str]:
    """Return the set of actual fiber keys, excluding _metadata keys."""
    if not yarn.blend_ratio_json:
        return set()
    return {k for k in yarn.blend_ratio_json.keys() if not k.startswith("_")}


def _has_fibers(yarn: YarnSpec, required: set[str]) -> bool:
    """Check that ALL required fibers are present in the blend."""
    return required.issubset(_blend_fibers(yarn))


def _is_cotton_blend(yarn: YarnSpec) -> bool:
    """Cotton (COT) + at least one secondary fiber, and no PV/PM-style match
    that would have already matched at higher priority."""
    fibers = _blend_fibers(yarn)
    if "COT" not in fibers:
        return False
    if len(fibers) < 2:
        return False
    # Exclude pure PV / PM / 3-component cases (those are caught at higher priority)
    return True


def _has_recycled_fiber(yarn: YarnSpec) -> bool:
    """recycle_flag set OR canonical_code includes recycled marker OR
    blend_ratio_json contains RCY_ prefix fibers."""
    if yarn.is_recycled:
        return True
    if "_RECYCLED" in yarn.canonical_code:
        return True
    if "RCY_" in yarn.canonical_code:
        return True
    if yarn.blend_ratio_json:
        return any(k.startswith("RCY_") for k in yarn.blend_ratio_json.keys())
    return False


# ---------------------------------------------------------------------------
# Rule definition: (priority, regex_pattern, condition_fn, output_slug, reason)
# Lower priority number = higher precedence. First match wins.
# ---------------------------------------------------------------------------

Rule = tuple[int, str, Callable[[YarnSpec], bool], str, str]

INFERENCE_RULES: list[Rule] = [
    # =====================================================================
    # Priority 1: Construction-specific (highest specificity)
    # Corespun overrides everything; recycled overrides family-based rules.
    # =====================================================================

    # Corespun (elastane core) — anywhere in code or blend ratio
    (1, r"_CORESPUN|ELASTANE",
     lambda y: True,
     "corespun_staple",
     "construction:corespun"),

    # Recycled polyester (single-fiber recycled PES)
    (1, r".*",
     lambda y: _has_recycled_fiber(y) and y.fiber_family == "polyester" and not _is_blend(y),
     "recycled_polyester_staple",
     "construction:recycled_polyester"),

    # Recycled blend (any blend with at least one recycled fiber)
    (1, r".*",
     lambda y: _has_recycled_fiber(y) and _is_blend(y),
     "recycled_blend_staple",
     "construction:recycled_blend"),

    # =====================================================================
    # Priority 2: Multi-component blends (3+ fibers)
    # =====================================================================

    (2, r".*",
     lambda y: _is_blend(y) and len(_blend_fibers(y)) >= 3,
     "three_component_staple",
     "blend:three_component"),

    # =====================================================================
    # Priority 3: Two-fiber blends (specific fiber combinations)
    # =====================================================================

    # PV blend: Polyester + Viscose
    (3, r"^PV_|^PES_VIS|^VIS_PES",
     lambda y: _is_blend(y) and _has_fibers(y, {"PES", "VIS"}) and len(_blend_fibers(y)) == 2,
     "pv_blend_staple",
     "blend:pv"),

    (3, r".*",
     lambda y: _is_blend(y) and _has_fibers(y, {"PES", "VIS"}) and len(_blend_fibers(y)) == 2,
     "pv_blend_staple",
     "blend:pv_via_ratio"),

    # PM blend: Polyester + Modal
    (3, r"^PM_|^PES_MOD|^MOD_PES",
     lambda y: _is_blend(y) and _has_fibers(y, {"PES", "MOD"}) and len(_blend_fibers(y)) == 2,
     "pm_blend_staple",
     "blend:pm"),

    (3, r".*",
     lambda y: _is_blend(y) and _has_fibers(y, {"PES", "MOD"}) and len(_blend_fibers(y)) == 2,
     "pm_blend_staple",
     "blend:pm_via_ratio"),

    # Cotton blends (PC, CV, CM): Cotton + secondary
    (3, r".*",
     lambda y: _is_blend(y) and _is_cotton_blend(y) and len(_blend_fibers(y)) == 2,
     "cotton_blend_staple",
     "blend:cotton_with_secondary"),

    # =====================================================================
    # Priority 4: Single-fiber staple (one rule per family)
    # =====================================================================

    (4, r".*",
     lambda y: y.fiber_family == "viscose" and not _is_blend(y),
     "viscose_staple",
     "single:viscose"),

    (4, r".*",
     lambda y: y.fiber_family == "modal" and not _is_blend(y),
     "modal_staple",
     "single:modal"),

    (4, r".*",
     lambda y: y.fiber_family == "cotton" and not _is_blend(y),
     "cotton_staple",
     "single:cotton"),

    (4, r"_STAPLE",
     lambda y: y.fiber_family == "polyester" and not _is_blend(y),
     "polyester_staple",
     "single:polyester_staple"),

    (4, r"_STAPLE",
     lambda y: y.fiber_family == "polyamide" and not _is_blend(y),
     "polyamide_staple",
     "single:polyamide_staple"),

    # =====================================================================
    # Priority 5: Filament-specific suffixes (DTY, POY, GIPE)
    # Match these BEFORE the default filament fallback.
    # =====================================================================

    (5, r"_DTY|_GIPE",
     lambda y: y.fiber_family == "polyester",
     "polyester_dty",
     "filament:polyester_dty"),

    (5, r"_POY",
     lambda y: y.fiber_family == "polyester",
     "polyester_poy",
     "filament:polyester_poy"),

    # =====================================================================
    # Priority 6: Filament default fallback
    # Any polyester or polyamide yarn that is NOT a blend, NOT staple,
    # and did not match a specific filament suffix above. Catches FDY,
    # PA6.6 HT (tire cord), and other generic filament codes.
    # =====================================================================

    (6, r".*",
     lambda y: y.fiber_family == "polyester" and not _is_blend(y)
               and "_STAPLE" not in y.canonical_code,
     "polyester_fdy",
     "filament:polyester_default"),

    (6, r".*",
     lambda y: y.fiber_family == "polyamide" and not _is_blend(y)
               and "_STAPLE" not in y.canonical_code,
     "polyamide_fdy",
     "filament:polyamide_default"),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def infer_driver_slug(yarn: YarnSpec) -> InferenceResult:
    """
    Apply rules in priority order. First matching rule wins.
    Always returns an InferenceResult; falls back to polyester_staple
    with a 'P99:default_fallback' reason if no rule matches (logged warning).
    """
    sorted_rules = sorted(INFERENCE_RULES, key=lambda r: r[0])
    for priority, regex, cond_fn, output_slug, reason in sorted_rules:
        if re.search(regex, yarn.canonical_code) and cond_fn(yarn):
            return InferenceResult(
                yarn_id=yarn.yarn_id,
                canonical_code=yarn.canonical_code,
                inferred_driver_slug=output_slug,
                inference_reason=f"P{priority}:{reason}",
            )

    logger.warning(
        f"No inference rule matched for yarn_id={yarn.yarn_id} "
        f"canonical_code={yarn.canonical_code} fiber_family={yarn.fiber_family}; "
        f"falling back to polyester_staple"
    )
    return InferenceResult(
        yarn_id=yarn.yarn_id,
        canonical_code=yarn.canonical_code,
        inferred_driver_slug="polyester_staple",
        inference_reason="P99:default_fallback",
    )


def write_audit_log(results: list[InferenceResult], output_dir: Path) -> Path:
    """
    Append-only audit CSV per run, named by timestamp.
    Returns the written path.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"driver_inference_{timestamp}.csv"
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["yarn_id", "canonical_code",
                        "inferred_driver_slug", "inference_reason"],
        )
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))
    logger.info(f"Wrote {len(results)} inference records to {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Self-test (run as script for sanity checks)
# ---------------------------------------------------------------------------

def _self_test():
    """Quick sanity check on representative yarn specs from evidence sheet."""
    fixtures = [
        # Single-fiber
        YarnSpec(1, "VIS_NE30_1_RING_STAPLE",  "viscose",   None),
        YarnSpec(2, "MOD_NE30_1_RING_STAPLE",  "modal",     None),
        YarnSpec(3, "COT_NE30_1_RING",          "cotton",    None),
        YarnSpec(4, "PES_NE30_1_RING_STAPLE",   "polyester", None),
        YarnSpec(5, "PA66_NE30_1_RING_STAPLE",  "polyamide", None),

        # Filament
        YarnSpec(6, "PES_75D_36F_DTY",          "polyester", None),
        YarnSpec(7, "PES_75D_36F_GIPE_40",      "polyester", None),
        YarnSpec(8, "PES_75D_36F_FDY",          "polyester", None),
        YarnSpec(9, "PA6.6_470D_136F_HT_A",     "polyamide", None),

        # Two-fiber blend
        YarnSpec(10, "PV_NE40_1_65_35",        "blend", {"PES": 65, "VIS": 35}),
        YarnSpec(11, "PM_NE28_1_50_50",        "blend", {"PES": 50, "MOD": 50}),
        YarnSpec(12, "COT_PES_70_30_NE30_1",   "blend", {"COT": 70, "PES": 30}),
        YarnSpec(13, "COT_VIS_50_50_NE30_1",   "blend", {"COT": 50, "VIS": 50}),

        # Three-component
        YarnSpec(14, "PES_VIS_COT_50_30_20_NE30_1", "blend",
                 {"PES": 50, "VIS": 30, "COT": 20}),

        # Corespun
        YarnSpec(15, "COT_ELASTANE_NE30_1_CORESPUN", "blend",
                 {"COT": 97, "ELASTANE": 3}),
        YarnSpec(16, "PV_NE40_2_LYCRA_CORESPUN_BLACK", "blend",
                 {"PES": 62, "VIS": 33, "ELASTANE": 5}),

        # Recycled
        YarnSpec(17, "PES_NE30_1_RING_RECYCLED", "polyester", None, is_recycled=True),
        YarnSpec(18, "COT_RECYCLED_PES_50_50_NE30_1", "blend",
                 {"COT": 50, "RCY_PES": 50}, is_recycled=True),
    ]

    expected = [
        "viscose_staple",
        "modal_staple",
        "cotton_staple",
        "polyester_staple",
        "polyamide_staple",
        "polyester_dty",
        "polyester_dty",     # GIPE -> DTY
        "polyester_fdy",
        "polyamide_fdy",
        "pv_blend_staple",
        "pm_blend_staple",
        "cotton_blend_staple",
        "cotton_blend_staple",
        "three_component_staple",
        "corespun_staple",
        "corespun_staple",
        "recycled_polyester_staple",
        "recycled_blend_staple",
    ]

    print(f"{'yarn_id':>7} | {'canonical_code':<40} | "
          f"{'inferred':<28} | {'expected':<28} | {'OK':<3}")
    print("-" * 120)
    pass_count = 0
    for yarn, expected_slug in zip(fixtures, expected):
        result = infer_driver_slug(yarn)
        ok = "PASS" if result.inferred_driver_slug == expected_slug else "FAIL"
        if ok == "PASS":
            pass_count += 1
        print(f"{yarn.yarn_id:>7} | {yarn.canonical_code:<40} | "
              f"{result.inferred_driver_slug:<28} | {expected_slug:<28} | {ok}")
    print("-" * 120)
    print(f"Result: {pass_count}/{len(fixtures)} passed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _self_test()
