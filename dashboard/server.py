"""
dashboard/server.py — Rayon Intelligence FastAPI backend

Run:
    uvicorn dashboard.server:app --port 8000 --reload
"""

import os
import threading as _threading
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import psycopg2
from psycopg2.pool import ThreadedConnectionPool
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

DB_URL = os.environ.get("DATABASE_URL", "")
STATIC_DIR = Path(__file__).parent / "static"

# ── Live CNY/USD rate with 1-hour in-process cache ───────────────────────────
_rate_cache: dict = {"rate": None, "date": None, "fetched_at": None}
_RATE_FALLBACK = float(os.getenv("RMB_USD_RATE", "0.138"))


def get_rmb_usd_rate() -> tuple[float, str | None]:
    """Return (rate, rate_date). Refreshes at most once per hour."""
    import logging
    log = logging.getLogger(__name__)
    now = datetime.now(timezone.utc)
    cached = _rate_cache
    if cached["fetched_at"] and (now - cached["fetched_at"]).total_seconds() < 3600:
        return cached["rate"], cached["date"]
    try:
        resp = requests.get(
            "https://api.frankfurter.app/latest?from=CNY&to=USD",
            timeout=5,
        )
        data = resp.json()
        rate = float(data["rates"]["USD"])
        date_str = data.get("date")
        _rate_cache.update({"rate": rate, "date": date_str, "fetched_at": now})
        return rate, date_str
    except Exception as exc:
        log.warning("Could not fetch live CNY/USD rate (%s) — using fallback %.4f", exc, _RATE_FALLBACK)
        _rate_cache.update({"rate": _RATE_FALLBACK, "date": None, "fetched_at": now})
        return _RATE_FALLBACK, None

# Turkish display labels for auto-signal texts
MATERIAL_LABELS = {
    "polyester_staple_fiber": "PSF (Polyester Elyaf)",
    "polyester_fdy":          "Polyester FDY",
    "polyester_poy":          "Polyester POY",
    "polyester_dty":          "Polyester DTY",
    "polyester_yarn":         "Polyester İplik",
    "pta":                    "PTA",
    "cotton_lint":            "Pamuk (Ham)",
    "cotton_yarn":            "Pamuk İpliği",
    "polyamide_fdy":          "Naylon FDY (PA6)",
    "pa6_chip":               "PA6 Chip",
    "pa66_chip":              "PA66 Chip",
    "rayon_yarn":             "Rayon İpliği",
    "adipic_acid":            "Adipik Asit",
}

app = FastAPI(title="Rayon Intelligence API", docs_url="/api/docs")


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    path = str(request.url.path)
    if path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# === Connection pool (M2.2.6) ===
# Pool is initialized lazily on first request to avoid blocking module import
# if Railway is briefly unreachable. minconn=1 keeps the warm connection alive,
# maxconn=8 covers the burst of concurrent requests during a detail-drawer fetch.
_pool: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(minconn=1, maxconn=8, dsn=DB_URL)
    return _pool


class _PooledConn:
    """Context manager that borrows a connection from the pool and returns it.

    On exception inside the `with` block we still return the connection to
    the pool but mark it for rollback so a poisoned transaction does not
    leak to the next caller.
    """

    def __init__(self) -> None:
        self.pool = _get_pool()
        self.conn = None

    def __enter__(self):
        self.conn = self.pool.getconn()
        # M2.2.6b: autocommit avoids implicit BEGIN/COMMIT round-trip per query.
        # The dashboard is read-only, so per-statement autocommit is safe and
        # eliminates ~700ms per query against Railway's high-latency network.
        if not self.conn.autocommit:
            self.conn.autocommit = True
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if self.conn is None:
            return
        # In autocommit mode there is no open transaction to commit or roll
        # back. We just return the connection to the pool.
        self.pool.putconn(self.conn)
        self.conn = None


def _conn():
    return _PooledConn()


@app.on_event("shutdown")
def _close_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
        except Exception:
            pass
        _pool = None


# === Thread-local connection sharing (M2.2.6c) ===
# Endpoints that issue many queries can borrow a single pool connection at
# entry and bind it to a thread-local. _rows() then reuses that connection
# for the duration of the request, avoiding pool getconn/putconn overhead
# per query (~200ms each against Railway US-West).
_request_conn = _threading.local()


def _begin_shared_conn():
    """Borrow a pool connection and bind it to thread-local. Returns the
    holder so the caller can release it with _end_shared_conn()."""
    holder = _PooledConn()
    conn = holder.__enter__()
    _request_conn.conn = conn
    return holder


def _end_shared_conn(holder, exc_type=None, exc=None, tb=None):
    """Release a connection borrowed by _begin_shared_conn()."""
    _request_conn.conn = None
    if holder is not None:
        holder.__exit__(exc_type, exc, tb)


def with_shared_conn(fn):
    """Decorator: borrow one pooled connection for the whole endpoint.

    Use on endpoints that issue many sequential queries (e.g. counterparty_detail
    with 11 queries). The body is unchanged — _rows() automatically reuses the
    bound connection via thread-local.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        holder = _begin_shared_conn()
        try:
            return fn(*args, **kwargs)
        finally:
            _end_shared_conn(holder)
    return wrapper


def _rows(sql: str, params=None) -> list[dict]:
    # M2.2.6c — if an endpoint has bound a shared connection via
    # _begin_shared_conn() (typically through the @with_shared_conn decorator),
    # reuse it for this query. This avoids pool getconn/putconn round-trip
    # per call (~200ms each against Railway US-West).
    shared = getattr(_request_conn, "conn", None)
    if shared is not None:
        with shared.cursor() as cur:
            cur.execute(sql, params or [])
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _one(sql: str, params=None):
    rows = _rows(sql, params)
    return rows[0] if rows else {}


# ── /api/stats ─────────────────────────────────────────────────────────────────

@app.get("/api/stats")
def stats():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    signal_count = _one(
        "SELECT COUNT(*)::int AS n FROM market_signals WHERE detected_at >= %s",
        [cutoff],
    ).get("n", 0)

    competitor_count = _one(
        "SELECT COUNT(*)::int AS n FROM companies WHERE category = 'competitor'",
    ).get("n", 0)

    latest_poly = _one(
        """SELECT price::float AS price_rmb, price_usd::float AS price_usd,
                  change_7d::float AS change_7d
           FROM price_metrics_daily
           WHERE material = 'polyester_fdy' AND frequency = 'daily'
           ORDER BY metric_date DESC LIMIT 1""",
    )

    hs5407_export = _one(
        """SELECT to_char(period,'YYYY-MM') AS period,
                  (SUM(value_usd)/1e6)::float AS value_mn
           FROM trade_flows
           WHERE hs_code = '5407' AND flow_direction = 'export'
             AND partner_country IS NOT NULL
             AND period = (SELECT MAX(period) FROM trade_flows
                           WHERE hs_code='5407' AND flow_direction='export')
           GROUP BY period""",
    )

    price_signals_active = _one(
        """SELECT COUNT(*)::int AS n FROM price_intelligence_signals
           WHERE signal_date >= NOW() - INTERVAL '7 days' AND suppressed = FALSE""",
    ).get("n", 0)

    pta_row = _one(
        """SELECT momentum_score::float AS momentum
           FROM price_metrics_daily
           WHERE material = 'pta' AND frequency = 'daily'
           ORDER BY metric_date DESC LIMIT 1""",
    )
    pta_momentum = pta_row.get("momentum")
    if pta_momentum is not None:
        if pta_momentum > 0.1:   polyester_pressure = "rising"
        elif pta_momentum < -0.1: polyester_pressure = "falling"
        else:                     polyester_pressure = "stable"
    else:
        polyester_pressure = None

    rate, rate_date = get_rmb_usd_rate()
    return {
        "signal_count_30d":    signal_count,
        "competitor_count":    competitor_count,
        "polyester_price_rmb": latest_poly.get("price_rmb"),
        "polyester_price_usd": latest_poly.get("price_usd"),
        "polyester_change_7d": latest_poly.get("change_7d"),
        "hs5407_export_mn":    hs5407_export.get("value_mn"),
        "hs5407_period":       hs5407_export.get("period"),
        "rmb_usd_rate":        rate,
        "rmb_usd_rate_date":   rate_date,
        "price_signals_active": price_signals_active,
        "polyester_pressure":   polyester_pressure,
    }


# ── /api/signals ───────────────────────────────────────────────────────────────

@app.get("/api/signals")
def signals(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(200, ge=1, le=500),
    min_impact: int = Query(50, ge=0, le=100),
    category: str = Query("all"),
    horizon: str = Query("all"),
    action: str = Query("all"),
    exclude_critical: bool = Query(False),
    view_all: bool = Query(False),
):
    # Server-side floor: never serve below impact=60 unless view_all is explicitly requested
    if not view_all:
        min_impact = max(min_impact, 50)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conditions = ["ms.detected_at >= %s"]
    params: list = [cutoff]

    conditions.append("ms.impact_score >= %s")
    params.append(min_impact)

    if category != "all":
        conditions.append("ms.signal_category = %s")
        params.append(category)
    if horizon != "all":
        conditions.append("ms.time_horizon = %s")
        params.append(horizon)
    if action != "all":
        conditions.append("ms.action_tag = %s")
        params.append(action)

    # Exclude signals already shown in the Critical panel (impact≥80 within last 7 days)
    if exclude_critical:
        conditions.append(
            "(ms.impact_score < 80 OR ms.detected_at < NOW() - INTERVAL '7 days')"
        )

    where = " AND ".join(conditions)
    sql = f"""
        SELECT DISTINCT ON (COALESCE(ms.source_id::text, ms.id::text))
               ms.signal_type, ms.severity, ms.title,
               ms.body            AS summary,
               ms.source_table,
               ms.source_url,
               to_char(ms.detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS detected_at,
               ms.impact_score,
               ms.time_horizon,
               ms.action_tag,
               ms.signal_category,
               ms.material_form,
               ms.theme,
               ms.affected_products,
               ms.rayon_relevance,
               c.name AS company_name
        FROM market_signals ms
        LEFT JOIN companies c ON ms.company_id = c.id
        WHERE {where}
        ORDER BY COALESCE(ms.source_id::text, ms.id::text),
                 ms.impact_score DESC NULLS LAST, ms.detected_at DESC
        LIMIT %s
    """
    params.append(limit)
    return _rows(sql, params)


# ── /api/signal_stats ──────────────────────────────────────────────────────────

@app.get("/api/signal_stats")
def signal_stats():
    cutoff_7d  = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    cutoff_30d = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    # All counts use DISTINCT source_id to match the deduplication in /api/signals
    high_impact_7d = _one(
        """SELECT COUNT(DISTINCT source_id)::int AS n FROM market_signals
           WHERE detected_at >= %s AND impact_score >= 60""",
        [cutoff_7d],
    ).get("n", 0)

    critical_count = _one(
        """SELECT COUNT(DISTINCT source_id)::int AS n FROM market_signals
           WHERE detected_at >= %s AND impact_score >= 80""",
        [cutoff_7d],
    ).get("n", 0)

    cost_pressure_count = _one(
        """SELECT COUNT(DISTINCT source_id)::int AS n FROM market_signals
           WHERE detected_at >= %s AND signal_category = 'COST_IMPACT'""",
        [cutoff_30d],
    ).get("n", 0)

    risk_count = _one(
        """SELECT COUNT(DISTINCT source_id)::int AS n FROM market_signals
           WHERE detected_at >= %s AND action_tag = 'RISK'""",
        [cutoff_30d],
    ).get("n", 0)

    opportunity_count = _one(
        """SELECT COUNT(DISTINCT source_id)::int AS n FROM market_signals
           WHERE detected_at >= %s AND action_tag = 'OPPORTUNITY'""",
        [cutoff_30d],
    ).get("n", 0)

    top_themes = _rows(
        """SELECT theme, COUNT(DISTINCT source_id)::int AS count
           FROM market_signals
           WHERE detected_at >= %s AND theme IS NOT NULL
           GROUP BY theme ORDER BY count DESC LIMIT 5""",
        [cutoff_30d],
    )

    cat_rows = _rows(
        """SELECT signal_category, COUNT(DISTINCT source_id)::int AS count
           FROM market_signals
           WHERE detected_at >= %s AND signal_category IS NOT NULL
           GROUP BY signal_category ORDER BY count DESC""",
        [cutoff_30d],
    )
    category_breakdown = {r["signal_category"]: r["count"] for r in cat_rows}

    return {
        "high_impact_7d":       high_impact_7d,
        "critical_count":       critical_count,
        "cost_pressure_count":  cost_pressure_count,
        "risk_count":           risk_count,
        "opportunity_count":    opportunity_count,
        "top_themes":           top_themes,
        "category_breakdown":   category_breakdown,
    }


# ── /api/prices ────────────────────────────────────────────────────────────────

@app.get("/api/prices")
def prices():
    """
    Query price_metrics_daily (gold layer) for all daily-frequency materials.
    Joins dim_material for family, material_form, and Turkey lag estimates.
    Returns JSON:
      {
        meta: { rmb_usd_rate, rate_date },
        <material>: {
          meta: { family, material_form, lag_min_weeks, lag_max_weeks },
          latest: { price, price_usd, change_1d/7d/30d, confidence_tier,
                    momentum_score, divergence_score, ... },
          series: [{date, price, price_usd, ma7, ma30, normalized_idx}]
        }
      }
    """
    rate, rate_date = get_rmb_usd_rate()

    # Fetch dim_material for lag + family metadata
    dim_rows = _rows(
        "SELECT slug, family, material_form, lag_min_weeks, lag_max_weeks FROM dim_material"
    )
    dim_mat = {r["slug"]: r for r in dim_rows}

    rows = _rows("""
        SELECT material,
               to_char(metric_date, 'YYYY-MM-DD') AS metric_date,
               price::float,
               price_usd::float,
               change_1d::float,
               change_7d::float,
               change_30d::float,
               ma7::float,
               ma30::float,
               volatility_7d::float,
               normalized_idx::float,
               trend_direction,
               data_points,
               confidence_level,
               confidence_tier,
               momentum_score::float,
               divergence_score::float
        FROM price_metrics_daily
        WHERE frequency = 'daily'
          AND metric_date >= NOW() - INTERVAL '90 days'
        ORDER BY material, metric_date
    """)

    grouped: dict = {
        "meta": {"rmb_usd_rate": rate, "rate_date": rate_date},
    }
    for r in rows:
        m = r["material"]
        dm = dim_mat.get(m, {})
        if m not in grouped:
            grouped[m] = {
                "latest": None,
                "series": [],
                "meta": {
                    "family":        dm.get("family"),
                    "material_form": dm.get("material_form"),
                    "lag_min_weeks": dm.get("lag_min_weeks"),
                    "lag_max_weeks": dm.get("lag_max_weeks"),
                },
            }
        grouped[m]["series"].append({
            "date":           r["metric_date"],
            "price":          r["price"],
            "price_usd":      r["price_usd"],
            "ma7":            r["ma7"],
            "ma30":           r["ma30"],
            "normalized_idx": r["normalized_idx"],
        })
        grouped[m]["latest"] = {
            "price":            r["price"],
            "price_usd":        r["price_usd"],
            "change_1d":        r["change_1d"],
            "change_7d":        r["change_7d"],
            "change_30d":       r["change_30d"],
            "volatility_7d":    r["volatility_7d"],
            "trend_direction":  r["trend_direction"],
            "data_points":      r["data_points"],
            "confidence_level": r["confidence_level"],
            "confidence_tier":  r["confidence_tier"],
            "momentum_score":   r["momentum_score"],
            "divergence_score": r["divergence_score"],
        }

    return grouped


# ── /api/price_intelligence_signals ───────────────────────────────────────────

@app.get("/api/price_intelligence_signals")
def price_intelligence_signals_endpoint():
    """
    Return active price signals from price_intelligence_signals (Etap 1D output).
    Ordered by severity (critical→high→medium→low), then signal_date DESC.
    """
    return _rows("""
        SELECT
            id,
            signal_date::text        AS signal_date,
            signal_type,
            chain,
            material_slug,
            upstream_slug,
            downstream_slug,
            severity,
            time_horizon,
            confidence_tier,
            value_pct::float         AS value_pct,
            explanation,
            business_implication,
            turkey_lag_min,
            turkey_lag_max,
            suppressed
        FROM price_intelligence_signals
        WHERE signal_date >= NOW() - INTERVAL '7 days'
          AND suppressed = FALSE
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high'     THEN 2
                WHEN 'medium'   THEN 3
                ELSE 4
            END,
            signal_date DESC
    """)


# ── /api/price_signals ─────────────────────────────────────────────────────────

@app.get("/api/price_signals")
def price_signals_auto():
    """
    Compute auto-signals from the latest price_metrics_daily row per material.
    Rules:
      - change_7d > +3%  → rise warning
      - change_7d < -3%  → drop warning
      - volatility_7d > 2× average → volatility info
      - polyamide_fdy/polyester_fdy spread change > ±5% vs 30d ago → spread info
    Skips materials with < 7 data points (insufficient series).
    """
    # Latest row per daily material with confidence metadata
    latest = _rows("""
        SELECT DISTINCT ON (material)
            material,
            price::float         AS price,
            change_7d::float     AS change_7d,
            change_30d::float    AS change_30d,
            volatility_7d::float AS volatility_7d,
            trend_direction,
            data_points,
            confidence_level
        FROM price_metrics_daily
        WHERE frequency = 'daily'
        ORDER BY material, metric_date DESC
    """)

    # Split into eligible (high/medium confidence, change_7d present) and suppressed
    eligible   = [
        r for r in latest
        if r.get("confidence_level") in ("high", "medium")
        and r.get("change_7d") is not None
    ]
    suppressed_count = len(latest) - len(eligible)

    # Average volatility across eligible materials only
    vols    = [r["volatility_7d"] for r in eligible if r["volatility_7d"] is not None]
    avg_vol = sum(vols) / len(vols) if vols else None

    by_mat  = {r["material"]: r for r in latest}
    signals = []

    for r in eligible:
        mat   = r["material"]
        label = MATERIAL_LABELS.get(mat, mat)
        c7    = r["change_7d"]
        vol   = r["volatility_7d"]

        if c7 > 3:
            signals.append({
                "material": mat, "type": "rise", "severity": "warning",
                "text": f"{label} 7 günde +{c7:.1f}% yükseldi",
            })
        elif c7 < -3:
            signals.append({
                "material": mat, "type": "drop", "severity": "warning",
                "text": f"{label} 7 günde {c7:.1f}% geriledi",
            })

        if vol is not None and avg_vol and avg_vol > 0 and vol > 2 * avg_vol:
            signals.append({
                "material": mat, "type": "volatility", "severity": "info",
                "text": f"{label} yüksek volatilite (7G σ={vol:.1f})",
            })

    # Spread signal: polyamide_fdy / polyester_fdy ratio vs 30d ago
    # Requires high/medium confidence on both legs and change_30d available
    pa = by_mat.get("polyamide_fdy")
    pf = by_mat.get("polyester_fdy")
    if (pa and pf
            and pa.get("confidence_level") in ("high", "medium")
            and pf.get("confidence_level") in ("high", "medium")
            and pa.get("price") and pf.get("price") and pf["price"] != 0
            and pa.get("change_30d") is not None
            and pf.get("change_30d") is not None):
        ratio_now  = pa["price"] / pf["price"]
        pa_30d     = pa["price"] / (1 + pa["change_30d"] / 100)
        poly_30d   = pf["price"] / (1 + pf["change_30d"] / 100)
        if poly_30d != 0:
            ratio_30d  = pa_30d / poly_30d
            spread_chg = (ratio_now - ratio_30d) / ratio_30d * 100
            if abs(spread_chg) > 5:
                direction = "genişledi" if spread_chg > 0 else "daraldı"
                signals.append({
                    "material": "polyamide_fdy/polyester_fdy",
                    "type": "spread", "severity": "info",
                    "text": (f"Naylon/Polyester FDY fiyat makası {direction} "
                             f"({spread_chg:+.1f}%)"),
                })

    return {
        "signals":           signals,
        "suppressed":        suppressed_count,
        "suppressed_reason": "Insufficient data (confidence: low or minimal)",
    }


# ── /api/exports ───────────────────────────────────────────────────────────────

@app.get("/api/exports")
def exports(
    hs_code: str = Query("5407"),
    months: int = Query(12, ge=1, le=60),
):
    cutoff_period = (
        datetime.now() - timedelta(days=months * 30)
    ).strftime("%Y-%m-01")

    # Top 10 destinations (latest month)
    top_dest = _rows(
        """SELECT partner_country AS country,
                  (SUM(value_usd)/1e6)::float AS value_mn
           FROM trade_flows
           WHERE hs_code = %s AND flow_direction = 'export'
             AND partner_country IS NOT NULL
             AND period = (SELECT MAX(period) FROM trade_flows
                           WHERE hs_code=%s AND flow_direction='export')
           GROUP BY partner_country
           ORDER BY value_mn DESC LIMIT 10""",
        [hs_code, hs_code],
    )

    # Monthly trend for HS 5407 + 6006
    trend_rows = _rows(
        """SELECT hs_code,
                  to_char(period,'YYYY-MM') AS period,
                  (SUM(value_usd)/1e6)::float AS value_mn
           FROM trade_flows
           WHERE hs_code IN ('5407','6006') AND flow_direction='export'
             AND partner_country IS NOT NULL
             AND period >= %s
           GROUP BY hs_code, period
           ORDER BY period, hs_code""",
        [cutoff_period],
    )
    trend: dict = {}
    for r in trend_rows:
        h = r["hs_code"]
        trend.setdefault(h, {"periods": [], "values": []})
        trend[h]["periods"].append(r["period"])
        trend[h]["values"].append(r["value_mn"])

    # KPI metrics
    latest_two = _rows(
        """SELECT to_char(period,'YYYY-MM') AS period,
                  (SUM(value_usd)/1e6)::float AS value_mn
           FROM trade_flows
           WHERE hs_code=%s AND flow_direction='export' AND partner_country IS NOT NULL
           GROUP BY period ORDER BY period DESC LIMIT 2""",
        [hs_code],
    )
    kpi: dict = {}
    if latest_two:
        kpi["latest_period"] = latest_two[0]["period"]
        kpi["latest_value_mn"] = latest_two[0]["value_mn"]
        if len(latest_two) > 1 and latest_two[1]["value_mn"]:
            kpi["mom_pct"] = round(
                (latest_two[0]["value_mn"] - latest_two[1]["value_mn"])
                / latest_two[1]["value_mn"] * 100,
                1,
            )
    if top_dest:
        kpi["top_dest"] = top_dest[0]["country"]
        kpi["top_dest_mn"] = top_dest[0]["value_mn"]

    return {"kpi": kpi, "top_destinations": top_dest, "trend": trend}


# ── /api/lescon ────────────────────────────────────────────────────────────────

@app.get("/api/lescon")
def lescon(months: int = Query(24, ge=1, le=120)):
    by_fabric = _rows(
        """SELECT COALESCE(NULLIF(TRIM(fabric_type),''),'Unknown') AS fabric_type,
                  COUNT(*)::int AS tx_count,
                  ROUND(SUM(miktar*unit_price_usd)::numeric,0)::float AS revenue_usd
           FROM lescon_sales
           WHERE NOT is_return AND unit_price_usd > 0
             AND unit_price_usd IS NOT NULL AND miktar IS NOT NULL
           GROUP BY 1 ORDER BY revenue_usd DESC""",
    )

    monthly = _rows(
        """SELECT to_char(DATE_TRUNC('month',tarih),'YYYY-MM') AS month,
                  ROUND(SUM(miktar*unit_price_usd)::numeric,0)::float AS revenue_usd
           FROM lescon_sales
           WHERE NOT is_return AND tarih IS NOT NULL
             AND unit_price_usd > 0
             AND unit_price_usd IS NOT NULL AND miktar IS NOT NULL
           GROUP BY 1 ORDER BY 1""",
    )

    top_products = _rows(
        """SELECT COALESCE(NULLIF(TRIM(urun_aciklamasi),''),'Unknown') AS product,
                  COUNT(*)::int AS tx_count,
                  ROUND(SUM(miktar*unit_price_usd)::numeric,0)::float AS revenue_usd
           FROM lescon_sales
           WHERE NOT is_return AND unit_price_usd > 0
             AND unit_price_usd IS NOT NULL AND miktar IS NOT NULL
           GROUP BY 1 ORDER BY tx_count DESC LIMIT 10""",
    )

    yarn_trend = _rows(
        """SELECT EXTRACT(YEAR FROM factory_entry_date)::int AS year,
                  ROUND(AVG(unit_cost_usd)::numeric,4)::float AS avg_cost,
                  COUNT(*)::int AS records
           FROM yarn_costs
           WHERE unit_cost_usd > 0 AND unit_cost_usd IS NOT NULL
             AND factory_entry_date IS NOT NULL
           GROUP BY 1 ORDER BY 1""",
    )

    suppliers = _rows(
        """SELECT COALESCE(supplier_clean, supplier_raw, 'Unknown') AS supplier,
                  COALESCE(currency_clean,'?') AS currency,
                  COUNT(*)::int AS order_count,
                  ROUND(SUM(qty_numeric)::numeric,0)::float AS total_kg,
                  ROUND(AVG(price_numeric)::numeric,4)::float AS avg_price
           FROM orders
           WHERE record_status IS DISTINCT FROM 'exclude'
           GROUP BY 1,2 ORDER BY order_count DESC LIMIT 15""",
    )

    total_rev = sum(r["revenue_usd"] or 0 for r in by_fabric)
    total_tx  = sum(r["tx_count"] or 0  for r in by_fabric)

    return {
        "summary": {
            "total_revenue_usd": total_rev,
            "total_transactions": total_tx,
            "avg_tx_value": round(total_rev / total_tx, 0) if total_tx else 0,
        },
        "by_fabric": by_fabric,
        "monthly": monthly,
        "top_products": top_products,
        "yarn_trend": yarn_trend,
        "suppliers": suppliers,
    }


# ── /api/yarn_master ───────────────────────────────────────────────────────────

@app.get("/api/yarn_master")
def get_yarn_master():
    """
    Returns active canonical yarn specs with their price drivers.
    Phase 1 scope: synthetic yarn exposure and driver mapping only.
    NOT for exact pricing or quote benchmarking.
    """
    rows = _rows("""
        SELECT
            ym.yarn_id,
            ym.yarn_code,
            ym.display_name,
            ym.fiber_family,
            ym.filament_process,
            ym.denier,
            ym.filament_count,
            ym.denier_class,
            ym.luster,
            ym.recycle_flag,
            ym.subspec_sensitive,
            ym.application,
            yd.primary_driver_slug,
            yd.secondary_driver_slug,
            yd.pricing_method,
            yd.price_confidence,
            yd.denier_premium_rule,
            yd.luster_premium_rule,
            yd.recycle_factor::float,
            COUNT(yla.alias_id) AS alias_count
        FROM dim_yarn_master ym
        LEFT JOIN dim_yarn_price_driver yd ON yd.yarn_id = ym.yarn_id
        LEFT JOIN dim_yarn_label_alias yla ON yla.yarn_id = ym.yarn_id
        WHERE ym.pricing_eligible = TRUE
          AND ym.is_placeholder = FALSE
        GROUP BY ym.yarn_id, yd.driver_id
        ORDER BY ym.fiber_family, ym.denier NULLS LAST
    """)
    return {
        "yarns":        rows,
        "scope":        "Phase 1 — synthetic yarn driver mapping only",
        "coverage":     "polyester FDY/DTY + PA6/PA6.6",
        "not_covered":  ["cotton", "viscose", "blend", "elastane"],
        "safe_for":     ["driver_mapping", "exposure_grouping", "watchlist"],
        "not_safe_for": ["exact_pricing", "quote_benchmarking", "landed_cost"],
    }


# ── /api/yarn_pressure ─────────────────────────────────────────────────────────

@app.get("/api/yarn_pressure")
def get_yarn_pressure():
    """
    For each yarn, returns estimated cost pressure based on primary driver.
    Uses price_metrics_daily gold layer. Phase 1: indicative only.

    Coverage status is computed per-row in Python (not SQL) because the logic
    is still evolving. Possible values:
      - quote-validated : has a supplier quote in fact_supplier_quotes (last 90d)
      - placeholder     : dim_yarn_master.is_placeholder = true
      - driver-priced   : pricing_eligible + has driver match + has price data
      - not-covered     : pricing_eligible = false OR no driver mapping OR no price

    Pressure signals (derived from driver change_7d):
      - rising  : > +5%
      - firming : > +2% (and <= +5%)
      - stable  : -2% to +2%
      - easing  : < -2% (and >= -5%)
      - falling : < -5%
      - watch   : no data / insufficient
    """
    # Yarn IDs with fresh quotes (last 90 days). Currently empty, future-proof.
    quote_rows = _rows("""
        SELECT DISTINCT yarn_id
        FROM fact_supplier_quotes
        WHERE quote_date >= CURRENT_DATE - INTERVAL '90 days'
    """)
    yarns_with_quotes = {r["yarn_id"] for r in quote_rows}

    # Main query — all yarns, including placeholders and non-eligible specs.
    # Now includes filament_count and alias_count for spec metadata rendering.
    rows = _rows("""
        SELECT
            ym.yarn_id,
            ym.yarn_code,
            ym.display_name,
            ym.fiber_family,
            ym.filament_process,
            ym.denier,
            ym.denier_class,
            ym.filament_count,
            ym.luster,
            ym.recycle_flag,
            ym.subspec_sensitive,
            ym.is_placeholder,
            ym.pricing_eligible,
            COALESCE(ac.alias_count, 0) AS alias_count,
            yd.primary_driver_slug,
            yd.price_confidence,
            pmd.price_usd::float        AS driver_price_usd,
            pmd.change_7d::float        AS driver_change_7d,
            pmd.change_1d::float        AS driver_change_1d,
            pmd.trend_direction         AS driver_trend,
            pmd.momentum_score::float   AS driver_momentum,
            pmd.confidence_tier         AS driver_data_quality,
            dm.lag_min_weeks,
            dm.lag_max_weeks,
            CASE
                WHEN pmd.change_7d IS NULL     THEN 'watch'
                WHEN pmd.change_7d > 5         THEN 'rising'
                WHEN pmd.change_7d > 2         THEN 'firming'
                WHEN pmd.change_7d < -5        THEN 'falling'
                WHEN pmd.change_7d < -2        THEN 'easing'
                ELSE 'stable'
            END AS pressure_signal
        FROM dim_yarn_master ym
        LEFT JOIN dim_yarn_price_driver yd ON yd.yarn_id = ym.yarn_id
        LEFT JOIN (
            SELECT DISTINCT ON (material)
                material, price_usd, change_7d, change_1d,
                trend_direction, momentum_score, confidence_tier
            FROM price_metrics_daily
            WHERE frequency = 'daily'
            ORDER BY material, metric_date DESC
        ) pmd ON pmd.material = yd.primary_driver_slug
        LEFT JOIN dim_material dm ON dm.slug = yd.primary_driver_slug
        LEFT JOIN (
            SELECT yarn_id, COUNT(*) AS alias_count
            FROM dim_yarn_label_alias
            GROUP BY yarn_id
        ) ac ON ac.yarn_id = ym.yarn_id
        ORDER BY
            ym.fiber_family,
            CASE
                WHEN pmd.change_7d > 5     THEN 1
                WHEN pmd.change_7d > 2     THEN 2
                WHEN pmd.change_7d IS NULL THEN 6
                WHEN pmd.change_7d < -5    THEN 5
                WHEN pmd.change_7d < -2    THEN 4
                ELSE 3
            END,
            ym.denier NULLS LAST
    """)

    # Compute coverage_status per row (interpretation layer, kept in Python).
    for r in rows:
        if r["yarn_id"] in yarns_with_quotes:
            r["coverage_status"] = "quote-validated"
        elif r.get("is_placeholder"):
            r["coverage_status"] = "placeholder"
        elif (
            not r.get("pricing_eligible")
            or not r.get("primary_driver_slug")
            or r.get("driver_price_usd") is None
        ):
            r["coverage_status"] = "not-covered"
        else:
            r["coverage_status"] = "driver-priced"

    by_family: dict = {}
    for r in rows:
        fam = r["fiber_family"]
        by_family.setdefault(fam, []).append(r)

    # Coverage distribution for UI banner / legend
    coverage_summary = {
        "quote_validated": sum(1 for r in rows if r["coverage_status"] == "quote-validated"),
        "placeholder":     sum(1 for r in rows if r["coverage_status"] == "placeholder"),
        "driver_priced":   sum(1 for r in rows if r["coverage_status"] == "driver-priced"),
        "not_covered":     sum(1 for r in rows if r["coverage_status"] == "not-covered"),
        "total":           len(rows),
    }

    return {
        "by_family":         by_family,
        "flat":              rows,
        "coverage_summary":  coverage_summary,
        "confidence_note":   "indicative — driver-based estimates only, not validated quotes",
        "subspec_warning":   "yarns with subspec_sensitive=true may have pricing variants not captured here",
        "phase":             "Phase 1 — synthetic yarn driver mapping only. Cotton / viscose / blend = Phase 2.",
    }


# ── Serve static files (must be last) ─────────────────────────────────────────

# ════════════════════════════════════════════════════════════════════════════
# OPERATIONS INTELLIGENCE ENDPOINTS (M2)
# ════════════════════════════════════════════════════════════════════════════
#
# Six endpoints powering the "Operations Intelligence" dashboard tab.
# All endpoints read from gold views created in migration 010 v2:
#   - v_kpi_latest_month
#   - v_monthly_procurement_by_bucket
#   - v_monthly_cost_structure
#   - v_monthly_revenue_core
#   - v_top_suppliers_overall
#   - v_top_customers_overall
#
# Conventions:
#   - TL is primary; USD/EUR are secondary (per-currency, never mixed)
#   - Months filter applied at SQL layer (NOT frontend slicing)
#   - Default range = 24 months; query param `?months=N` overrides
#   - No caching (MVP — correctness first)
#   - Yarn resale exclusion is enforced inside views, not here
# ════════════════════════════════════════════════════════════════════════════


# ── /api/internal/kpi-latest-month ─────────────────────────────────────────
# Returns 12 KPI cards (4 per panel) for the latest complete month + YoY.
# Frontend-friendly normalized shape: one flat list, panel + display_order
# sufficient for grouping. No nested structure to unpack.

@app.get("/api/internal/overview-signals")
def internal_overview_signals():
    """
    M2.5.1 — Overview Phase 1 top-signals strip.
    Returns 4 fixed slots: customer_concentration, procurement_concentration,
    contra_revenue, margin_trend. Severity is rule-based (see migration 026).
    """
    rows = _rows("""
        SELECT
            display_order,
            signal_key,
            severity,
            title,
            metric_text,
            why_text
        FROM v_overview_signals
        ORDER BY display_order
    """)
    return {"signals": rows}


@app.get("/api/internal/kpi-latest-month")
def internal_kpi_latest_month():
    rows = _rows("""
        SELECT
            panel,
            display_order,
            metric_key,
            metric_label,
            current_tl::float          AS amount_tl,
            current_usd::float         AS amount_usd,
            current_eur::float         AS amount_eur,
            prior_tl::float            AS prior_tl,
            prior_usd::float           AS prior_usd,
            prior_eur::float           AS prior_eur,
            yoy_pct_tl::float          AS yoy_pct_tl,
            yoy_pct_usd::float         AS yoy_pct_usd,
            yoy_pct_eur::float         AS yoy_pct_eur,
            to_char(purchase_latest_month, 'YYYY-MM') AS purchase_latest_month,
            to_char(sales_latest_month,    'YYYY-MM') AS sales_latest_month
        FROM v_kpi_latest_month
        ORDER BY panel, display_order
    """)

    # Reference month — latest complete month from each side
    purchase_latest = rows[0]["purchase_latest_month"] if rows else None
    sales_latest    = rows[0]["sales_latest_month"]    if rows else None

    return {
        "kpis": rows,
        "reference": {
            "purchase_latest_month": purchase_latest,
            "sales_latest_month":    sales_latest,
            "wording":               "Latest complete month (current month excluded)",
        },
    }


# ── /api/internal/procurement-trend ────────────────────────────────────────
# Panel 1 main chart. Monthly procurement spend per raw-material bucket.

@app.get("/api/internal/procurement-trend")
def internal_procurement_trend(
    months: int = Query(24, ge=1, le=72),
):
    rows = _rows("""
        SELECT
            to_char(month, 'YYYY-MM')        AS month,
            business_bucket,
            row_count,
            amount_tl::float                 AS amount_tl,
            amount_usd::float                AS amount_usd,
            amount_eur::float                AS amount_eur,
            amount_try_d::float              AS amount_try_d,
            amount_other_fx::float           AS amount_other_fx,
            rows_usd_invoiced,
            rows_eur_invoiced
        FROM v_monthly_procurement_by_bucket
        WHERE month >= (
            SELECT (DATE_TRUNC('month', MAX(fatura_tarihi)) - (%s || ' months')::interval)::date
            FROM fact_purchase_lines_clean
        )
        ORDER BY month, business_bucket
    """, [months])

    return {
        "data":      rows,
        "row_count": len(rows),
        "months_requested": months,
        "buckets": [
            "raw_material_yarn",
            "raw_material_chemical",
            "raw_material_dye",
            "raw_material_greige_fabric",
        ],
    }


# ── /api/internal/cost-structure-trend ─────────────────────────────────────
# Panel 2 main chart. Monthly production-cost structure.
# Note: logistics_distribution is provisional (M2.1 will split inbound/outbound).

@app.get("/api/internal/cost-structure-trend")
def internal_cost_structure_trend(
    months: int = Query(24, ge=1, le=72),
):
    rows = _rows("""
        SELECT
            to_char(month, 'YYYY-MM')        AS month,
            business_bucket,
            row_count,
            amount_tl::float                 AS amount_tl,
            amount_usd::float                AS amount_usd,
            amount_eur::float                AS amount_eur,
            amount_try_d::float              AS amount_try_d
        FROM v_monthly_cost_structure
        WHERE month >= (
            SELECT (DATE_TRUNC('month', MAX(fatura_tarihi)) - (%s || ' months')::interval)::date
            FROM fact_purchase_lines_clean
        )
        ORDER BY month, business_bucket
    """, [months])

    return {
        "data":      rows,
        "row_count": len(rows),
        "months_requested": months,
        "buckets": [
            "utilities",
            "maintenance_factory",
            "packaging",
            "factory_overhead",
            "outsourced_processing",
            "logistics_distribution",
        ],
        "notes": {
            "logistics_distribution":
                "Provisional. M2.1 will split into inbound (procurement) vs outbound (commercial).",
        },
    }


# ── /api/internal/revenue-trend ────────────────────────────────────────────
# Panel 3 main chart. Monthly gross & net core revenue.
# Yarn resale is EXCLUDED at the view level via subtype filter.

@app.get("/api/internal/revenue-trend")
def internal_revenue_trend(
    months: int = Query(24, ge=1, le=72),
):
    rows = _rows("""
        SELECT
            to_char(month, 'YYYY-MM')        AS month,
            core_sales_tl::float             AS core_sales_tl,
            core_sales_try_d::float          AS core_sales_try_d,
            core_sales_usd::float            AS core_sales_usd,
            core_sales_eur::float            AS core_sales_eur,
            fason_revenue_tl::float          AS fason_revenue_tl,
            fason_revenue_usd::float         AS fason_revenue_usd,
            fason_revenue_eur::float         AS fason_revenue_eur,
            total_contra_tl::float           AS total_contra_tl,
            gross_revenue_tl::float          AS gross_revenue_tl,
            net_revenue_tl::float            AS net_revenue_tl,
            yarn_resale_tl::float            AS yarn_resale_tl
        FROM v_monthly_revenue_core
        WHERE month >= (
            SELECT (DATE_TRUNC('month', MAX(fatura_tarihi)) - (%s || ' months')::interval)::date
            FROM fact_sales_lines_clean
        )
        ORDER BY month
    """, [months])

    return {
        "data":      rows,
        "row_count": len(rows),
        "months_requested": months,
        "notes": {
            "yarn_resale":   "Excluded from core revenue (Rayon is fabric producer, not yarn trader). "
                             "Tracked separately as `yarn_resale_tl` for transparency.",
            "net_revenue":   "Net = Gross - SATIŞ-side returns/discounts - ALIŞ-side contra. TL only "
                             "(mixed-source contra not safe to aggregate in FX).",
        },
    }


# ── /api/internal/procurement-kpis ─────────────────────────────────────────
# M2.2.2 — Procurement Phase 1 KPI strip.
# Returns 6 metrics (3 anchor + 3 context) over the 12m rolling window,
# plus window metadata (latest complete month, total 12m TL).
@app.get("/api/internal/procurement-kpis")
def internal_procurement_kpis():
    rows = _rows("""
        SELECT
            top_3_supplier_share_pct::float AS top_3_supplier_share_pct,
            fx_invoiced_share_pct::float    AS fx_invoiced_share_pct,
            active_supplier_count,
            yarn_share_pct::float           AS yarn_share_pct,
            greige_share_pct::float         AS greige_share_pct,
            biggest_mover_bucket,
            biggest_mover_pct::float        AS biggest_mover_pct,
            biggest_mover_tl::float         AS biggest_mover_tl,
            latest_month,
            prior_month,
            total_12m_tl::float             AS total_12m_tl
        FROM v_procurement_kpis
    """)
    if not rows:
        return {"error": "no procurement data"}
    return rows[0]


# ── /api/internal/procurement-concentration-trend ──────────────────────────
# M2.2.4 — Procurement Phase 1 Chart 3: top 1 / top 3 / top 10 supplier share
# month-by-month over the trailing 24-month window. Source: v_procurement_concentration_trend.
@app.get("/api/internal/procurement-concentration-trend")
def internal_procurement_concentration_trend():
    rows = _rows("""
        SELECT
            month,
            top_1_share_pct::float  AS top_1_share_pct,
            top_3_share_pct::float  AS top_3_share_pct,
            top_10_share_pct::float AS top_10_share_pct,
            total_tl::float          AS total_tl,
            active_suppliers
        FROM v_procurement_concentration_trend
        ORDER BY month
    """)
    return {
        "data":      rows,
        "threshold": 33.0,
        "window":    "24 months rolling",
        "scope":     "cost_model_relevant only",
    }


# ── /api/internal/procurement-currency-trend ───────────────────────────────
# M2.2.5 — Procurement Phase 1 Chart 4: TL-equivalent spend by invoice
# currency (TRY/USD/EUR/OTHER) over 24m. Source: v_monthly_procurement_by_currency.
# Note: amount_tl is the invoice-date TL equivalent stored by Nebim
# (net_tutar_y), NOT a re-conversion at today's FX rate.
@app.get("/api/internal/procurement-currency-trend")
def internal_procurement_currency_trend():
    rows = _rows("""
        SELECT
            month,
            currency,
            row_count,
            amount_tl::float AS amount_tl
        FROM v_monthly_procurement_by_currency
        ORDER BY month, currency
    """)
    return {
        "data":       rows,
        "currencies": ["TRY", "USD", "EUR", "OTHER"],
        "window":     "24 months rolling",
        "scope":      "cost_model_relevant only",
        "note":       "amount_tl is invoice-date TL equivalent (net_tutar_y), not re-converted at current FX rate",
    }


# ── /api/internal/top-suppliers ────────────────────────────────────────────
# Panel 1 list. Top N suppliers by spend in cost-relevant buckets (last 12 months).

@app.get("/api/internal/top-suppliers")
def internal_top_suppliers(
    limit: int = Query(10, ge=1, le=100),
):
    rows = _rows("""
        SELECT
            supplier_name,
            row_count,
            bucket_count,
            amount_tl::float    AS amount_tl,
            amount_usd::float   AS amount_usd,
            amount_eur::float   AS amount_eur,
            top_bucket,
            to_char(first_invoice_date, 'YYYY-MM-DD') AS first_invoice_date,
            to_char(last_invoice_date,  'YYYY-MM-DD') AS last_invoice_date,
            -- M2.2.1 enrichment (Migration 015)
            share_pct::float    AS share_pct,
            trend_direction,
            amount_tl_h1::float AS amount_tl_h1,
            amount_tl_h2::float AS amount_tl_h2,
            vergi_numarasi,
            is_verified,
            name_variants_count
        FROM v_top_suppliers_overall
        ORDER BY amount_tl DESC NULLS LAST
        LIMIT %s
    """, [limit])

    return {
        "suppliers":     rows,
        "count":         len(rows),
        "window":        "last 12 months",
        "scope":         "cost_model_relevant buckets only",
    }


# ── /api/internal/revenue-kpis ─────────────────────────────────────────────
# M2.3.2 — Revenue Phase 1 KPI strip.
# Returns 6+ metrics over the 12m rolling window.
# core_total_12m_tl is provided for frontend-side avg-monthly calc (÷ 12).
# KPI 6 = Top 3 customer share Δ (pp). Positive = concentration rising.
@app.get("/api/internal/revenue-kpis")
def internal_revenue_kpis():
    rows = _rows("""
        SELECT
            top_3_customer_share_pct::float AS top_3_customer_share_pct,
            fx_invoiced_share_pct::float    AS fx_invoiced_share_pct,
            active_customer_count,
            core_revenue_share_pct::float   AS core_revenue_share_pct,
            contra_share_pct::float         AS contra_share_pct,
            top_3_share_delta_pp::float     AS top_3_share_delta_pp,
            top_3_share_latest_pct::float   AS top_3_share_latest_pct,
            top_3_share_prior_pct::float    AS top_3_share_prior_pct,
            latest_month,
            prior_month,
            core_total_12m_tl::float        AS core_total_12m_tl
        FROM v_revenue_kpis
    """)
    if not rows:
        return {"error": "no revenue data"}
    return rows[0]


# ── /api/internal/customer-concentration-trend ─────────────────────────────
# M2.3.3 — Revenue Phase 1: top 1 / top 3 / top 10 customer share month by
# month over the trailing 24-month window. Mirror of procurement-concentration.
@app.get("/api/internal/customer-concentration-trend")
def internal_customer_concentration_trend():
    rows = _rows("""
        SELECT
            month,
            top_1_share_pct::float  AS top_1_share_pct,
            top_3_share_pct::float  AS top_3_share_pct,
            top_10_share_pct::float AS top_10_share_pct,
            total_tl::float          AS total_tl,
            active_customers
        FROM v_customer_concentration_trend
        ORDER BY month
    """)
    return {
        "data":      rows,
        "threshold": 33.0,
        "window":    "24 months rolling",
        "scope":     "core_product_sales + outsourced_service_revenue (yarn_resale excluded)",
    }


# ── /api/internal/cost-kpis ────────────────────────────────────────────────
# M2.4.2 — Cost Structure Phase 1 KPI strip.
# Returns 6 metrics over the 12m rolling window + 3m vs 3m margin trend.
# KPI 6 = cost/revenue ratio Δ (pp). Positive = margin compression.
@app.get("/api/internal/cost-kpis")
def internal_cost_kpis():
    rows = _rows("""
        SELECT
            cost_share_of_revenue_pct::float       AS cost_share_of_revenue_pct,
            outsourced_processing_share_pct::float AS outsourced_processing_share_pct,
            active_cost_supplier_count,
            maintenance_share_pct::float           AS maintenance_share_pct,
            avg_monthly_cost_tl::float             AS avg_monthly_cost_tl,
            cost_revenue_ratio_delta_pp::float     AS cost_revenue_ratio_delta_pp,
            cost_revenue_ratio_recent_pct::float   AS cost_revenue_ratio_recent_pct,
            cost_revenue_ratio_prior_pct::float    AS cost_revenue_ratio_prior_pct,
            recent_window_start,
            recent_window_end,
            prior_window_start,
            prior_window_end,
            cost_total_12m_tl::float               AS cost_total_12m_tl,
            revenue_total_12m_tl::float            AS revenue_total_12m_tl
        FROM v_cost_kpis
    """)
    if not rows:
        return {"error": "no cost data"}
    return rows[0]


# ── /api/internal/top-cost-suppliers ───────────────────────────────────────
# M2.4.1 — Cost Structure Phase 1: top suppliers in cost-bucket scope
# (utilities/maintenance/packaging/factory_overhead/outsourced_processing/
# logistics_distribution). 12m rolling. Includes bucket spread (top + secondary).
# ── /api/internal/cost-movers ──────────────────────────────────────────────
# M2.4.4 — Cost Structure Phase 1 Movers strip.
# Returns up to 3 slots (biggest_increase, biggest_decrease, highest_volatility).
# Each slot may be absent if threshold not met (frontend renders empty state).
@app.get("/api/internal/cost-movers")
def internal_cost_movers():
    rows = _rows("""
        SELECT
            display_order,
            slot,
            bucket,
            pct_change::float        AS pct_change,
            abs_change_tl::float     AS abs_change_tl,
            latest_tl::float         AS latest_tl,
            prior_tl::float          AS prior_tl,
            cv::float                AS cv,
            stdev_tl::float          AS stdev_tl,
            mean_tl::float           AS mean_tl
        FROM v_cost_movers
        ORDER BY display_order
    """)
    return {
        "movers": rows,
        "thresholds": {
            "increase_pct":   5.0,
            "decrease_pct":  -5.0,
            "volatility_cv":  0.20,
        },
        "window": {
            "movers":     "latest complete month vs prior complete month",
            "volatility": "last 12 months",
        },
    }


@app.get("/api/internal/top-cost-suppliers")
def internal_top_cost_suppliers(
    limit: int = Query(10, ge=1, le=100),
):
    rows = _rows("""
        SELECT
            supplier_name,
            row_count,
            bucket_count,
            amount_tl::float                        AS amount_tl,
            amount_usd::float                       AS amount_usd,
            amount_eur::float                       AS amount_eur,
            top_bucket,
            top_bucket_share_pct::float             AS top_bucket_share_pct,
            secondary_bucket,
            secondary_bucket_share_pct::float       AS secondary_bucket_share_pct,
            to_char(first_invoice_date, 'YYYY-MM-DD') AS first_invoice_date,
            to_char(last_invoice_date,  'YYYY-MM-DD') AS last_invoice_date,
            share_pct::float                        AS share_pct,
            trend_direction,
            amount_tl_h1::float                     AS amount_tl_h1,
            amount_tl_h2::float                     AS amount_tl_h2,
            vergi_numarasi,
            is_verified,
            name_variants_count
        FROM v_top_cost_suppliers_overall
        ORDER BY amount_tl DESC NULLS LAST
        LIMIT %s
    """, [limit])

    return {
        "suppliers":     rows,
        "count":         len(rows),
        "window":        "last 12 months",
        "scope":         "cost buckets only (utilities, maintenance, packaging, "
                         "factory_overhead, outsourced_processing, logistics_distribution)",
    }


# ── /api/internal/top-customers ────────────────────────────────────────────
# Panel 3 list. Top N customers by core-revenue spend (last 12 months).
# Yarn resale customers excluded at view level.

@app.get("/api/internal/top-customers")
def internal_top_customers(
    limit: int = Query(10, ge=1, le=100),
):
    rows = _rows("""
        SELECT
            customer_name,
            row_count,
            bucket_count,
            amount_tl::float    AS amount_tl,
            amount_usd::float   AS amount_usd,
            amount_eur::float   AS amount_eur,
            rows_usd,
            rows_try,
            rows_eur,
            to_char(first_invoice_date, 'YYYY-MM-DD') AS first_invoice_date,
            to_char(last_invoice_date,  'YYYY-MM-DD') AS last_invoice_date,
            -- M2.3.1 enrichment (Migration 019)
            share_pct::float    AS share_pct,
            trend_direction,
            amount_tl_h1::float AS amount_tl_h1,
            amount_tl_h2::float AS amount_tl_h2,
            vergi_numarasi,
            is_verified,
            name_variants_count
        FROM v_top_customers_overall
        ORDER BY amount_tl DESC NULLS LAST
        LIMIT %s
    """, [limit])

    return {
        "customers":     rows,
        "count":         len(rows),
        "window":        "last 12 months",
        "scope":         "core_product_sales + outsourced_service_revenue (yarn_resale excluded)",
    }


# ── /api/internal/contra-anomaly ───────────────────────────────────────────
# Single-row alert card. Surfaces contra revenue as a separate anomaly signal
# (median-based context, top counterparty concentration, severity flag) instead
# of an unreliable YoY % from a low-base prior month.

@app.get("/api/internal/contra-anomaly")
def internal_contra_anomaly():
    row = _one("""
        SELECT
            month_label,
            to_char(month_date, 'YYYY-MM-DD')        AS month_date,
            total_contra_tl::float                   AS total_contra_tl,
            alis_contra_tl::float                    AS alis_contra_tl,
            satis_contra_tl::float                   AS satis_contra_tl,
            returns_tl::float                        AS returns_tl,
            discounts_tl::float                      AS discounts_tl,
            gross_revenue_tl::float                  AS gross_revenue_tl,
            contra_pct_of_gross::float               AS contra_pct_of_gross,
            median_24m_pct::float                    AS median_24m_pct,
            mean_24m_pct::float                      AS mean_24m_pct,
            min_24m_pct::float                       AS min_24m_pct,
            max_24m_pct::float                       AS max_24m_pct,
            history_sample_months                    AS history_sample_months,
            ratio_to_median::float                   AS ratio_to_median,
            top_counterparty_name,
            top_counterparty_source,
            top_counterparty_tl::float               AS top_counterparty_tl,
            top_counterparty_pct::float              AS top_counterparty_pct,
            severity
        FROM v_contra_anomaly_detail
    """)

    return {
        "anomaly":  row,
        "notes": {
            "method":     "Median-based anomaly detection over 24-month history. "
                          "Severity: high if ratio_to_median >= 2.5, elevated if >= 1.5, else normal.",
            "yoy_warning": "YoY % is intentionally NOT exposed for contra revenue. "
                           "Prior-year same month can be an outlier itself, making YoY misleading.",
            "yarn_resale": "Gross revenue used for contra% excludes yarn resale (subtype filter).",
        },
    }


# === COUNTERPARTY EXPLORER (M2.1) ===
# Two endpoints backed by the dim_counterparty view (Migration 012).
# - List endpoint: smart search + lean field set, drives the search-typeahead UI.
# - Detail endpoint: full panel data for a selected counterparty.

@app.get("/api/internal/counterparties")
def list_counterparties(
    side: str = "purchase",
    q: str = "",
    type: str | None = None,
    limit: int = 50,
):
    """
    Smart-search list of counterparties.

    Search behavior:
      - If `q` looks like digits/tax id: prefix match on vergi_numarasi
      - Otherwise: case-insensitive substring on display_name
      - Order: exact-tax-match > tax-prefix > name-substring > total_tl_24m DESC
    """
    if side not in ("purchase", "sales"):
        return {"error": "side must be purchase or sales"}, 400

    limit = max(1, min(200, int(limit)))
    q = (q or "").strip()
    q_clean = q.replace(".0", "")  # tolerate '1234567890.0' style

    # Build the query
    sql_parts = ["""
        SELECT
            canonical_key,
            display_name,
            vergi_numarasi,
            is_verified,
            counterparty_type,
            total_tl_24m,
            row_count_24m,
            last_seen,
            name_variants_count
        FROM dim_counterparty
        WHERE side = %s
    """]
    params = [side]

    if type:
        sql_parts.append("AND counterparty_type = %s")
        params.append(type)

    is_numeric_query = q_clean.isdigit() and len(q_clean) >= 3

    if q:
        if is_numeric_query:
            # Tax id prefix match OR name substring (broader for short numeric queries)
            sql_parts.append(
                "AND (vergi_numarasi LIKE %s OR display_name ILIKE %s)"
            )
            params.append(q_clean + "%")
            params.append("%" + q + "%")
        else:
            # Pure name search
            sql_parts.append("AND display_name ILIKE %s")
            params.append("%" + q + "%")

    # Relevance-aware ordering
    if q and is_numeric_query:
        sql_parts.append("""
            ORDER BY
              CASE
                WHEN vergi_numarasi = %s THEN 0
                WHEN vergi_numarasi LIKE %s THEN 1
                WHEN display_name ILIKE %s THEN 2
                ELSE 3
              END,
              total_tl_24m DESC NULLS LAST
        """)
        params.extend([q_clean, q_clean + "%", "%" + q + "%"])
    elif q:
        # For text search, exact match first, then position of substring
        sql_parts.append("""
            ORDER BY
              CASE WHEN display_name ILIKE %s THEN 0 ELSE 1 END,
              total_tl_24m DESC NULLS LAST
        """)
        params.append(q + "%")  # starts-with bonus
    else:
        sql_parts.append("ORDER BY total_tl_24m DESC NULLS LAST")

    sql_parts.append("LIMIT %s")
    params.append(limit)

    sql = "\n".join(sql_parts)

    rows = _rows(sql, params)

    return {
        "side": side,
        "q": q,
        "count": len(rows),
        "results": [
            {
                "canonical_key": r["canonical_key"],
                "display_name": r["display_name"],
                "vergi_numarasi": r["vergi_numarasi"],
                "is_verified": r["is_verified"],
                "counterparty_type": r["counterparty_type"],
                "total_tl_24m": float(r["total_tl_24m"]) if r["total_tl_24m"] else 0,
                "row_count_24m": r["row_count_24m"] or 0,
                "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
                "name_variants_count": r["name_variants_count"] or 1,
            }
            for r in rows
        ],
    }


@app.get("/api/internal/counterparty/detail")
@with_shared_conn
def counterparty_detail(
    side: str = "purchase",
    canonical_key: str = "",
    months: int = 24,
):
    """
    Detail panel for a single counterparty.
    Returns: summary, monthly_trend, bucket_split, subtype_split,
             currency_split, top_accounts, classification_quality, recent_rows.

    M2.2.6c: @with_shared_conn borrows ONE pool connection for the whole
    request. All 11 _rows() calls below reuse it via thread-local, eliminating
    pool getconn/putconn round-trip per query (~200ms each against Railway
    US-West).
    """
    if side not in ("purchase", "sales"):
        return {"error": "side must be purchase or sales"}, 400
    if not canonical_key:
        return {"error": "canonical_key is required"}, 400

    months = max(1, min(120, int(months)))
    fact_table = f"fact_{'purchase' if side == 'purchase' else 'sales'}_lines_clean"

    # Header row from dim_counterparty
    header = _rows(
        """
        SELECT * FROM dim_counterparty
        WHERE side = %s AND canonical_key = %s
        """,
        [side, canonical_key],
    )
    if not header:
        return {"error": "counterparty not found"}, 404
    h = header[0]

    # Reconstruct the WHERE clause used by the view to filter rows for this counterparty
    if h["is_verified"]:
        # vergi_numarasi stored as-is (e.g. 'REDACTED_TAX_ID.0') — direct equality
        # matches the index idx_fact_purch_vn_date / idx_fact_sales_vn_date.
        cp_filter = "vergi_numarasi = %s"
        cp_param = h["vergi_numarasi"]
    else:
        # Unverified: tax id missing/zero — match by raw display name
        # Index idx_fact_purch_cariname_date / idx_fact_sales_cariname_date.
        cp_filter = """(vergi_numarasi IS NULL OR vergi_numarasi IN ('', '0', '0.0'))
                       AND cari_hesap_aciklamasi = %s"""
        cp_param = h["display_name"]

    # Data horizon (anchor for "trailing N months")
    horizon_row = _rows(f"SELECT MAX(fatura_tarihi) AS m FROM {fact_table}", [])
    horizon = horizon_row[0]["m"] if horizon_row else None

    # ── Summary ─────────────────────────────────────────────────────────────
    summary = _rows(
        f"""
        SELECT
            SUM(net_tutar_y) FILTER (
                WHERE fatura_tarihi >= (%s::date - INTERVAL '{months} months')
            )::float AS total_tl,
            SUM(net_tutar_d) FILTER (
                WHERE para_birimi_d = 'USD'
                  AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
            )::float AS total_usd,
            SUM(net_tutar_d) FILTER (
                WHERE para_birimi_d = 'EUR'
                  AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
            )::float AS total_eur,
            COUNT(*) FILTER (
                WHERE fatura_tarihi >= (%s::date - INTERVAL '{months} months')
            )::int AS row_count,
            MIN(fatura_tarihi) AS first_invoice,
            MAX(fatura_tarihi) AS last_invoice
        FROM {fact_table}
        WHERE {cp_filter}
        """,
        [horizon, horizon, horizon, horizon, cp_param],
    )[0]

    # Total side amount in window for share calc
    side_total_row = _rows(
        f"""
        SELECT SUM(net_tutar_y)::float AS t
        FROM {fact_table}
        WHERE fatura_tarihi >= (%s::date - INTERVAL '{months} months')
        """,
        [horizon],
    )
    side_total = side_total_row[0]["t"] or 0
    share_pct = (
        100.0 * (summary["total_tl"] or 0) / side_total
        if side_total else 0
    )

    # ── Monthly trend ───────────────────────────────────────────────────────
    monthly = _rows(
        f"""
        SELECT DATE_TRUNC('month', fatura_tarihi)::date AS month,
               SUM(net_tutar_y)::float AS amount_tl,
               COUNT(*)::int AS rows
        FROM {fact_table}
        WHERE {cp_filter}
          AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
        GROUP BY 1 ORDER BY 1
        """,
        [cp_param, horizon],
    )

    # ── Bucket split ────────────────────────────────────────────────────────
    buckets = _rows(
        f"""
        SELECT business_bucket AS bucket,
               SUM(net_tutar_y)::float AS amount_tl,
               COUNT(*)::int AS rows
        FROM {fact_table}
        WHERE {cp_filter}
          AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
        GROUP BY 1 ORDER BY amount_tl DESC NULLS LAST
        """,
        [cp_param, horizon],
    )
    cp_total = sum((b["amount_tl"] or 0) for b in buckets) or 1
    bucket_split = [
        {
            "bucket": b["bucket"],
            "amount_tl": b["amount_tl"] or 0,
            "share_pct": round(100.0 * (b["amount_tl"] or 0) / cp_total, 1),
            "rows": b["rows"],
        }
        for b in buckets
    ]

    # ── Subtype split ───────────────────────────────────────────────────────
    subtypes = _rows(
        f"""
        SELECT subtype, SUM(net_tutar_y)::float AS amount_tl, COUNT(*)::int AS rows
        FROM {fact_table}
        WHERE {cp_filter}
          AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
          AND subtype IS NOT NULL AND subtype <> ''
        GROUP BY 1 ORDER BY amount_tl DESC NULLS LAST
        LIMIT 15
        """,
        [cp_param, horizon],
    )

    # ── Currency split ──────────────────────────────────────────────────────
    currencies = _rows(
        f"""
        SELECT COALESCE(para_birimi_d, '<unknown>') AS ccy,
               SUM(net_tutar_y)::float AS amount_tl,
               COUNT(*)::int AS rows
        FROM {fact_table}
        WHERE {cp_filter}
          AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
        GROUP BY 1 ORDER BY amount_tl DESC NULLS LAST
        """,
        [cp_param, horizon],
    )

    # ── Top accounts ────────────────────────────────────────────────────────
    accounts = _rows(
        f"""
        SELECT hesap_kodu, hesap_aciklamasi,
               SUM(net_tutar_y)::float AS amount_tl,
               COUNT(*)::int AS rows
        FROM {fact_table}
        WHERE {cp_filter}
          AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
          AND hesap_kodu IS NOT NULL
        GROUP BY 1, 2 ORDER BY amount_tl DESC NULLS LAST
        LIMIT 10
        """,
        [cp_param, horizon],
    )

    # ── Classification quality ──────────────────────────────────────────────
    quality = _rows(
        f"""
        SELECT
            100.0 * SUM(CASE WHEN confidence_level = 'high' THEN 1 ELSE 0 END)
                  / NULLIF(COUNT(*), 0) AS confidence_high_pct,
            100.0 * SUM(CASE WHEN review_flag THEN 1 ELSE 0 END)
                  / NULLIF(COUNT(*), 0) AS review_flagged_pct
        FROM {fact_table}
        WHERE {cp_filter}
          AND fatura_tarihi >= (%s::date - INTERVAL '{months} months')
        """,
        [cp_param, horizon],
    )[0]

    # ── Recent rows ─────────────────────────────────────────────────────────
    recent = _rows(
        f"""
        SELECT fatura_tarihi, hesap_kodu, business_bucket AS bucket,
               net_tutar_y::float AS amount_tl,
               para_birimi_d AS ccy
        FROM {fact_table}
        WHERE {cp_filter}
        ORDER BY fatura_tarihi DESC NULLS LAST
        LIMIT 20
        """,
        [cp_param],
    )

    return {
        "side": side,
        "canonical_key": canonical_key,
        "vergi_numarasi": h["vergi_numarasi"],
        "display_name": h["display_name"],
        "is_verified": h["is_verified"],
        "counterparty_type": h["counterparty_type"],
        "name_variants_count": h["name_variants_count"] or 1,
        "months": months,
        "data_horizon": horizon.isoformat() if horizon else None,
        "summary": {
            "total_tl": summary["total_tl"] or 0,
            "total_usd": summary["total_usd"] or 0,
            "total_eur": summary["total_eur"] or 0,
            "row_count": summary["row_count"] or 0,
            "first_invoice": summary["first_invoice"].isoformat() if summary["first_invoice"] else None,
            "last_invoice": summary["last_invoice"].isoformat() if summary["last_invoice"] else None,
            "share_of_total_pct": round(share_pct, 2),
        },
        "monthly_trend": [
            {"month": r["month"].isoformat(), "amount_tl": r["amount_tl"] or 0, "rows": r["rows"]}
            for r in monthly
        ],
        "bucket_split": bucket_split,
        "subtype_split": [
            {"subtype": r["subtype"], "amount_tl": r["amount_tl"] or 0, "rows": r["rows"]}
            for r in subtypes
        ],
        "currency_split": [
            {"ccy": r["ccy"], "amount_tl": r["amount_tl"] or 0, "rows": r["rows"]}
            for r in currencies
        ],
        "top_accounts": [
            {
                "hesap_kodu": r["hesap_kodu"],
                "hesap_aciklamasi": r["hesap_aciklamasi"],
                "amount_tl": r["amount_tl"] or 0,
                "rows": r["rows"],
            }
            for r in accounts
        ],
        "classification_quality": {
            "confidence_high_pct": round(float(quality["confidence_high_pct"] or 0), 1),
            "review_flagged_pct": round(float(quality["review_flagged_pct"] or 0), 1),
        },
        "recent_rows": [
            {
                "fatura_tarihi": r["fatura_tarihi"].isoformat() if r["fatura_tarihi"] else None,
                "hesap_kodu": r["hesap_kodu"],
                "bucket": r["bucket"],
                "amount_tl": r["amount_tl"] or 0,
                "ccy": r["ccy"],
            }
            for r in recent
        ],
    }

# === END COUNTERPARTY EXPLORER (M2.1) ===

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
