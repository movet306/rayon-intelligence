"""
build_price_metrics.py — Frequency-aware price metrics builder.

Reads price_signals, groups by (material, frequency) separately, computes
derived metrics appropriate to each frequency, and upserts into
price_metrics_daily.

Threshold rules (daily series):
  Metrics are set to NULL if the data point count at that row is below
  the minimum required for a meaningful computation.

  MIN_POINTS_CHANGE_1D  = 2    need previous point
  MIN_POINTS_CHANGE_7D  = 7    need 7 lookback periods (i >= 7 → n >= 8)
  MIN_POINTS_CHANGE_30D = 30   need 30 lookback periods (i >= 30 → n >= 31)
  MIN_POINTS_MA7        = 7    need 7 points for rolling average
  MIN_POINTS_MA30       = 30   need 30 points for rolling average
  MIN_POINTS_VOLATILITY = 7    need 7 points for std dev
  MIN_POINTS_TREND      = 30   need 30 points for meaningful trend signal

Confidence levels (based on total series length per material):
  high    >= 30 pts — all metrics enabled
  medium  >= 14 pts — change_7d/MA7/volatility, no 30d metrics
  low     >=  7 pts — limited 7d metrics
  minimal <   7 pts — price and normalized_idx only

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
# Threshold constants
# ---------------------------------------------------------------------------

MIN_POINTS_CHANGE_1D  = 2
MIN_POINTS_CHANGE_7D  = 7   # enforced as i >= 7 (n >= 8) for safe index access
MIN_POINTS_CHANGE_30D = 30  # enforced as i >= 30 (n >= 31) for safe index access
MIN_POINTS_MA7        = 7
MIN_POINTS_MA30       = 30
MIN_POINTS_VOLATILITY = 7
MIN_POINTS_TREND      = 30

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
# Confidence and metric helpers
# ---------------------------------------------------------------------------

def _confidence_level(n: int) -> str:
    if n >= 30: return "high"
    if n >= 14: return "medium"
    if n >= 7:  return "low"
    return "minimal"


def _metrics_label(conf: str) -> str:
    if conf == "high":    return "all"
    if conf == "medium":  return "partial (no 30d metrics)"
    if conf == "low":     return "limited (7d only)"
    return "price only"


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
    Directional trend over the last `window` points.
    Returns 'up', 'down', or 'flat'.
    Call-site is responsible for enforcing MIN_POINTS_TREND before calling.
    """
    if len(prices) < window:
        return None
    segment = prices[-window:]
    delta = segment[-1] - segment[0]
    threshold = segment[0] * 0.005  # 0.5% deadband = flat
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
    Compute threshold-enforced metrics for a sorted daily price series.

    `rows` — list of dicts with keys: period, price_usd.
    Returns list of metric dicts ready for upsert.

    For each row, data_points = i+1 (accumulates through the series).
    The latest row therefore carries data_points = len(rows).
    Metrics are set to NULL when data_points < the required minimum.
    """
    prices = [float(r["price_usd"]) for r in rows]
    dates  = [r["period"] for r in rows]

    if not prices:
        return []

    min_p = min(prices)
    max_p = max(prices)
    results = []

    for i, (dt, price) in enumerate(zip(dates, prices)):
        n            = i + 1          # data points available at this row
        slice_prices = prices[:n]
        conf         = _confidence_level(n)

        # ── Changes: use index-safe lookback guards ────────────────────────
        change_1d  = (_pct_change(price, prices[i - 1])  if n >= MIN_POINTS_CHANGE_1D
                      else None)
        change_7d  = (_pct_change(price, prices[i - 7])  if i >= MIN_POINTS_CHANGE_7D
                      else None)   # i>=7 → n>=8, safe to access prices[i-7]
        change_30d = (_pct_change(price, prices[i - 30]) if i >= MIN_POINTS_CHANGE_30D
                      else None)   # i>=30 → n>=31, safe to access prices[i-30]

        # ── Moving averages ────────────────────────────────────────────────
        ma7  = _ma(slice_prices, 7)  if n >= MIN_POINTS_MA7  else None
        ma30 = _ma(slice_prices, 30) if n >= MIN_POINTS_MA30 else None

        # ── Volatility ─────────────────────────────────────────────────────
        vol_7d  = _stddev(slice_prices, 7)  if n >= MIN_POINTS_VOLATILITY else None
        vol_30d = _stddev(slice_prices, 30) if n >= 30                    else None

        # ── Trend (requires strong data foundation) ────────────────────────
        trend = _trend(slice_prices) if n >= MIN_POINTS_TREND else None

        results.append({
            "metric_date":     dt,
            "frequency":       "daily",
            "price":           price,
            "change_1d":       change_1d,
            "change_7d":       change_7d,
            "change_30d":      change_30d,
            "ma7":             ma7,
            "ma30":            ma30,
            "volatility_7d":   vol_7d,
            "volatility_30d":  vol_30d,
            "normalized_idx":  _normalized(price, min_p, max_p),
            "trend_direction": trend,
            "data_points":     n,
            "confidence_level": conf,
        })

    return results


def build_monthly_metrics(rows):
    """
    Compute metrics for a sorted monthly price series.

    Monthly series: only change_30d (prev-month delta), MA7/MA30 where data
    allows, normalized_idx, trend. No 1d/7d changes, no volatility.
    """
    prices = [float(r["price_usd"]) for r in rows]
    dates  = [r["period"] for r in rows]

    if not prices:
        return []

    min_p = min(prices)
    max_p = max(prices)
    results = []

    for i, (dt, price) in enumerate(zip(dates, prices)):
        n            = i + 1
        slice_prices = prices[:n]
        conf         = _confidence_level(n)

        results.append({
            "metric_date":     dt,
            "frequency":       "monthly",
            "price":           price,
            "change_1d":       None,   # not applicable for monthly
            "change_7d":       None,   # not applicable for monthly
            "change_30d":      _pct_change(price, prices[i - 1]) if n >= 2 else None,
            "ma7":             _ma(slice_prices, 7)  if n >= MIN_POINTS_MA7  else None,
            "ma30":            _ma(slice_prices, 30) if n >= MIN_POINTS_MA30 else None,
            "volatility_7d":   None,   # not applicable for monthly
            "volatility_30d":  None,   # not applicable for monthly
            "normalized_idx":  _normalized(price, min_p, max_p),
            "trend_direction": _trend(slice_prices) if n >= MIN_POINTS_TREND else None,
            "data_points":     n,
            "confidence_level": conf,
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
     normalized_idx, trend_direction,
     data_points, confidence_level)
VALUES
    (%(material)s, %(metric_date)s, %(frequency)s, %(price)s,
     %(change_1d)s, %(change_7d)s, %(change_30d)s,
     %(ma7)s, %(ma30)s, %(volatility_7d)s, %(volatility_30d)s,
     %(normalized_idx)s, %(trend_direction)s,
     %(data_points)s, %(confidence_level)s)
ON CONFLICT (material, metric_date, frequency) DO UPDATE SET
    price            = EXCLUDED.price,
    change_1d        = EXCLUDED.change_1d,
    change_7d        = EXCLUDED.change_7d,
    change_30d       = EXCLUDED.change_30d,
    ma7              = EXCLUDED.ma7,
    ma30             = EXCLUDED.ma30,
    volatility_7d    = EXCLUDED.volatility_7d,
    volatility_30d   = EXCLUDED.volatility_30d,
    normalized_idx   = EXCLUDED.normalized_idx,
    trend_direction  = EXCLUDED.trend_direction,
    data_points      = EXCLUDED.data_points,
    confidence_level = EXCLUDED.confidence_level
"""


def upsert_metrics(conn, material, metric_rows):
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
    log.info("Loaded %d source definitions", len(source_freq))

    # ── Load all price_signals ordered by material + date ─────────────────
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
        groups.setdefault((row["material"], freq), []).append(row)

    # ── Dual-source validation ─────────────────────────────────────────────
    by_material: dict[str, set] = {}
    for (material, freq) in groups:
        by_material.setdefault(material, set()).add(freq)

    dual = [m for m, freqs in by_material.items() if len(freqs) > 1]
    if dual:
        for m in sorted(dual):
            log.warning("DUAL SOURCE: %s — do not mix in signals (%s)",
                        m, ", ".join(sorted(by_material[m])))
    else:
        log.info("Dual-source check: OK — no material spans multiple frequencies")

    # ── Compute, upsert, collect stats ────────────────────────────────────
    daily_mats    = set()
    monthly_mats  = set()
    daily_total   = 0
    monthly_total = 0
    mat_stats: dict[str, dict] = {}

    for (material, freq), rows in sorted(groups.items()):
        n_total    = len(rows)
        conf_total = _confidence_level(n_total)

        if freq == "daily":
            metric_rows = build_daily_metrics(rows)
            daily_mats.add(material)
            daily_total += len(metric_rows)
        else:
            metric_rows = build_monthly_metrics(rows)
            monthly_mats.add(material)
            monthly_total += len(metric_rows)

        if args.dry_run:
            log.info("  [DRY-RUN] %s (%s): %d rows, confidence=%s",
                     material, freq, n_total, conf_total)
        else:
            upsert_metrics(conn, material, metric_rows)
            log.info("  %s (%s): %d rows upserted, confidence=%s",
                     material, freq, len(metric_rows), conf_total)

        mat_stats[material] = {
            "n": n_total, "conf": conf_total, "freq": freq,
        }

    # ── Per-material summary ───────────────────────────────────────────────
    print()
    SEP = "─" * 75
    print(SEP)
    print("  PER-MATERIAL SUMMARY")
    print(SEP)
    for mat in sorted(mat_stats):
        s = mat_stats[mat]
        metrics_lbl = _metrics_label(s["conf"])
        print(f"  {mat:<35}: {s['n']:>3} points, "
              f"confidence={s['conf']:<8}, metrics: {metrics_lbl}")
    print(SEP)

    # ── Aggregate summary ──────────────────────────────────────────────────
    mode = " [DRY-RUN]" if args.dry_run else ""
    print()
    print(SEP)
    print("  PRICE METRICS BUILD SUMMARY")
    print(SEP)
    print(f"  Daily series  : {len(daily_mats):>3} materials, {daily_total:>5} rows{mode}")
    print(f"  Monthly series: {len(monthly_mats):>3} materials, {monthly_total:>5} rows{mode}")
    print(f"  Total         : {len(daily_mats)+len(monthly_mats):>3} materials, "
          f"{daily_total+monthly_total:>5} rows{mode}")

    conf_counts = {}
    for s in mat_stats.values():
        conf_counts[s["conf"]] = conf_counts.get(s["conf"], 0) + 1
    print()
    print("  Confidence breakdown:")
    for lvl in ("high", "medium", "low", "minimal"):
        n = conf_counts.get(lvl, 0)
        if n:
            print(f"    {lvl:<8}: {n} material(s)")
    if dual:
        print(f"\n  WARNING — {len(dual)} dual-source material(s):")
        for m in sorted(dual):
            print(f"    • {m}")
    print(SEP)

    conn.close()


if __name__ == "__main__":
    main()
