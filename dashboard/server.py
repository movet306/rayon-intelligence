"""
dashboard/server.py — Rayon Intelligence FastAPI backend

Run:
    uvicorn dashboard.server:app --port 8000 --reload
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

DB_URL = os.environ.get("DATABASE_URL", "")
STATIC_DIR = Path(__file__).parent / "static"

RMB_USD_RATE = float(os.getenv("RMB_USD_RATE", "0.138"))

app = FastAPI(title="Rayon Intelligence API", docs_url="/api/docs")


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
        """SELECT price_usd::float AS price, unit
           FROM price_signals
           WHERE source = 'sunsirs' AND material = 'polyester_staple_fiber'
           ORDER BY period DESC LIMIT 1""",
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

    return {
        "signal_count_30d": signal_count,
        "competitor_count": competitor_count,
        "polyester_price_rmb": latest_poly.get("price"),
        "polyester_price_unit": latest_poly.get("unit", "RMB/ton"),
        "hs5407_export_mn": hs5407_export.get("value_mn"),
        "hs5407_period": hs5407_export.get("period"),
    }


# ── /api/signals ───────────────────────────────────────────────────────────────

@app.get("/api/signals")
def signals(
    days: int = Query(30, ge=1, le=365),
    type: str = Query("all"),
    severity: str = Query("all"),
    limit: int = Query(100, ge=1, le=500),
):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conditions = ["ms.detected_at >= %s"]
    params: list = [cutoff]

    if type != "all":
        conditions.append("ms.signal_type = %s")
        params.append(type)
    if severity != "all":
        conditions.append("ms.severity = %s")
        params.append(severity)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT ms.signal_type, ms.severity, ms.title,
               ms.body        AS summary,
               ms.source_table,
               to_char(ms.detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS detected_at,
               c.name AS company_name
        FROM market_signals ms
        LEFT JOIN companies c ON ms.company_id = c.id
        WHERE {where}
        ORDER BY ms.detected_at DESC
        LIMIT %s
    """
    params.append(limit)
    return _rows(sql, params)


# ── /api/prices ────────────────────────────────────────────────────────────────

@app.get("/api/prices")
def prices(
    materials: str = Query(
        "polyester_staple_fiber,polyester_fdy,polyester_poy,"
        "polyamide_fdy,cotton_lint,pa6_chip,pa66_chip"
    ),
):
    mat_list = [m.strip() for m in materials.split(",") if m.strip()]
    placeholders = ",".join(["%s"] * len(mat_list))
    sql = f"""
        SELECT material,
               to_char(period, 'YYYY-MM-DD') AS period,
               price_usd::float               AS price,
               unit
        FROM price_signals
        WHERE source = 'sunsirs'
          AND material IN ({placeholders})
        ORDER BY material, period
    """
    rows = _rows(sql, mat_list)

    # Group by material → {material: {periods:[], prices:[], unit:""}}
    grouped: dict = {}
    for r in rows:
        m = r["material"]
        if m not in grouped:
            grouped[m] = {"periods": [], "prices": [], "unit": r["unit"]}
        grouped[m]["periods"].append(r["period"])
        grouped[m]["prices"].append(r["price"])

    # Attach % change over series
    for m, d in grouped.items():
        prices_list = d["prices"]
        if len(prices_list) >= 2 and prices_list[0]:
            d["pct_change"] = round(
                (prices_list[-1] - prices_list[0]) / prices_list[0] * 100, 1
            )
        else:
            d["pct_change"] = None

    return grouped


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
