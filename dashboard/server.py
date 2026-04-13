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
        """SELECT price::float AS price, 'RMB/ton' AS unit
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
def prices():
    """
    Query price_metrics_daily (gold layer) for all daily-frequency materials.
    Returns JSON keyed by material slug:
      { material: { latest: {...}, series: [{date, price, ma7, ma30, normalized_idx}] } }
    """
    rows = _rows("""
        SELECT material,
               to_char(metric_date, 'YYYY-MM-DD') AS metric_date,
               price::float,
               change_1d::float,
               change_7d::float,
               change_30d::float,
               ma7::float,
               ma30::float,
               volatility_7d::float,
               normalized_idx::float,
               trend_direction
        FROM price_metrics_daily
        WHERE frequency = 'daily'
          AND metric_date >= NOW() - INTERVAL '90 days'
        ORDER BY material, metric_date
    """)

    grouped: dict = {}
    for r in rows:
        m = r["material"]
        if m not in grouped:
            grouped[m] = {"latest": None, "series": []}
        grouped[m]["series"].append({
            "date":          r["metric_date"],
            "price":         r["price"],
            "ma7":           r["ma7"],
            "ma30":          r["ma30"],
            "normalized_idx": r["normalized_idx"],
        })
        grouped[m]["latest"] = {
            "price":          r["price"],
            "change_1d":      r["change_1d"],
            "change_7d":      r["change_7d"],
            "change_30d":     r["change_30d"],
            "volatility_7d":  r["volatility_7d"],
            "trend_direction": r["trend_direction"],
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
    latest = _rows("""
        WITH counts AS (
            SELECT material, COUNT(*) AS data_points
            FROM price_metrics_daily
            WHERE frequency = 'daily'
            GROUP BY material
        )
        SELECT DISTINCT ON (pmd.material)
            pmd.material,
            pmd.price::float         AS price,
            pmd.change_7d::float     AS change_7d,
            pmd.change_30d::float    AS change_30d,
            pmd.volatility_7d::float AS volatility_7d,
            pmd.trend_direction,
            c.data_points::int       AS data_points
        FROM price_metrics_daily pmd
        JOIN counts c ON c.material = pmd.material
        WHERE pmd.frequency = 'daily'
        ORDER BY pmd.material, pmd.metric_date DESC
    """)

    # Average volatility across all materials that have it
    vols = [r["volatility_7d"] for r in latest if r["volatility_7d"] is not None]
    avg_vol = sum(vols) / len(vols) if vols else None

    by_mat = {r["material"]: r for r in latest}
    signals = []

    for r in latest:
        if (r["data_points"] or 0) < 7:
            continue
        mat   = r["material"]
        label = MATERIAL_LABELS.get(mat, mat)
        c7    = r["change_7d"]
        vol   = r["volatility_7d"]

        if c7 is not None and c7 > 3:
            signals.append({
                "material": mat, "type": "rise", "severity": "warning",
                "text": f"{label} 7 günde +{c7:.1f}% yükseldi",
            })
        elif c7 is not None and c7 < -3:
            signals.append({
                "material": mat, "type": "drop", "severity": "warning",
                "text": f"{label} 7 günde {c7:.1f}% geriledi",
            })

        if vol is not None and avg_vol and avg_vol > 0 and vol > 2 * avg_vol:
            signals.append({
                "material": mat, "type": "volatility", "severity": "info",
                "text": f"{label} yüksek volatilite (7G σ={vol:.1f})",
            })

    # Spread signal: polyamide_fdy / polyester_fdy ratio change vs 30d ago
    pa  = by_mat.get("polyamide_fdy")
    pf  = by_mat.get("polyester_fdy")
    if (pa and pf
            and (pa["data_points"] or 0) >= 7 and (pf["data_points"] or 0) >= 7
            and pa["price"] and pf["price"] and pf["price"] != 0
            and pa["change_30d"] is not None and pf["change_30d"] is not None):
        ratio_now  = pa["price"] / pf["price"]
        pa_30d     = pa["price"]  / (1 + pa["change_30d"]  / 100)
        poly_30d   = pf["price"]  / (1 + pf["change_30d"]  / 100)
        if poly_30d != 0:
            ratio_30d   = pa_30d / poly_30d
            spread_chg  = (ratio_now - ratio_30d) / ratio_30d * 100
            if abs(spread_chg) > 5:
                direction = "genişledi" if spread_chg > 0 else "daraldı"
                signals.append({
                    "material": "polyamide_fdy/polyester_fdy",
                    "type": "spread", "severity": "info",
                    "text": (f"Naylon/Polyester FDY fiyat makası {direction} "
                             f"({spread_chg:+.1f}%)"),
                })

    return signals


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
