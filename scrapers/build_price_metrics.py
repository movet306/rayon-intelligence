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
  MIN_POINTS_MOMENTUM   = 14   need 14 points for acceleration component

Confidence levels (based on total series length per material):
  high    >= 30 pts — all metrics enabled
  medium  >= 14 pts — change_7d/MA7/volatility, no 30d metrics
  low     >=  7 pts — limited 7d metrics
  minimal <   7 pts — price and normalized_idx only

Confidence tiers (A–E, based on data density and recency):
  A: >= 60 pts AND last update <= 3 days ago
  B: >= 30 pts AND last update <= 5 days ago
  C: >= 14 pts AND last update <= 7 days ago
  D: >= 7  pts AND last update <= 10 days ago
  E: everything else

Validation:
  If a material exists in BOTH daily and monthly price_signals, emit a warning:
  "DUAL SOURCE: {material} — do not mix in signals"

Usage:
    python scrapers/build_price_metrics.py           # build all
    python scrapers/build_price_metrics.py --dry-run # compute only, no upsert
"""

import argparse
import logging
import math
import os
from datetime import date, timedelta

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exchange rate helper
# ---------------------------------------------------------------------------

def get_rmb_usd_rate() -> float:
    """
    Fetch live CNY→USD rate from frankfurter.app (no API key required).
    Falls back to 0.138 if the request fails.
    """
    try:
        resp = requests.get(
            "https://api.frankfurter.app/latest?from=CNY&to=USD",
            timeout=5,
        )
        rate = resp.json()["rates"]["USD"]
        log.info("Live CNY/USD rate: %.6f", rate)
        return float(rate)
    except Exception as exc:
        log.warning("Could not fetch live CNY/USD rate (%s) — using fallback 0.138", exc)
        return 0.138


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
MIN_POINTS_MOMENTUM   = 14

# ---------------------------------------------------------------------------
# Chain definitions (Etap 1B)
# ---------------------------------------------------------------------------

# downstream → upstream (for divergence score)
CHAIN_PAIRS = {
    'polyester_fdy':   'pta',
    'polyester_poy':   'pta',
    'polyester_dty':   'polyester_poy',
    'polyester_yarn':  'polyester_dty',
    'polyamide_fdy':   'pa6_chip',
    'cotton_yarn':     'cotton_lint',   # sunsirs china spot chain
}

# (chain_name, upstream_slug, downstream_slug) for price_chain_spreads
CHAIN_SPREADS = [
    ('polyester', 'pta',             'polyester_fdy'),
    ('polyester', 'pta',             'polyester_poy'),
    ('polyester', 'polyester_poy',   'polyester_dty'),
    ('polyester', 'polyester_fdy',   'polyester_yarn'),
    ('nylon',     'pa6_chip',        'polyamide_fdy'),
    ('nylon',     'pa66_chip',       'polyamide_fdy'),
    ('cotton',    'cotton_lint',     'cotton_yarn'),     # sunsirs china spot chain
    ('polyester', 'pta',             'polyester_staple_fiber'),
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_connection():
    return psycopg2.connect(os.environ["RAYON_DATABASE_URL"])


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


def _price_at_offset(prev_dates, prev_prices, ref_dt, days_back, window_days):
    """
    Return the price closest to (ref_dt - days_back) within ±window_days.
    Only searches prev_dates/prev_prices (i.e., rows strictly before ref_dt).
    Returns None if no row falls within the window.
    """
    target = ref_dt - timedelta(days=days_back)
    best_price, best_delta = None, float("inf")
    for d, p in zip(prev_dates, prev_prices):
        delta = abs((d - target).days)
        if delta <= window_days and delta < best_delta:
            best_price, best_delta = p, delta
    return best_price


# ---------------------------------------------------------------------------
# SECTION 1 — Confidence Tier
# ---------------------------------------------------------------------------

def calculate_confidence_tier(data_points: int, days_since_last: int, has_gaps: bool) -> str:
    """
    Return confidence tier A–E based on data density and recency.
    has_gaps is available for future refinement but tiers are currently
    determined by data_points and days_since_last alone.
    """
    if data_points >= 60 and days_since_last <= 3:
        return 'A'
    if data_points >= 30 and days_since_last <= 5:
        return 'B'
    if data_points >= 14 and days_since_last <= 7:
        return 'C'
    if data_points >= 7  and days_since_last <= 10:
        return 'D'
    return 'E'


# ---------------------------------------------------------------------------
# SECTION 2 — Momentum score
# ---------------------------------------------------------------------------

def calculate_momentum(change_1d, change_7d, prev_7d) -> float | None:
    """
    Composite momentum score in [-1, +1] using tanh normalisation.
    Requires change_1d and change_7d; prev_7d may be None (acceleration → 0).
    Returns None if fewer than MIN_POINTS_MOMENTUM data points available
    (caller is responsible for that gate).
    """
    if change_1d is None or change_7d is None or prev_7d is None:
        return None

    acceleration = change_7d - prev_7d

    norm = lambda x, scale: math.tanh(x / scale)
    score = (
        norm(change_1d,    3) * 0.3 +
        norm(change_7d,    5) * 0.5 +
        norm(acceleration, 3) * 0.2
    )
    return round(score, 4)


# ---------------------------------------------------------------------------
# Core builders
# ---------------------------------------------------------------------------

def build_daily_metrics(rows, rmb_usd_rate: float = 0.138):
    """
    Compute threshold-enforced metrics for a sorted daily price series.

    `rows`         — list of dicts with keys: period, price_usd (RMB/ton from SunSirs).
    `rmb_usd_rate` — live CNY→USD conversion rate.
    Returns list of metric dicts ready for upsert.

    For each row, data_points = i+1 (accumulates through the series).
    The latest row therefore carries data_points = len(rows).
    Metrics are set to NULL when data_points < the required minimum.

    Changes use date-based lookback (not index-based) so sparse Wayback
    Machine series do not produce spurious multi-month "7-day" changes.
    """
    prices = [float(r["price_usd"]) for r in rows]   # RMB/ton
    dates  = [r["period"] for r in rows]

    if not prices:
        return []

    min_p = min(prices)
    max_p = max(prices)
    today = date.today()
    results = []

    for i, (dt, price) in enumerate(zip(dates, prices)):
        n            = i + 1          # data points available at this row
        slice_prices = prices[:n]
        conf         = _confidence_level(n)
        prev_dates   = dates[:i]
        prev_prices  = prices[:i]

        # ── Changes: date-based lookback with ±window tolerance ───────────
        change_1d  = (
            _pct_change(price, _price_at_offset(prev_dates, prev_prices, dt, 1,  2))
            if n >= MIN_POINTS_CHANGE_1D else None
        )
        change_7d  = (
            _pct_change(price, _price_at_offset(prev_dates, prev_prices, dt, 7,  2))
            if n >= MIN_POINTS_CHANGE_7D else None
        )
        change_30d = (
            _pct_change(price, _price_at_offset(prev_dates, prev_prices, dt, 30, 3))
            if n >= MIN_POINTS_CHANGE_30D else None
        )

        # ── Moving averages ────────────────────────────────────────────────
        ma7  = _ma(slice_prices, 7)  if n >= MIN_POINTS_MA7  else None
        ma30 = _ma(slice_prices, 30) if n >= MIN_POINTS_MA30 else None

        # ── Volatility ─────────────────────────────────────────────────────
        vol_7d  = _stddev(slice_prices, 7)  if n >= MIN_POINTS_VOLATILITY else None
        vol_30d = _stddev(slice_prices, 30) if n >= 30                    else None

        # ── Trend (requires strong data foundation) ────────────────────────
        trend = _trend(slice_prices) if n >= MIN_POINTS_TREND else None

        # ── SECTION 1: Confidence Tier ─────────────────────────────────────
        days_since_last = (dt - dates[i - 1]).days if i > 0 else 0
        recent_start    = dt - timedelta(days=7)
        pts_in_7d       = sum(1 for d in dates[:i + 1] if d >= recent_start)
        has_gaps        = pts_in_7d < 3
        confidence_tier = calculate_confidence_tier(n, days_since_last, has_gaps)

        # ── SECTION 2: Momentum score ──────────────────────────────────────
        momentum_score = None
        if n >= MIN_POINTS_MOMENTUM:
            price_7d_ago  = _price_at_offset(prev_dates, prev_prices, dt, 7,  2)
            price_14d_ago = _price_at_offset(prev_dates, prev_prices, dt, 14, 2)
            prev_7d       = _pct_change(price_7d_ago, price_14d_ago)
            momentum_score = calculate_momentum(change_1d, change_7d, prev_7d)

        results.append({
            "metric_date":      dt,
            "frequency":        "daily",
            "price":            price,
            "price_usd":        round(price * rmb_usd_rate, 4),
            "change_1d":        change_1d,
            "change_7d":        change_7d,
            "change_30d":       change_30d,
            "ma7":              ma7,
            "ma30":             ma30,
            "volatility_7d":    vol_7d,
            "volatility_30d":   vol_30d,
            "normalized_idx":   _normalized(price, min_p, max_p),
            "trend_direction":  trend,
            "data_points":      n,
            "confidence_level": conf,
            # new v2 fields
            "momentum_score":   momentum_score,
            "divergence_score": None,     # filled by compute_divergence_scores()
            "confidence_tier":  confidence_tier,
        })

    return results


def build_monthly_metrics(rows, rmb_usd_rate: float = 0.138):
    """
    Compute metrics for a sorted monthly price series.

    Monthly series: only change_30d (prev-month delta), MA7/MA30 where data
    allows, normalized_idx, trend. No 1d/7d changes, no volatility.
    New v2 fields (momentum, divergence, confidence_tier) are daily-only.
    """
    prices = [float(r["price_usd"]) for r in rows]   # RMB/ton
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
            "metric_date":      dt,
            "frequency":        "monthly",
            "price":            price,
            "price_usd":        round(price * rmb_usd_rate, 4),
            "change_1d":        None,
            "change_7d":        None,
            "change_30d":       _pct_change(price, prices[i - 1]) if n >= 2 else None,
            "ma7":              _ma(slice_prices, 7)  if n >= MIN_POINTS_MA7  else None,
            "ma30":             _ma(slice_prices, 30) if n >= MIN_POINTS_MA30 else None,
            "volatility_7d":    None,
            "volatility_30d":   None,
            "normalized_idx":   _normalized(price, min_p, max_p),
            "trend_direction":  _trend(slice_prices) if n >= MIN_POINTS_TREND else None,
            "data_points":      n,
            "confidence_level": conf,
            # new v2 fields — not applicable for monthly
            "momentum_score":   None,
            "divergence_score": None,
            "confidence_tier":  None,
        })

    return results


# ---------------------------------------------------------------------------
# SECTION 4 — Upsert (including new v2 fields)
# ---------------------------------------------------------------------------

UPSERT_SQL = """
INSERT INTO price_metrics_daily
    (material, metric_date, frequency, price, price_usd,
     change_1d, change_7d, change_30d,
     ma7, ma30, volatility_7d, volatility_30d,
     normalized_idx, trend_direction,
     data_points, confidence_level,
     momentum_score, divergence_score, confidence_tier)
VALUES
    (%(material)s, %(metric_date)s, %(frequency)s, %(price)s, %(price_usd)s,
     %(change_1d)s, %(change_7d)s, %(change_30d)s,
     %(ma7)s, %(ma30)s, %(volatility_7d)s, %(volatility_30d)s,
     %(normalized_idx)s, %(trend_direction)s,
     %(data_points)s, %(confidence_level)s,
     %(momentum_score)s, %(divergence_score)s, %(confidence_tier)s)
ON CONFLICT (material, metric_date, frequency) DO UPDATE SET
    price            = EXCLUDED.price,
    price_usd        = EXCLUDED.price_usd,
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
    confidence_level = EXCLUDED.confidence_level,
    momentum_score   = EXCLUDED.momentum_score,
    divergence_score = EXCLUDED.divergence_score,
    confidence_tier  = EXCLUDED.confidence_tier
"""


def upsert_metrics(conn, material, metric_rows):
    records = [{"material": material, **m} for m in metric_rows]
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, UPSERT_SQL, records, page_size=200)
    conn.commit()
    return len(records)


# ---------------------------------------------------------------------------
# SECTION 3 — Divergence scores (post-upsert pass)
# ---------------------------------------------------------------------------

def compute_divergence_scores(conn, dry_run=False) -> list:
    """
    For each downstream material in CHAIN_PAIRS, compute:
        divergence_score = upstream_change_7d - downstream_change_7d
    Positive = upstream rising faster (cost pressure building upstream).
    Negative = downstream rising faster (pass-through happening).
    Updates price_metrics_daily in-place.
    """
    all_slugs = list(set(CHAIN_PAIRS.keys()) | set(CHAIN_PAIRS.values()))
    rows = _fetch(conn, """
        SELECT material, metric_date, change_7d
        FROM price_metrics_daily
        WHERE frequency = 'daily' AND material = ANY(%s)
        ORDER BY material, metric_date
    """, [all_slugs])

    by_mat: dict[str, dict] = {}
    for r in rows:
        by_mat.setdefault(r["material"], {})[r["metric_date"]] = r["change_7d"]

    updates = []
    for downstream, upstream in CHAIN_PAIRS.items():
        dn_map = by_mat.get(downstream, {})
        up_map = by_mat.get(upstream, {})
        for dt, dn_c7d in dn_map.items():
            up_c7d = up_map.get(dt)
            if dn_c7d is not None and up_c7d is not None:
                updates.append({
                    "material":        downstream,
                    "metric_date":     dt,
                    "divergence_score": round(float(up_c7d) - float(dn_c7d), 4),
                })

    if not dry_run and updates:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, """
                UPDATE price_metrics_daily
                SET divergence_score = %(divergence_score)s
                WHERE material = %(material)s
                  AND metric_date = %(metric_date)s
                  AND frequency = 'daily'
            """, updates, page_size=200)
        conn.commit()
        log.info("Divergence: updated %d rows across %d materials",
                 len(updates), len(CHAIN_PAIRS))

    return updates


# ---------------------------------------------------------------------------
# SECTION 5 — Chain spreads
# ---------------------------------------------------------------------------

def build_chain_spreads(conn, dry_run=False) -> tuple[int, int, dict]:
    """
    Compute price_chain_spreads for all CHAIN_SPREADS pairs.
    Returns (pairs_computed, dates_computed, signal_counts).
    """
    rows = _fetch(conn, """
        SELECT material, metric_date, price_usd
        FROM price_metrics_daily
        WHERE frequency = 'daily' AND price_usd IS NOT NULL
        ORDER BY material, metric_date
    """)

    by_material: dict[str, dict] = {}
    for r in rows:
        by_material.setdefault(r["material"], {})[r["metric_date"]] = float(r["price_usd"])

    spread_records = []
    signal_counts  = {"widening": 0, "tightening": 0, "stable": 0, "none": 0}
    pairs_computed = 0
    dates_computed = 0

    for (chain, upstream_slug, downstream_slug) in CHAIN_SPREADS:
        up_prices = by_material.get(upstream_slug, {})
        dn_prices = by_material.get(downstream_slug, {})

        common_dates = sorted(set(up_prices) & set(dn_prices))
        if not common_dates:
            log.info("  No common dates: %s → %s", upstream_slug, downstream_slug)
            continue

        pairs_computed += 1

        # Build full spread series first (needed for zscore lookback)
        spread_series = {d: dn_prices[d] - up_prices[d] for d in common_dates}
        spread_dates  = common_dates  # already sorted

        for idx, calc_date in enumerate(spread_dates):
            spread_usd = spread_series[calc_date]
            up_price   = up_prices[calc_date]
            spread_pct = round(spread_usd / up_price * 100, 4) if up_price != 0 else None

            # spread_7d_delta: compare with spread ~7 days ago (±2 day window)
            target_7d   = calc_date - timedelta(days=7)
            spread_7d_ago = None
            for back_d in reversed(spread_dates[:idx]):
                if abs((back_d - target_7d).days) <= 2:
                    spread_7d_ago = spread_series[back_d]
                    break
            spread_7d_delta = (
                round(spread_usd - spread_7d_ago, 4) if spread_7d_ago is not None else None
            )

            # zscore_30d over last 30 spread values
            zscore_30d = None
            if idx >= 29:
                window = [spread_series[d] for d in spread_dates[idx - 29: idx + 1]]
                mean30 = sum(window) / len(window)
                std30  = (sum((x - mean30) ** 2 for x in window) / len(window)) ** 0.5
                if std30 > 0:
                    zscore_30d = round((spread_usd - mean30) / std30, 4)

            # signal
            if zscore_30d is not None:
                if zscore_30d > 1.5:
                    signal = "widening"
                elif zscore_30d < -1.5:
                    signal = "tightening"
                else:
                    signal = "stable"
            else:
                signal = None

            spread_records.append({
                "calc_date":       calc_date,
                "chain":           chain,
                "upstream_slug":   upstream_slug,
                "downstream_slug": downstream_slug,
                "spread_usd":      round(spread_usd, 4),
                "spread_pct":      spread_pct,
                "spread_7d_delta": spread_7d_delta,
                "zscore_30d":      zscore_30d,
                "signal":          signal,
            })
            dates_computed += 1
            signal_counts[signal or "none"] += 1

    if not dry_run and spread_records:
        SPREAD_UPSERT = """
        INSERT INTO price_chain_spreads
            (calc_date, chain, upstream_slug, downstream_slug,
             spread_usd, spread_pct, spread_7d_delta, zscore_30d, signal)
        VALUES
            (%(calc_date)s, %(chain)s, %(upstream_slug)s, %(downstream_slug)s,
             %(spread_usd)s, %(spread_pct)s, %(spread_7d_delta)s, %(zscore_30d)s, %(signal)s)
        ON CONFLICT (calc_date, upstream_slug, downstream_slug) DO UPDATE SET
            spread_usd      = EXCLUDED.spread_usd,
            spread_pct      = EXCLUDED.spread_pct,
            spread_7d_delta = EXCLUDED.spread_7d_delta,
            zscore_30d      = EXCLUDED.zscore_30d,
            signal          = EXCLUDED.signal
        """
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, SPREAD_UPSERT, spread_records, page_size=200)
        conn.commit()
        log.info("Chain spreads: upserted %d records across %d pairs",
                 len(spread_records), pairs_computed)

    return pairs_computed, dates_computed, signal_counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build price_metrics_daily from price_signals")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute metrics but do not write to DB")
    args = parser.parse_args()

    conn = get_connection()

    # ── Fetch live exchange rate ───────────────────────────────────────────
    rmb_usd_rate = get_rmb_usd_rate()

    # ── Load source frequency map ──────────────────────────────────────────
    source_freq = {
        r["source_name"]: r["frequency"]
        for r in _fetch(conn, "SELECT source_name, frequency FROM dim_price_source")
    }
    log.info("Loaded %d source definitions", len(source_freq))

    # ── Load all price_signals ordered by material + date ─────────────────
    raw = _fetch(conn, """
        SELECT material, source, period, price_usd, unit
        FROM price_signals
        WHERE price_usd IS NOT NULL
        ORDER BY material, period
    """)
    log.info("Loaded %d price_signals rows", len(raw))

    # Group by (material, source, frequency) — keeps ice_cotton separate from sunsirs
    groups: dict[tuple, list] = {}
    for row in raw:
        freq = source_freq.get(row["source"], "daily")
        groups.setdefault((row["material"], row["source"], freq), []).append(row)

    # ── Dual-source validation ─────────────────────────────────────────────
    by_material: dict[str, set] = {}
    for (material, source, freq) in groups:
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

    USc_LB_TO_USD_TON = 0.01 * 2204.62  # 22.0462 USD/ton per USc/lb

    for (material, source, freq), rows in sorted(groups.items()):
        n_total    = len(rows)
        conf_total = _confidence_level(n_total)

        # Determine conversion factor from native unit to USD/ton
        first_unit = rows[0].get("unit") if rows else None
        if first_unit == "USc/lb":
            conversion_factor = USc_LB_TO_USD_TON
            unit_label = "USc/lb -> USD/ton"
        else:
            conversion_factor = rmb_usd_rate
            unit_label = "RMB/ton -> USD/ton"

        mat_key = f"{material}:{source}" if source != "sunsirs" else material

        if freq == "daily":
            metric_rows = build_daily_metrics(rows, conversion_factor)
            daily_mats.add(mat_key)
            daily_total += len(metric_rows)
        else:
            metric_rows = build_monthly_metrics(rows, conversion_factor)
            monthly_mats.add(mat_key)
            monthly_total += len(metric_rows)

        if args.dry_run:
            log.info("  [DRY-RUN] %s/%s (%s) [%s]: %d rows, confidence=%s",
                     material, source, freq, unit_label, n_total, conf_total)
        else:
            upsert_metrics(conn, material, metric_rows)
            log.info("  %s/%s (%s) [%s]: %d rows upserted, confidence=%s",
                     material, source, freq, unit_label, len(metric_rows), conf_total)

        # Capture latest-row stats for summary
        latest = metric_rows[-1] if metric_rows else {}
        mat_stats[mat_key] = {
            "n":               n_total,
            "conf":            conf_total,
            "freq":            freq,
            "confidence_tier": latest.get("confidence_tier"),
            "momentum":        latest.get("momentum_score"),
            "divergence":      None,  # filled after divergence pass
        }

    # ── SECTION 3: Divergence scores ──────────────────────────────────────
    if not args.dry_run:
        div_updates = compute_divergence_scores(conn, dry_run=False)
        # Update mat_stats with latest divergence per material
        div_latest: dict[str, float] = {}
        for u in div_updates:
            div_latest[u["material"]] = u["divergence_score"]
        for mat, div in div_latest.items():
            if mat in mat_stats:
                mat_stats[mat]["divergence"] = div
    else:
        log.info("  [DRY-RUN] skipping divergence score computation")

    # ── SECTION 5: Chain spreads ──────────────────────────────────────────
    if not args.dry_run:
        sp_pairs, sp_dates, sp_signals = build_chain_spreads(conn, dry_run=False)
    else:
        sp_pairs, sp_dates, sp_signals = 0, 0, {"widening": 0, "tightening": 0, "stable": 0, "none": 0}
        log.info("  [DRY-RUN] skipping chain spreads computation")

    # ── Per-material summary ───────────────────────────────────────────────
    SEP = "-" * 80
    print()
    print(SEP)
    print("  PER-MATERIAL SUMMARY")
    print(SEP)
    for mat in sorted(mat_stats):
        s = mat_stats[mat]
        metrics_lbl = _metrics_label(s["conf"])
        tier_str    = s["confidence_tier"] or "-"
        mom_str     = f"{s['momentum']:+.4f}" if s["momentum"] is not None else "-"
        div_str     = f"{s['divergence']:+.4f}" if s["divergence"] is not None else "-"
        print(f"  {mat:<35}: {s['n']:>3} pts  tier={tier_str}  "
              f"momentum={mom_str:>8}  divergence={div_str:>8}  [{metrics_lbl}]")
    print(SEP)

    # ── Aggregate summary ──────────────────────────────────────────────────
    mode = " [DRY-RUN]" if args.dry_run else ""
    print()
    print(SEP)
    print("  PRICE METRICS BUILD SUMMARY  (Etap 1B)")
    print(SEP)
    print(f"  CNY/USD rate     : {rmb_usd_rate:.6f} (live from frankfurter.app)")
    print(f"  Daily series     : {len(daily_mats):>3} materials, {daily_total:>5} rows{mode}")
    print(f"  Monthly series   : {len(monthly_mats):>3} materials, {monthly_total:>5} rows{mode}")
    print(f"  Total            : {len(daily_mats)+len(monthly_mats):>3} materials, "
          f"{daily_total+monthly_total:>5} rows{mode}")

    conf_counts: dict[str, int] = {}
    for s in mat_stats.values():
        conf_counts[s["conf"]] = conf_counts.get(s["conf"], 0) + 1
    print()
    print("  Confidence level breakdown:")
    for lvl in ("high", "medium", "low", "minimal"):
        n = conf_counts.get(lvl, 0)
        if n:
            print(f"    {lvl:<8}: {n} material(s)")

    tier_counts: dict[str, int] = {}
    for s in mat_stats.values():
        t = s["confidence_tier"] or "—"
        tier_counts[t] = tier_counts.get(t, 0) + 1
    print()
    print("  Confidence tier breakdown (A=best, E=worst):")
    for t in ("A", "B", "C", "D", "E", "-"):
        n = tier_counts.get(t, 0)
        if n:
            print(f"    Tier {t}   : {n} material(s)")

    print()
    print("  === Etap 1B Results ===")
    print(f"  Chain spreads    : {sp_pairs} pairs, {sp_dates} date-rows computed{mode}")
    print(f"  Spread signals   : widening={sp_signals.get('widening',0)}  "
          f"tightening={sp_signals.get('tightening',0)}  "
          f"stable={sp_signals.get('stable',0)}  "
          f"no-zscore={sp_signals.get('none',0)}")

    if dual:
        print(f"\n  WARNING — {len(dual)} dual-source material(s):")
        for m in sorted(dual):
            print(f"    • {m}")
    print(SEP)

    conn.close()


if __name__ == "__main__":
    main()
