"""
build_price_metrics.py — Frequency-aware price metrics builder.

Reads price_signals, groups by (material, frequency) separately, computes
derived metrics appropriate to each frequency, and upserts into
price_metrics_daily.

Rules:
  daily  (sunsirs) — change_1d, change_7d, change_30d, MA7, MA30,
                      volatility_7d, volatility_30d, normalized_idx,
                      trend_direction
  monthly (indexmundi, fred_cotton) — change_30d only (as 1-month delta),
                      MA7/MA30 computed where data allows; NO 1d/7d metrics,
                      NO volatility

Validation:
  If a material exists in BOTH daily and monthly price_signals, emit a warning:
  "DUAL SOURCE: {material} — do not mix in signals"

Usage:
    python scrapers/build_price_metrics.py           # build all
    python scrapers/build_price_metrics.py --dry-run # compute only, no upsert
"""

import argparse
import logging
import os
import sys
from decimal import Decimal

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
# DB helpers
# ---------------------------------------------------------------------------

def get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def _fetch(conn, sql, params=None):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params or [])
        return cur.fetchall()


# ---------------------------------------------------------------------------
# Metric computation helpers
# ---------------------------------------------------------------------------

def _pct_change(new, old):
    """Return percentage change, or None if either value is None/zero."""
    if old is None or new is None or old == 0:
        return None
    return float((new - old) / old * 100)


def _ma(prices, window):
    """Simple moving average over last `window` values; None if insufficient."""
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window


def _stddev(prices, window):
    """Population std dev over last `window` values; None if insufficient."""
    if len(prices) < window:
        return None
    subset = prices[-window:]
    mean = sum(subset) / window
    variance = sum((p - mean) ** 2 for p in subset) / window
    return variance ** 0.5


def _trend(prices, window=3):
    """
    Simple trend over last `window` values.
    Returns 'up', 'down', or 'flat'. None if < window values.
    """
    if len(prices) < window:
        return None
    segment = prices[-window:]
    delta = segment[-1] - segment[0]
    threshold = segment[0] * 0.005  # 0.5% band = flat
    if delta > threshold:
        return "up"
    if delta < -threshold:
        return "down"
    return "flat"


def _normalized(price, min_p, max_p):
    """Min-max normalize price to 0–100 index."""
    if max_p == min_p:
        return 50.0
    return float((price - min_p) / (max_p - min_p) * 100)


# ---------------------------------------------------------------------------
# Core builders
# ---------------------------------------------------------------------------

def build_daily_metrics(rows):
    """
    Compute metrics for a sorted daily price series.

    `rows` is a list of dicts with keys: period (date), price_usd (Decimal).
    Returns list of metric dicts keyed to price_metrics_daily columns.
    """
    prices = [float(r["price_usd"]) for r in rows]
    dates = [r["period"] for r in rows]

    if not prices:
        return []

    min_p = min(prices)
    max_p = max(prices)
    results = []

    for i, (dt, price) in enumerate(zip(dates, prices)):
        slice_prices = prices[: i + 1]

        # Previous-day index
        p_1d = prices[i - 1] if i >= 1 else None
        # Price 7 days back in the series (not necessarily calendar -7)
        p_7d = prices[i - 7] if i >= 7 else None
        # Price 30 days back in the series
        p_30d = prices[i - 30] if i >= 30 else None

        results.append({
            "metric_date":    dt,
            "frequency":      "daily",
            "price":          price,
            "change_1d":      _pct_change(price, p_1d),
            "change_7d":      _pct_change(price, p_7d),
            "change_30d":     _pct_change(price, p_30d),
            "ma7":            _ma(slice_prices, 7),
            "ma30":           _ma(slice_prices, 30),
            "volatility_7d":  _stddev(slice_prices, 7),
            "volatility_30d": _stddev(slice_prices, 30),
            "normalized_idx": _normalized(price, min_p, max_p),
            "trend_direction": _trend(slice_prices),
        })

    return results


def build_monthly_metrics(rows):
    """
    Compute metrics for a sorted monthly price series.

    Only change_30d (1-month delta), MA7, MA30 (where data allows),
    and normalized_idx/trend. No 1d/7d changes, no volatility.
    """
    prices = [float(r["price_usd"]) for r in rows]
    dates = [r["period"] for r in rows]

    if not prices:
        return []

    min_p = min(prices)
    max_p = max(prices)
    results = []

    for i, (dt, price) in enumerate(zip(dates, prices)):
        slice_prices = prices[: i + 1]

        # For monthly: "30d change" means previous month's price
        p_prev = prices[i - 1] if i >= 1 else None

        results.append({
            "metric_date":    dt,
            "frequency":      "monthly",
            "price":          price,
            "change_1d":      None,   # not applicable for monthly
            "change_7d":      None,   # not applicable for monthly
            "change_30d":     _pct_change(price, p_prev),
            "ma7":            _ma(slice_prices, 7),
            "ma30":           _ma(slice_prices, 30),
            "volatility_7d":  None,   # not applicable for monthly
            "volatility_30d": None,   # not applicable for monthly
            "normalized_idx": _normalized(price, min_p, max_p),
            "trend_direction": _trend(slice_prices),
        })

    return results


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

UPSERT_SQL = """
INSERT INTO price_metrics_daily
    (material, metric_date, frequency, price,
     change_1d, change_7d, change_30d,
     ma7, ma30, volatility_7d, volatility_30d,
     normalized_idx, trend_direction)
VALUES
    (%(material)s, %(metric_date)s, %(frequency)s, %(price)s,
     %(change_1d)s, %(change_7d)s, %(change_30d)s,
     %(ma7)s, %(ma30)s, %(volatility_7d)s, %(volatility_30d)s,
     %(normalized_idx)s, %(trend_direction)s)
ON CONFLICT (material, metric_date, frequency) DO UPDATE SET
    price           = EXCLUDED.price,
    change_1d       = EXCLUDED.change_1d,
    change_7d       = EXCLUDED.change_7d,
    change_30d      = EXCLUDED.change_30d,
    ma7             = EXCLUDED.ma7,
    ma30            = EXCLUDED.ma30,
    volatility_7d   = EXCLUDED.volatility_7d,
    volatility_30d  = EXCLUDED.volatility_30d,
    normalized_idx  = EXCLUDED.normalized_idx,
    trend_direction = EXCLUDED.trend_direction
"""


def upsert_metrics(conn, material, metric_rows):
    """Upsert all metric rows for one material."""
    records = [{"material": material, **m} for m in metric_rows]
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, UPSERT_SQL, records, page_size=200)
    conn.commit()
    return len(records)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build price_metrics_daily from price_signals")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute metrics but do not write to DB")
    args = parser.parse_args()

    conn = get_connection()

    # ── Load source frequency map ──────────────────────────────────────────
    source_freq = {
        r["source_name"]: r["frequency"]
        for r in _fetch(conn, "SELECT source_name, frequency FROM dim_price_source")
    }
    # Any source not registered in dim_price_source defaults to 'daily'
    log.info("Loaded %d source definitions", len(source_freq))

    # ── Load all price_signals, ordered per material + date ───────────────
    raw = _fetch(conn, """
        SELECT material, source, period, price_usd
        FROM price_signals
        WHERE price_usd IS NOT NULL
        ORDER BY material, period
    """)
    log.info("Loaded %d price_signals rows", len(raw))

    # Group by (material, frequency)
    groups: dict[tuple, list] = {}
    for row in raw:
        freq = source_freq.get(row["source"], "daily")
        key = (row["material"], freq)
        groups.setdefault(key, []).append(row)

    # ── Dual-source validation ─────────────────────────────────────────────
    by_material: dict[str, set] = {}
    for (material, freq) in groups:
        by_material.setdefault(material, set()).add(freq)

    dual_source_materials = [m for m, freqs in by_material.items() if len(freqs) > 1]
    if dual_source_materials:
        for m in sorted(dual_source_materials):
            freqs = sorted(by_material[m])
            log.warning("DUAL SOURCE: %s — do not mix in signals (frequencies: %s)",
                        m, ", ".join(freqs))
    else:
        log.info("Dual-source check: OK — no material spans multiple frequencies")

    # ── Compute and upsert ────────────────────────────────────────────────
    daily_materials = set()
    monthly_materials = set()
    daily_total = 0
    monthly_total = 0

    for (material, freq), rows in sorted(groups.items()):
        if freq == "daily":
            metric_rows = build_daily_metrics(rows)
            daily_materials.add(material)
            daily_total += len(metric_rows)
        else:
            metric_rows = build_monthly_metrics(rows)
            monthly_materials.add(material)
            monthly_total += len(metric_rows)

        if args.dry_run:
            log.info("  [DRY-RUN] %s (%s): %d metric rows computed",
                     material, freq, len(metric_rows))
        else:
            n = upsert_metrics(conn, material, metric_rows)
            log.info("  %s (%s): %d rows upserted", material, freq, n)

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    print("─" * 60)
    print("  PRICE METRICS BUILD SUMMARY")
    print("─" * 60)
    mode = " [DRY-RUN]" if args.dry_run else ""
    print(f"  Daily series  : {len(daily_materials):>3} materials, {daily_total:>5} rows{mode}")
    print(f"  Monthly series: {len(monthly_materials):>3} materials, {monthly_total:>5} rows{mode}")
    print(f"  Total         : {len(daily_materials)+len(monthly_materials):>3} materials, "
          f"{daily_total+monthly_total:>5} rows{mode}")
    if dual_source_materials:
        print(f"\n  WARNING — {len(dual_source_materials)} dual-source material(s):")
        for m in sorted(dual_source_materials):
            print(f"    • {m}")
    print("─" * 60)

    conn.close()


if __name__ == "__main__":
    main()
