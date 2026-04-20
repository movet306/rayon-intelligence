"""
dashboard/server.py — Rayon Intelligence FastAPI backend

Run:
    uvicorn dashboard.server:app --port 8000 --reload
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
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


def _conn():
    return psycopg2.connect(DB_URL)


def _rows(sql: str, params=None) -> list[dict]:
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
        """SELECT price::float AS price_rmb, price_usd::float AS price_usd
           FROM price_metrics_daily
           WHERE material = 'polyester_staple_fiber' AND frequency = 'daily'
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

    rate, rate_date = get_rmb_usd_rate()
    return {
        "signal_count_30d": signal_count,
        "competitor_count": competitor_count,
        "polyester_price_rmb": latest_poly.get("price_rmb"),
        "polyester_price_usd": latest_poly.get("price_usd"),
        "hs5407_export_mn": hs5407_export.get("value_mn"),
        "hs5407_period": hs5407_export.get("period"),
        "rmb_usd_rate": rate,
        "rmb_usd_rate_date": rate_date,
    }


# ── /api/signals ───────────────────────────────────────────────────────────────

@app.get("/api/signals")
def signals(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(200, ge=1, le=500),
    min_impact: int = Query(0, ge=0, le=100),
    category: str = Query("all"),
    horizon: str = Query("all"),
    action: str = Query("all"),
    exclude_critical: bool = Query(False),
):
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
    Returns JSON:
      {
        meta: { rmb_usd_rate, rate_date },
        <material>: { latest: {...}, series: [{date, price, price_usd, ma7, ma30, normalized_idx}] }
      }
    """
    rate, rate_date = get_rmb_usd_rate()

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
               confidence_level
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
        if m not in grouped:
            grouped[m] = {"latest": None, "series": []}
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
        }

    return grouped


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


# ── Serve static files (must be last) ─────────────────────────────────────────

app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
