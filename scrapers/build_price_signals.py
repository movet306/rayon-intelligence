"""
scrapers/build_price_signals.py — Price Intelligence Signal Engine (Etap 1D)

Reads price_metrics_daily and price_chain_spreads, applies 8 signal rules,
and upserts structured signals into price_intelligence_signals.

Signal Rules:
  1  COST_PRESSURE_UP          change_7d >= +3.0%
  2  COST_PRESSURE_DOWN        change_7d <= -3.0%
  3  UPSTREAM_DOWNSTREAM_DIVG  divergence_score >= 3.0
  4  SPREAD_WIDENING           zscore_30d >= +1.5
  5  SPREAD_TIGHTENING         zscore_30d <= -1.5
  6  VOLATILITY_SPIKE          volatility_7d > 2x rolling average
  7  DELAYED_PASS_THROUGH_RISK PTA up but FDY/POY not yet moving
  8  DATA_QUALITY_WARNING      confidence_tier = 'E' (suppressed)

Usage:
    python scrapers/build_price_signals.py
    python scrapers/build_price_signals.py --dry-run
    python scrapers/build_price_signals.py --date 2026-04-20
"""

import argparse
import logging
import os
from datetime import date, timedelta

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Turkish display labels
# ---------------------------------------------------------------------------

MATERIAL_LABELS = {
    "pta":                    "PTA",
    "polyester_fdy":          "Polyester FDY",
    "polyester_poy":          "Polyester POY",
    "polyester_dty":          "Polyester DTY",
    "polyester_yarn":         "Polyester Iplik",
    "polyester_staple_fiber": "Polyester Stapel Elyaf",
    "pa6_chip":               "PA6 Cip",
    "pa66_chip":              "PA66 Cip",
    "polyamide_fdy":          "Poliamid FDY",
    "cotton_lint":            "Pamuk Lif (Cin spot)",
    "cotton_lint_futures":    "Pamuk Lif (ICE vadeli)",
    "cotton_yarn":            "Pamuk Iplik",
    "rayon_yarn":             "Viskon Iplik",
    "adipic_acid":            "Adipik Asit",
}

FAMILY_BUSINESS_IMPL_UP = {
    "polyester": (
        "Polyester iplik maliyetleri artabilir. "
        "Turkiye'ye tahmini yansima: {lag_min}-{lag_max} hafta."
    ),
    "nylon": (
        "Naylon iplik maliyet baskisi. "
        "Teknik/askeri kumas uretim maliyeti etkilenecek."
    ),
    "cotton": "Pamuk iplik maliyet baskisi.",
    "rayon":  "Viskon kumas uretim maliyeti etkilenecek.",
}

FAMILY_BUSINESS_IMPL_DOWN = {
    "polyester": "Polyester maliyet baskisi azaliyor. Yakin vadede fiyat dususu mumkun.",
    "nylon":     "Naylon maliyet baskisi azaliyor. Yakin vadede fiyat dususu mumkun.",
    "cotton":    "Pamuk maliyet baskisi azaliyor. Yakin vadede fiyat dususu mumkun.",
    "rayon":     "Viskon maliyet baskisi azaliyor. Yakin vadede fiyat dususu mumkun.",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GOOD_TIERS = {"A", "B", "C", "D"}


def mat_label(slug: str) -> str:
    return MATERIAL_LABELS.get(slug, slug.replace("_", " ").title())


def severity_from_pct(pct_abs: float) -> str:
    if pct_abs >= 10: return "critical"
    if pct_abs >= 7:  return "high"
    if pct_abs >= 5:  return "medium"
    return "low"


def severity_from_zscore(zscore_abs: float) -> str:
    if zscore_abs >= 2.5: return "high"
    if zscore_abs >= 2.0: return "medium"
    return "low"


def _fetch(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or [])
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_latest_metrics(conn):
    """
    Latest price_metrics_daily row per material (daily frequency only).
    Returns dict: material -> row dict.
    """
    rows = _fetch(conn, """
        SELECT DISTINCT ON (material)
            material, metric_date, frequency, price_usd,
            change_1d, change_7d, change_30d,
            volatility_7d, volatility_30d,
            divergence_score, confidence_tier,
            data_points, momentum_score, trend_direction
        FROM price_metrics_daily
        WHERE frequency = 'daily'
        ORDER BY material, metric_date DESC
    """)
    return {r["material"]: dict(r) for r in rows}


def load_volatility_history(conn, lookback_rows: int = 30):
    """
    For each material, fetch the last `lookback_rows` volatility_7d values
    (daily, excluding NULLs). Returns dict: material -> [float, ...]
    """
    rows = _fetch(conn, """
        SELECT material, metric_date, volatility_7d
        FROM price_metrics_daily
        WHERE frequency = 'daily' AND volatility_7d IS NOT NULL AND volatility_7d > 0
        ORDER BY material, metric_date DESC
    """)

    by_mat: dict[str, list] = {}
    for r in rows:
        lst = by_mat.setdefault(r["material"], [])
        if len(lst) < lookback_rows:
            lst.append(float(r["volatility_7d"]))

    return by_mat


def load_dim_material(conn):
    """Returns dict: slug -> {family, material_form, lag_min_weeks, lag_max_weeks}"""
    rows = _fetch(conn, """
        SELECT slug, family, material_form, lag_min_weeks, lag_max_weeks
        FROM dim_material
    """)
    return {r["slug"]: dict(r) for r in rows}


def load_latest_spreads(conn):
    """
    Latest price_chain_spreads row per (upstream, downstream) pair.
    Returns list of dicts.
    """
    return _fetch(conn, """
        SELECT DISTINCT ON (upstream_slug, downstream_slug)
            calc_date, chain, upstream_slug, downstream_slug,
            spread_usd, spread_pct, spread_7d_delta, zscore_30d, signal
        FROM price_chain_spreads
        ORDER BY upstream_slug, downstream_slug, calc_date DESC
    """)


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------

def rule1_cost_pressure_up(metrics, dim_mat, signal_date):
    """COST_PRESSURE_UP: change_7d >= +3.0% on good-tier daily series."""
    signals = []
    for mat, row in metrics.items():
        if row["confidence_tier"] not in GOOD_TIERS:
            continue
        c7 = row["change_7d"]
        if c7 is None or float(c7) < 3.0:
            continue

        pct = float(c7)
        info = dim_mat.get(mat, {})
        family = info.get("family", "unknown")
        lag_min = info.get("lag_min_weeks")
        lag_max = info.get("lag_max_weeks")
        label   = mat_label(mat)

        impl_tmpl = FAMILY_BUSINESS_IMPL_UP.get(family, "Maliyet artisi bekleniyor.")
        impl = impl_tmpl.format(lag_min=lag_min, lag_max=lag_max) if lag_min else impl_tmpl

        signals.append({
            "signal_date":           signal_date,
            "signal_type":           "COST_PRESSURE_UP",
            "chain":                 family,
            "material_slug":         mat,
            "upstream_slug":         None,
            "downstream_slug":       None,
            "severity":              severity_from_pct(pct),
            "time_horizon":          "short",
            "confidence_tier":       row["confidence_tier"],
            "value_pct":             round(pct, 4),
            "explanation":           f"{label} son 7 gunde +{pct:.1f}% artti (China spot)",
            "business_implication":  impl,
            "turkey_lag_min":        lag_min,
            "turkey_lag_max":        lag_max,
            "suppressed":            False,
        })
    return signals


def rule2_cost_pressure_down(metrics, dim_mat, signal_date):
    """COST_PRESSURE_DOWN: change_7d <= -3.0% on good-tier daily series."""
    signals = []
    for mat, row in metrics.items():
        if row["confidence_tier"] not in GOOD_TIERS:
            continue
        c7 = row["change_7d"]
        if c7 is None or float(c7) > -3.0:
            continue

        pct = float(c7)
        pct_abs = abs(pct)
        info = dim_mat.get(mat, {})
        family = info.get("family", "unknown")
        lag_min = info.get("lag_min_weeks")
        lag_max = info.get("lag_max_weeks")
        label   = mat_label(mat)

        impl = FAMILY_BUSINESS_IMPL_DOWN.get(family, "Maliyet baskisi azaliyor.")

        signals.append({
            "signal_date":           signal_date,
            "signal_type":           "COST_PRESSURE_DOWN",
            "chain":                 family,
            "material_slug":         mat,
            "upstream_slug":         None,
            "downstream_slug":       None,
            "severity":              severity_from_pct(pct_abs),
            "time_horizon":          "short",
            "confidence_tier":       row["confidence_tier"],
            "value_pct":             round(pct, 4),
            "explanation":           f"{label} son 7 gunde {pct:.1f}% geriledi (China spot)",
            "business_implication":  impl,
            "turkey_lag_min":        lag_min,
            "turkey_lag_max":        lag_max,
            "suppressed":            False,
        })
    return signals


def rule3_divergence(metrics, dim_mat, signal_date):
    """UPSTREAM_DOWNSTREAM_DIVERGENCE: divergence_score >= 3.0."""
    signals = []

    # Map upstream slug → change_7d for explanation
    up_change: dict[str, float] = {}
    CHAIN_PAIRS = {
        "polyester_fdy":   "pta",
        "polyester_poy":   "pta",
        "polyester_dty":   "polyester_poy",
        "polyester_yarn":  "polyester_dty",
        "polyamide_fdy":   "pa6_chip",
        "cotton_yarn":     "cotton_lint",
    }
    for mat, row in metrics.items():
        c7 = row["change_7d"]
        if c7 is not None:
            up_change[mat] = float(c7)

    for mat, row in metrics.items():
        if row["confidence_tier"] not in GOOD_TIERS:
            continue
        div = row["divergence_score"]
        if div is None or float(div) < 3.0:
            continue

        div_val  = float(div)
        info     = dim_mat.get(mat, {})
        family   = info.get("family", "unknown")
        lag_min  = info.get("lag_min_weeks")
        lag_max  = info.get("lag_max_weeks")
        upstream = CHAIN_PAIRS.get(mat)

        if div_val >= 7:   sev = "high"
        elif div_val >= 5: sev = "medium"
        else:              sev = "low"

        up_label   = mat_label(upstream) if upstream else "upstream"
        dn_label   = mat_label(mat)
        up_c7_val  = up_change.get(upstream, 0.0)

        expl = (
            f"Upstream {up_label} +{up_c7_val:.1f}% artarken "
            f"{dn_label} henuz tepki vermedi ({div_val:.1f}% fark)"
        )
        if lag_min and lag_max:
            impl = (
                f"{dn_label} fiyat artisi gecikmis olabilir. "
                f"{lag_min}-{lag_max} hafta icinde yansima beklenir."
            )
        else:
            impl = f"{dn_label} fiyat artisi gecikmis olabilir."

        signals.append({
            "signal_date":           signal_date,
            "signal_type":           "UPSTREAM_DOWNSTREAM_DIVG",
            "chain":                 family,
            "material_slug":         mat,
            "upstream_slug":         upstream,
            "downstream_slug":       None,
            "severity":              sev,
            "time_horizon":          "mid",
            "confidence_tier":       row["confidence_tier"],
            "value_pct":             round(div_val, 4),
            "explanation":           expl,
            "business_implication":  impl,
            "turkey_lag_min":        lag_min,
            "turkey_lag_max":        lag_max,
            "suppressed":            False,
        })
    return signals


def rule4_spread_widening(spreads, signal_date):
    """SPREAD_WIDENING: zscore_30d >= +1.5 and signal='widening'."""
    signals = []
    for row in spreads:
        if row["signal"] != "widening":
            continue
        zscore = row["zscore_30d"]
        if zscore is None or float(zscore) < 1.5:
            continue

        z = float(zscore)
        up_lbl = mat_label(row["upstream_slug"])
        dn_lbl = mat_label(row["downstream_slug"])

        signals.append({
            "signal_date":           signal_date,
            "signal_type":           "SPREAD_WIDENING",
            "chain":                 row["chain"],
            "material_slug":         None,
            "upstream_slug":         row["upstream_slug"],
            "downstream_slug":       row["downstream_slug"],
            "severity":              severity_from_zscore(z),
            "time_horizon":          "short",
            "confidence_tier":       None,
            "value_pct":             round(z, 4),
            "explanation":           (
                f"{up_lbl}->{dn_lbl} spread tarihsel ortalamanin "
                f"+{z:.1f} std uzerinde"
            ),
            "business_implication":  (
                "Donusum marji genisliyyor — hammadde sikisiyor "
                "veya isleme kapasitesi daraliyor."
            ),
            "turkey_lag_min":        None,
            "turkey_lag_max":        None,
            "suppressed":            False,
        })
    return signals


def rule5_spread_tightening(spreads, signal_date):
    """SPREAD_TIGHTENING: zscore_30d <= -1.5 and signal='tightening'."""
    signals = []
    for row in spreads:
        if row["signal"] != "tightening":
            continue
        zscore = row["zscore_30d"]
        if zscore is None or float(zscore) > -1.5:
            continue

        z = float(zscore)
        z_abs = abs(z)
        up_lbl = mat_label(row["upstream_slug"])
        dn_lbl = mat_label(row["downstream_slug"])

        signals.append({
            "signal_date":           signal_date,
            "signal_type":           "SPREAD_TIGHTENING",
            "chain":                 row["chain"],
            "material_slug":         None,
            "upstream_slug":         row["upstream_slug"],
            "downstream_slug":       row["downstream_slug"],
            "severity":              severity_from_zscore(z_abs),
            "time_horizon":          "short",
            "confidence_tier":       None,
            "value_pct":             round(z, 4),
            "explanation":           (
                f"{up_lbl}->{dn_lbl} spread tarihsel ortalamanin "
                f"{z:.1f} std altinda"
            ),
            "business_implication":  "Donusum marji daraliyor.",
            "turkey_lag_min":        None,
            "turkey_lag_max":        None,
            "suppressed":            False,
        })
    return signals


def rule6_volatility_spike(metrics, vol_history, dim_mat, signal_date):
    """VOLATILITY_SPIKE: volatility_7d > 2x rolling average of last 30 values."""
    signals = []
    for mat, row in metrics.items():
        if row["confidence_tier"] not in GOOD_TIERS:
            continue
        if row["data_points"] is None or int(row["data_points"]) < 30:
            continue
        vol_now = row["volatility_7d"]
        if vol_now is None or float(vol_now) == 0:
            continue

        vol_now_f = float(vol_now)
        history = vol_history.get(mat, [])
        if len(history) < 7:
            continue

        avg_vol = sum(history) / len(history)
        if avg_vol == 0:
            continue

        ratio = vol_now_f / avg_vol
        if ratio < 2.0:
            continue

        info   = dim_mat.get(mat, {})
        family = info.get("family", "unknown")
        label  = mat_label(mat)
        sev    = "high" if ratio >= 3.0 else "medium"

        signals.append({
            "signal_date":           signal_date,
            "signal_type":           "VOLATILITY_SPIKE",
            "chain":                 family,
            "material_slug":         mat,
            "upstream_slug":         None,
            "downstream_slug":       None,
            "severity":              sev,
            "time_horizon":          "short",
            "confidence_tier":       row["confidence_tier"],
            "value_pct":             round(ratio, 4),
            "explanation":           (
                f"{label} volatilitesi normalin {ratio:.1f} katina cikti"
            ),
            "business_implication":  (
                "Fiyat belirsizligi yuksek — satin alma kararlarinda dikkat."
            ),
            "turkey_lag_min":        None,
            "turkey_lag_max":        None,
            "suppressed":            False,
        })
    return signals


def rule7_delayed_pass_through(metrics, signal_date):
    """DELAYED_PASS_THROUGH_RISK: PTA up >= 3% but FDY/POY not moving."""
    signals = []
    pta_row = metrics.get("pta")
    if pta_row is None or pta_row["confidence_tier"] not in GOOD_TIERS:
        return signals

    pta_c7 = pta_row["change_7d"]
    if pta_c7 is None or float(pta_c7) < 3.0:
        return signals

    pta_pct = float(pta_c7)
    sev     = "high" if pta_pct >= 5.0 else "medium"

    # Check each downstream — generate a signal for any that hasn't moved
    laggards = []
    for slug in ("polyester_fdy", "polyester_poy"):
        row = metrics.get(slug)
        if row is None:
            continue
        c7 = row["change_7d"]
        if c7 is None or float(c7) < 1.0:
            laggards.append(mat_label(slug))

    if not laggards:
        return signals

    laggard_str = "/".join(laggards)

    signals.append({
        "signal_date":           signal_date,
        "signal_type":           "DELAYED_PASS_THROUGH_RISK",
        "chain":                 "polyester",
        "material_slug":         "pta",
        "upstream_slug":         "pta",
        "downstream_slug":       "polyester_fdy",
        "severity":              sev,
        "time_horizon":          "mid",
        "confidence_tier":       pta_row["confidence_tier"],
        "value_pct":             round(pta_pct, 4),
        "explanation":           (
            f"PTA +{pta_pct:.1f}% artarken {laggard_str} henuz tepki vermedi"
        ),
        "business_implication":  (
            "Polyester iplik fiyat artisi gecikmis. "
            "4-8 hafta icinde Turkiye'ye yansimasi bekleniyor."
        ),
        "turkey_lag_min":        4,
        "turkey_lag_max":        8,
        "suppressed":            False,
    })
    return signals


def rule8_data_quality_warning(metrics, dim_mat, signal_date):
    """DATA_QUALITY_WARNING: confidence_tier = 'E' — suppressed."""
    signals = []
    for mat, row in metrics.items():
        if row["confidence_tier"] != "E":
            continue

        dp = int(row["data_points"]) if row["data_points"] else 0
        days_needed = max(0, 7 - dp)
        info   = dim_mat.get(mat, {})
        family = info.get("family", "unknown")
        label  = mat_label(mat)

        signals.append({
            "signal_date":           signal_date,
            "signal_type":           "DATA_QUALITY_WARNING",
            "chain":                 family,
            "material_slug":         mat,
            "upstream_slug":         None,
            "downstream_slug":       None,
            "severity":              "low",
            "time_horizon":          None,
            "confidence_tier":       "E",
            "value_pct":             None,
            "explanation":           (
                f"{label} icin yeterli veri yok ({dp} gun). "
                f"Metrikler {days_needed} gunde aktif olacak."
            ),
            "business_implication":  None,
            "turkey_lag_min":        None,
            "turkey_lag_max":        None,
            "suppressed":            True,
        })
    return signals


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

UPSERT_SQL = """
INSERT INTO price_intelligence_signals
    (signal_date, signal_type, chain, material_slug, upstream_slug, downstream_slug,
     severity, time_horizon, confidence_tier, value_pct,
     explanation, business_implication,
     turkey_lag_min, turkey_lag_max, suppressed)
VALUES
    (%(signal_date)s, %(signal_type)s, %(chain)s,
     %(material_slug)s, %(upstream_slug)s, %(downstream_slug)s,
     %(severity)s, %(time_horizon)s, %(confidence_tier)s, %(value_pct)s,
     %(explanation)s, %(business_implication)s,
     %(turkey_lag_min)s, %(turkey_lag_max)s, %(suppressed)s)
ON CONFLICT (signal_date, signal_type, material_slug, upstream_slug, downstream_slug)
DO UPDATE SET
    severity             = EXCLUDED.severity,
    time_horizon         = EXCLUDED.time_horizon,
    confidence_tier      = EXCLUDED.confidence_tier,
    value_pct            = EXCLUDED.value_pct,
    explanation          = EXCLUDED.explanation,
    business_implication = EXCLUDED.business_implication,
    turkey_lag_min       = EXCLUDED.turkey_lag_min,
    turkey_lag_max       = EXCLUDED.turkey_lag_max,
    suppressed           = EXCLUDED.suppressed
"""


def upsert_signals(conn, signals: list) -> int:
    if not signals:
        return 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, UPSERT_SQL, signals, page_size=100)
    conn.commit()
    return len(signals)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build price_intelligence_signals")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate signals but do not write to DB")
    parser.add_argument("--date", type=str, default=None,
                        help="Override signal_date (YYYY-MM-DD). Default: today.")
    args = parser.parse_args()

    signal_date = date.fromisoformat(args.date) if args.date else date.today()
    log.info("Signal date: %s", signal_date)

    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    # ── Load data ──────────────────────────────────────────────────────────
    log.info("Loading price_metrics_daily (latest per material)...")
    metrics = load_latest_metrics(conn)
    log.info("  %d materials loaded", len(metrics))

    log.info("Loading volatility history (last 30 rows per material)...")
    vol_history = load_volatility_history(conn)

    log.info("Loading dim_material...")
    dim_mat = load_dim_material(conn)

    log.info("Loading latest price_chain_spreads...")
    spreads = load_latest_spreads(conn)
    log.info("  %d spread pairs loaded", len(spreads))

    # ── Apply rules ────────────────────────────────────────────────────────
    all_signals = []

    r1 = rule1_cost_pressure_up(metrics, dim_mat, signal_date)
    r2 = rule2_cost_pressure_down(metrics, dim_mat, signal_date)
    r3 = rule3_divergence(metrics, dim_mat, signal_date)
    r4 = rule4_spread_widening(spreads, signal_date)
    r5 = rule5_spread_tightening(spreads, signal_date)
    r6 = rule6_volatility_spike(metrics, vol_history, dim_mat, signal_date)
    r7 = rule7_delayed_pass_through(metrics, signal_date)
    r8 = rule8_data_quality_warning(metrics, dim_mat, signal_date)

    all_signals = r1 + r2 + r3 + r4 + r5 + r6 + r7 + r8

    log.info("Rules fired: R1=%d R2=%d R3=%d R4=%d R5=%d R6=%d R7=%d R8=%d",
             len(r1), len(r2), len(r3), len(r4), len(r5), len(r6), len(r7), len(r8))

    # ── Upsert ─────────────────────────────────────────────────────────────
    if not args.dry_run:
        # Clear today's signals first for idempotent rebuild
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM price_intelligence_signals WHERE signal_date = %s",
                (signal_date,)
            )
        conn.commit()

        upsert_signals(conn, all_signals)
        log.info("Upserted %d signals for %s", len(all_signals), signal_date)
    else:
        log.info("[DRY-RUN] %d signals would be written", len(all_signals))

    conn.close()

    # ── Summary ────────────────────────────────────────────────────────────
    active   = [s for s in all_signals if not s["suppressed"]]
    suppressed = [s for s in all_signals if s["suppressed"]]

    counts_by_type: dict[str, int] = {}
    for s in active:
        counts_by_type[s["signal_type"]] = counts_by_type.get(s["signal_type"], 0) + 1

    sev_counts: dict[str, int] = {}
    for s in active:
        sev_counts[s["severity"]] = sev_counts.get(s["severity"], 0) + 1

    SEP  = "-" * 70
    mode = " [DRY-RUN]" if args.dry_run else ""
    print()
    print(SEP)
    print(f"  === Price Signals Generated ({signal_date}){mode} ===")
    print(SEP)
    print()
    print("  By signal type:")
    for stype, cnt in sorted(counts_by_type.items()):
        print(f"    {stype:<35}: {cnt}")
    print()
    print(f"  Total active  : {len(active)}")
    print(f"  Suppressed    : {len(suppressed)}")
    print(f"  Critical: {sev_counts.get('critical', 0)}   "
          f"High: {sev_counts.get('high', 0)}   "
          f"Medium: {sev_counts.get('medium', 0)}   "
          f"Low: {sev_counts.get('low', 0)}")
    print()

    # Detail table
    if active:
        print("  Active signals:")
        print(f"  {'Type':<35} {'Mat/Pair':<30} {'Sev':<9} {'Val':>7}  Explanation")
        print(f"  {'-'*35} {'-'*30} {'-'*8} {'-'*7}  {'-'*40}")
        for s in sorted(active, key=lambda x: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}[x["severity"]],
            x["signal_type"]
        )):
            mat_pair = s["material_slug"] or f"{s['upstream_slug']}->{s['downstream_slug']}"
            val_str  = f"{float(s['value_pct']):.2f}" if s["value_pct"] is not None else "-"
            expl     = s["explanation"][:48]
            print(f"  {s['signal_type']:<35} {mat_pair:<30} {s['severity']:<9} {val_str:>7}  {expl}")

    print(SEP)


if __name__ == "__main__":
    main()
