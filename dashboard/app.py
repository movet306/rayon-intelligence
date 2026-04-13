"""
dashboard/app.py  —  Rayon Tekstil Intelligence Platform

Constraints:
  • NO st.dataframe()   — pyarrow bypass; st.table() for small tables, HTML for styled ones
  • NO plotly.express   — plotly.graph_objects only
  • Clean light theme via injected CSS
  • All 4 tabs load without errors

Run (clean env):
    conda run -n rayon-dashboard streamlit run dashboard/app.py --server.port 8501
"""

import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import psycopg2
import streamlit as st
from dotenv import load_dotenv
from plotly.subplots import make_subplots

load_dotenv()

# ── Must be first Streamlit call ───────────────────────────────────────────────
st.set_page_config(
    page_title="Rayon Intelligence",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Layout ── */
.block-container { padding: 1.2rem 2rem 2rem !important; }
section[data-testid="stSidebar"] > div { padding-top: 1.5rem; }

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 14px 18px !important;
}
[data-testid="metric-container"] label {
    font-size: 12px !important;
    color: #64748b !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 22px !important;
    font-weight: 700 !important;
    color: #1e293b !important;
}

/* ── Tab bar ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 2px solid #e2e8f0;
}
.stTabs [data-baseweb="tab"] {
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 600;
    color: #64748b;
    border-radius: 6px 6px 0 0;
}
.stTabs [aria-selected="true"] {
    background: white !important;
    color: #1f77b4 !important;
    border-bottom: 2px solid #1f77b4 !important;
}

/* ── Section divider ── */
hr { border: none; border-top: 1px solid #e2e8f0; margin: 1rem 0; }

/* ── Plotly chart border ── */
.js-plotly-plot { border: 1px solid #e2e8f0; border-radius: 8px; }

/* ── st.table styling ── */
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead tr { background: #f1f5f9; }
th { padding: 8px 12px; text-align: left; font-weight: 600;
     color: #475569; border-bottom: 2px solid #e2e8f0; }
td { padding: 7px 12px; border-bottom: 1px solid #f1f5f9; color: #334155; }
tr:hover td { background: #f8fafc; }
</style>
""", unsafe_allow_html=True)

# ── Colour tokens ──────────────────────────────────────────────────────────────
C_BLUE   = "#1f77b4"
C_ORANGE = "#ff7f0e"
C_RED    = "#d62728"
C_GREEN  = "#2ca02c"
C_TEAL   = "#17becf"
C_GREY   = "#7f7f7f"
C_PURPLE = "#9467bd"

SIGNAL_COLORS = {
    "competitor_mention": C_ORANGE,
    "price_move":         C_GREEN,
    "price_signal":       C_BLUE,
    "capacity_change":    C_PURPLE,
    "regulation":         C_RED,
    "trend":              C_TEAL,
    "new_market":         "#8c564b",
    "fair_participation": "#e377c2",
    "other":              C_GREY,
}
SEVERITY_COLORS = {
    "alert":   C_RED,
    "warning": C_ORANGE,
    "info":    C_BLUE,
}
_PAL = [C_BLUE, C_ORANGE, C_GREEN, C_RED, C_PURPLE, C_TEAL, "#8c564b", "#e377c2"]

_CHART_BASE = dict(
    paper_bgcolor="white",
    plot_bgcolor="#fafafa",
    font=dict(color="#334155", size=12, family="sans-serif"),
    margin=dict(l=10, r=10, t=44, b=10),
    hovermode="x unified",
)
_GRID = "#e2e8f0"

# ── App constants ──────────────────────────────────────────────────────────────
RMB_USD_RATE = float(os.getenv("RMB_USD_RATE", "0.138"))

MATERIAL_LABELS = {
    "polyester_staple_fiber": "Polyester Staple Fibre",
    "polyester_poy":  "Polyester POY",
    "polyester_fdy":  "Polyester FDY",
    "polyester_dty":  "Polyester DTY",
    "polyester_yarn": "Polyester Yarn",
    "polyamide_fdy":  "Nylon FDY (PA6)",
    "pa6_chip":       "PA6 Chip",
    "pa66_chip":      "PA66 Chip",
    "cotton_lint":    "Cotton Lint",
    "cotton_yarn":    "Cotton Yarn",
    "adipic_acid":    "Adipic Acid",
}

HS_LABELS = {
    "5407": "HS 5407 — Woven synthetic filament",
    "5512": "HS 5512 — Woven ≥85% synth. staple",
    "5515": "HS 5515 — Other woven synth. staple",
    "6006": "HS 6006 — Technical knit",
    "6001": "HS 6001 — Pile/velour knit",
    "5402": "HS 5402 — Filament yarn",
    "5509": "HS 5509 — Staple yarn",
}

COUNTRY_NAMES = {
    "US": "USA",        "DE": "Germany",     "NL": "Netherlands", "GB": "UK",
    "FR": "France",     "IT": "Italy",       "ES": "Spain",       "PL": "Poland",
    "RU": "Russia",     "UA": "Ukraine",     "BY": "Belarus",     "KZ": "Kazakhstan",
    "RO": "Romania",    "BG": "Bulgaria",    "IQ": "Iraq",        "SA": "Saudi Arabia",
    "AE": "UAE",        "EG": "Egypt",       "MA": "Morocco",     "GE": "Georgia",
    "AZ": "Azerbaijan", "AM": "Armenia",     "UZ": "Uzbekistan",  "TM": "Turkmenistan",
    "IR": "Iran",       "IL": "Israel",      "GR": "Greece",      "CZ": "Czech Rep.",
    "SK": "Slovakia",   "HU": "Hungary",     "HR": "Croatia",     "RS": "Serbia",
    "PT": "Portugal",   "BE": "Belgium",     "SE": "Sweden",      "DK": "Denmark",
    "AT": "Austria",    "CH": "Switzerland", "CN": "China",       "TW": "Taiwan",
    "PK": "Pakistan",   "BD": "Bangladesh",  "IN": "India",       "VN": "Vietnam",
    "MX": "Mexico",     "BR": "Brazil",      "TR": "Turkey (re-export)",
    "NG": "Nigeria",    "ZA": "South Africa","TN": "Tunisia",     "DZ": "Algeria",
}

DB_URL = os.environ.get("DATABASE_URL", "")


# ── DB helpers — each query uses its own short-lived connection ────────────────

def _conn():
    return psycopg2.connect(DB_URL)


@st.cache_data(ttl=3600, show_spinner=False)
def q_market_signals(days_back: int, types_filter: tuple, sev_filter: tuple):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    sql = """
        SELECT ms.signal_type, ms.severity, ms.title, ms.body,
               ms.source_table,
               to_char(ms.detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS detected_at,
               c.name AS company_name
        FROM market_signals ms
        LEFT JOIN companies c ON ms.company_id = c.id
        WHERE ms.detected_at >= %s
        ORDER BY ms.detected_at DESC
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (cutoff,))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    # Build plain Python list-of-dicts — no pandas Arrow inference
    return [dict(zip(cols, row)) for row in rows], types_filter, sev_filter


@st.cache_data(ttl=3600, show_spinner=False)
def q_price_signals():
    sql = """
        SELECT material,
               to_char(period, 'YYYY-MM-DD') AS period,
               price_usd::float               AS price_usd,
               unit
        FROM price_signals
        WHERE source = 'sunsirs'
        ORDER BY material, period
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


@st.cache_data(ttl=3600, show_spinner=False)
def q_trade_top_destinations(hs_code: str):
    sql = """
        SELECT partner_country, SUM(value_usd)::float AS value_usd
        FROM trade_flows
        WHERE hs_code = %s AND flow_direction = 'export'
          AND period = (SELECT MAX(period) FROM trade_flows
                        WHERE hs_code = %s AND flow_direction = 'export')
          AND partner_country IS NOT NULL
        GROUP BY partner_country
        ORDER BY value_usd DESC LIMIT 12
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (hs_code, hs_code))
        rows = cur.fetchall()
    return [(COUNTRY_NAMES.get(r[0], r[0]), float(r[1])) for r in rows]


@st.cache_data(ttl=3600, show_spinner=False)
def q_trade_monthly_trend(hs_codes: tuple):
    placeholders = ",".join(["%s"] * len(hs_codes))
    sql = f"""
        SELECT hs_code,
               to_char(period, 'YYYY-MM') AS period,
               (SUM(value_usd) / 1e6)::float AS value_usd_mn
        FROM trade_flows
        WHERE hs_code IN ({placeholders})
          AND flow_direction = 'export'
          AND partner_country IS NOT NULL
        GROUP BY hs_code, period
        ORDER BY period, hs_code
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, list(hs_codes))
        rows = cur.fetchall()
    result = {}
    for hs, period, val in rows:
        result.setdefault(hs, {"periods": [], "values": []})
        result[hs]["periods"].append(period)
        result[hs]["values"].append(val)
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def q_trade_metrics(hs_code: str):
    sql_p = """
        SELECT to_char(period,'YYYY-MM') AS period, SUM(value_usd)::float AS total
        FROM trade_flows
        WHERE hs_code = %s AND flow_direction = 'export' AND partner_country IS NOT NULL
        GROUP BY period ORDER BY period DESC LIMIT 2
    """
    sql_t = """
        SELECT partner_country, SUM(value_usd)::float AS v
        FROM trade_flows
        WHERE hs_code = %s AND flow_direction = 'export'
          AND period = (SELECT MAX(period) FROM trade_flows
                        WHERE hs_code = %s AND flow_direction = 'export')
          AND partner_country IS NOT NULL
        GROUP BY partner_country ORDER BY v DESC LIMIT 1
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(sql_p, (hs_code,))
        periods = cur.fetchall()
        cur.execute(sql_t, (hs_code, hs_code))
        top = cur.fetchone()
    r = {}
    if periods:
        r["latest_period"] = periods[0][0]
        r["latest_total"]  = periods[0][1]
        if len(periods) > 1 and periods[1][1]:
            r["mom_pct"] = (periods[0][1] - periods[1][1]) / periods[1][1] * 100
    if top:
        r["top_dest"]     = COUNTRY_NAMES.get(top[0], top[0])
        r["top_dest_val"] = top[1]
    return r


@st.cache_data(ttl=3600, show_spinner=False)
def q_lescon_by_fabric():
    sql = """
        SELECT COALESCE(NULLIF(TRIM(fabric_type),''),'Unknown') AS fabric_type,
               COUNT(*)::int                                      AS tx_count,
               ROUND(SUM(miktar*unit_price_usd)::numeric,2)::float AS revenue_usd
        FROM lescon_sales
        WHERE NOT is_return AND unit_price_usd > 0
          AND unit_price_usd IS NOT NULL AND miktar IS NOT NULL
        GROUP BY 1 ORDER BY revenue_usd DESC
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        return cur.fetchall()   # list of (fabric_type, tx_count, revenue_usd)


@st.cache_data(ttl=3600, show_spinner=False)
def q_lescon_monthly():
    sql = """
        SELECT to_char(DATE_TRUNC('month',tarih),'YYYY-MM') AS month,
               ROUND(SUM(miktar*unit_price_usd)::numeric,2)::float AS revenue_usd
        FROM lescon_sales
        WHERE NOT is_return AND tarih IS NOT NULL
          AND unit_price_usd > 0 AND unit_price_usd IS NOT NULL AND miktar IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
    return [r[0] for r in rows], [r[1] for r in rows]   # months, revenues


@st.cache_data(ttl=3600, show_spinner=False)
def q_lescon_top_products():
    sql = """
        SELECT COALESCE(NULLIF(TRIM(urun_aciklamasi),''),'Unknown') AS product,
               COUNT(*)::int                                          AS tx_count,
               ROUND(SUM(miktar*unit_price_usd)::numeric,0)::float   AS revenue_usd
        FROM lescon_sales
        WHERE NOT is_return AND unit_price_usd > 0
          AND unit_price_usd IS NOT NULL AND miktar IS NOT NULL
        GROUP BY 1 ORDER BY tx_count DESC LIMIT 10
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        return cur.fetchall()   # (product, tx_count, revenue_usd)


@st.cache_data(ttl=3600, show_spinner=False)
def q_yarn_cost_trend():
    sql = """
        SELECT EXTRACT(YEAR FROM factory_entry_date)::int AS year,
               ROUND(AVG(unit_cost_usd)::numeric,4)::float AS avg_cost,
               COUNT(*)::int                               AS records
        FROM yarn_costs
        WHERE unit_cost_usd > 0 AND unit_cost_usd IS NOT NULL
          AND factory_entry_date IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        return cur.fetchall()   # (year, avg_cost, records)


@st.cache_data(ttl=3600, show_spinner=False)
def q_orders_by_supplier():
    sql = """
        SELECT COALESCE(supplier_clean, supplier_raw, 'Unknown') AS supplier,
               COALESCE(currency_clean, '?')                      AS currency,
               COUNT(*)::int                                       AS order_count,
               ROUND(SUM(qty_numeric)::numeric,0)::float          AS total_kg,
               ROUND(AVG(price_numeric)::numeric,4)::float        AS avg_price
        FROM orders
        WHERE record_status IS DISTINCT FROM 'exclude'
        GROUP BY 1,2 ORDER BY order_count DESC LIMIT 15
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        return cur.fetchall()   # (supplier, currency, order_count, total_kg, avg_price)


# ── Rendering utilities ────────────────────────────────────────────────────────

def _badge(label: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;background:{color};color:white;'
        f'padding:2px 9px;border-radius:4px;font-size:11px;font-weight:700;'
        f'letter-spacing:0.4px;text-transform:uppercase">'
        f'{label.replace("_"," ")}</span>'
    )


def _signal_card(row: dict) -> str:
    type_color = SIGNAL_COLORS.get(row["signal_type"], C_GREY)
    sev_color  = SEVERITY_COLORS.get(row["severity"],  C_BLUE)
    title      = (row["title"] or "")[:160]
    body       = row["body"] or ""
    src        = (row["source_table"] or "").replace("_", " ")
    dt         = row["detected_at"] or ""
    co_html    = (
        f'<div style="margin-top:5px;font-size:12px;font-weight:600;color:{type_color}">'
        f'&#128198; {row["company_name"]}</div>'
        if row.get("company_name") else ""
    )
    return (
        f'<div style="background:white;border:1px solid #e2e8f0;'
        f'border-left:3px solid {type_color};border-radius:0 6px 6px 0;'
        f'padding:12px 16px;margin:5px 0;">'
        f'<div style="display:flex;gap:6px;align-items:center;margin-bottom:7px;flex-wrap:wrap">'
        f'{_badge(row["signal_type"], type_color)}'
        f'{_badge(row["severity"], sev_color)}'
        f'<span style="margin-left:auto;font-size:11px;color:#94a3b8">{dt} · {src}</span>'
        f'</div>'
        f'<div style="font-weight:600;font-size:14px;color:#1e293b;margin-bottom:4px">{title}</div>'
        f'<div style="font-size:13px;color:#475569;line-height:1.55">{body}</div>'
        f'{co_html}'
        f'</div>'
    )


def _price_chart(xs, rmb_vals, title: str) -> go.Figure:
    usd_vals = [v * RMB_USD_RATE for v in rmb_vals]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=xs, y=rmb_vals, name="RMB/ton",
        line=dict(color=C_BLUE, width=2.5),
        hovertemplate="%{x}<br><b>%{y:,.0f} RMB/ton</b><extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=xs, y=usd_vals, name="USD/ton",
        line=dict(color=C_ORANGE, width=1.5, dash="dot"),
        hovertemplate="%{x}<br><b>%{y:,.0f} USD/ton</b><extra></extra>",
    ), secondary_y=True)
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#334155")),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        height=250,
        **_CHART_BASE,
    )
    fig.update_yaxes(title_text="RMB/ton", secondary_y=False, gridcolor=_GRID, tickformat=",")
    fig.update_yaxes(title_text="USD/ton", secondary_y=True,  gridcolor=_GRID, tickformat=",")
    fig.update_xaxes(gridcolor=_GRID)
    return fig


def _hbar(values, labels, title: str, colorscale: str, text_fmt=None,
          height=340) -> go.Figure:
    text = text_fmt or [str(v) for v in values]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        text=text, textposition="outside",
        marker=dict(color=values, colorscale=colorscale, showscale=False),
        hovertemplate="%{y}: %{x}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#334155")),
        yaxis=dict(autorange="reversed", gridcolor=_GRID),
        xaxis=dict(gridcolor=_GRID),
        height=height,
        **_CHART_BASE,
    )
    return fig


# ── Sidebar ────────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("## 🧵 Rayon Intelligence")
        st.caption("Rayon Tekstil Sanayi ve Dış Tic.")
        st.divider()
        st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        if st.button("↺  Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()


# ── Tab 1: Market Signals ──────────────────────────────────────────────────────

def tab_market_signals():
    st.subheader("Market Signals")

    c_win, c_type, c_sev = st.columns([1, 2, 2])
    with c_win:
        days_back = st.selectbox("Window", [7, 14, 30, 60, 90, 365],
                                 format_func=lambda d: f"Last {d}d", index=2)
    with c_type:
        types_sel = st.multiselect("Signal type", list(SIGNAL_COLORS.keys()),
                                   default=[], placeholder="All types",
                                   format_func=lambda t: t.replace("_"," ").title())
    with c_sev:
        sev_sel = st.multiselect("Severity", ["info","warning","alert"],
                                 default=[], placeholder="All severities")

    all_rows, _, _ = q_market_signals(days_back, tuple(types_sel), tuple(sev_sel))

    # Apply filters (already baked into cache key, but cache returns all — filter here)
    rows = all_rows
    if types_sel:
        rows = [r for r in rows if r["signal_type"] in types_sel]
    if sev_sel:
        rows = [r for r in rows if r["severity"] in sev_sel]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total signals", len(rows))
    m2.metric("Competitor mentions",
              sum(1 for r in rows if r["signal_type"] == "competitor_mention"))
    m3.metric("Alerts",   sum(1 for r in rows if r["severity"] == "alert"))
    m4.metric("Warnings", sum(1 for r in rows if r["severity"] == "warning"))

    st.divider()

    if not rows:
        st.info("No signals in this period. Try expanding the time window.")
        return

    st.markdown("".join(_signal_card(r) for r in rows), unsafe_allow_html=True)


# ── Tab 2: Price Intelligence ──────────────────────────────────────────────────

def tab_price_intelligence():
    st.subheader("Commodity Price Intelligence")
    st.caption("Source: SunSirs · RMB/ton (left axis) · USD/ton (right axis, dotted)")

    price_rows = q_price_signals()
    if not price_rows:
        st.info("No price data yet.")
        return

    # Group by material
    by_mat: dict = {}
    for r in price_rows:
        by_mat.setdefault(r["material"], {"periods": [], "prices": []})
        by_mat[r["material"]]["periods"].append(r["period"])
        by_mat[r["material"]]["prices"].append(r["price_usd"])

    def _delta(prices):
        if len(prices) < 2:
            return None
        return (prices[-1] - prices[0]) / prices[0] * 100 if prices[0] else None

    # Row 1: Polyester Staple + Nylon FDY
    c1, c2 = st.columns(2)
    for col, mat in [(c1, "polyester_staple_fiber"), (c2, "polyamide_fdy")]:
        with col:
            label = MATERIAL_LABELS.get(mat, mat)
            d = by_mat.get(mat)
            if d:
                cur   = d["prices"][-1]
                delta = _delta(d["prices"])
                st.metric(
                    label,
                    f"{cur:,.0f} RMB  /  {cur*RMB_USD_RATE:,.0f} USD  (per ton)",
                    delta=f"{delta:+.1f}% period change" if delta is not None else None,
                    delta_color="inverse",
                )
                st.plotly_chart(
                    _price_chart(d["periods"], d["prices"], label),
                    use_container_width=True,
                )
            else:
                st.info(f"No data for {label}")

    st.divider()

    # Row 2: Cotton Lint + PA6 vs PA66
    c3, c4 = st.columns(2)
    with c3:
        mat   = "cotton_lint"
        label = MATERIAL_LABELS.get(mat, mat)
        d = by_mat.get(mat)
        if d:
            cur   = d["prices"][-1]
            delta = _delta(d["prices"])
            st.metric(
                label,
                f"{cur:,.0f} RMB  /  {cur*RMB_USD_RATE:,.0f} USD  (per ton)",
                delta=f"{delta:+.1f}% period change" if delta is not None else None,
                delta_color="inverse",
            )
            st.plotly_chart(
                _price_chart(d["periods"], d["prices"], label),
                use_container_width=True,
            )
        else:
            st.info(f"No data for {label}")

    with c4:
        fig = go.Figure()
        for mat, color, name in [
            ("pa6_chip",  C_BLUE,   "PA6 Chip"),
            ("pa66_chip", C_ORANGE, "PA66 Chip"),
        ]:
            d = by_mat.get(mat)
            if d:
                fig.add_trace(go.Scatter(
                    x=d["periods"], y=d["prices"],
                    name=name, mode="lines+markers",
                    line=dict(color=color, width=2.5),
                    hovertemplate=f"{name}: %{{y:,.0f}} RMB/ton<extra></extra>",
                ))
        if fig.data:
            fig.update_layout(
                title=dict(text="PA6 Chip vs PA66 Chip (RMB/ton)",
                           font=dict(size=13, color="#334155")),
                legend=dict(bgcolor="rgba(0,0,0,0)"),
                height=250,
                yaxis=dict(title="RMB/ton", gridcolor=_GRID, tickformat=","),
                xaxis=dict(gridcolor=_GRID),
                **_CHART_BASE,
            )
            pa1, pa2 = st.columns(2)
            for c_, mat, name in [(pa1,"pa6_chip","PA6"), (pa2,"pa66_chip","PA66")]:
                d = by_mat.get(mat)
                if d:
                    c_.metric(f"{name} Chip", f"{d['prices'][-1]:,.0f} RMB/ton")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No PA chip data yet")

    st.divider()

    # Latest prices table — small, use st.table
    with st.expander("All materials — latest prices"):
        table_data = {"Material": [], "Date": [], "Price": [], "Unit": [], "USD equiv./ton": []}
        seen = set()
        for r in reversed(price_rows):   # reversed = newest first after groupby
            if r["material"] not in seen:
                seen.add(r["material"])
                label = MATERIAL_LABELS.get(r["material"], r["material"])
                price = r["price_usd"]
                usd_eq = f"{price * RMB_USD_RATE:,.0f}" if "RMB" in r["unit"] else "—"
                table_data["Material"].append(label)
                table_data["Date"].append(r["period"])
                table_data["Price"].append(f"{price:,.2f}")
                table_data["Unit"].append(r["unit"])
                table_data["USD equiv./ton"].append(usd_eq)
        st.table(pd.DataFrame(table_data))


# ── Tab 3: Export Intelligence ─────────────────────────────────────────────────

def tab_export_intelligence():
    st.subheader("Turkey Textile Export Intelligence")
    st.caption("Source: UN Comtrade · reporter: Turkey · flow: export · monthly")

    m5407 = q_trade_metrics("5407")
    m6006 = q_trade_metrics("6006")
    m1, m2, m3, m4 = st.columns(4)
    if m5407:
        m1.metric(
            f"HS 5407 ({m5407.get('latest_period','—')})",
            f"${m5407.get('latest_total',0)/1e6:.1f}M",
            delta=f"{m5407['mom_pct']:+.1f}% MoM" if "mom_pct" in m5407 else None,
        )
        m2.metric("Top dest. (5407)", m5407.get("top_dest","—"))
    if m6006:
        m3.metric(
            f"HS 6006 ({m6006.get('latest_period','—')})",
            f"${m6006.get('latest_total',0)/1e6:.1f}M",
            delta=f"{m6006['mom_pct']:+.1f}% MoM" if "mom_pct" in m6006 else None,
        )
        m4.metric("Top dest. (6006)", m6006.get("top_dest","—"))

    st.divider()

    # Top destinations
    hs_sel = st.selectbox("HS code", list(HS_LABELS.keys()),
                          format_func=lambda k: HS_LABELS[k], index=0)
    dest_rows = q_trade_top_destinations(hs_sel)
    if dest_rows:
        top10    = dest_rows[:10]
        names    = [r[0] for r in top10]
        vals     = [r[1] for r in top10]
        texts    = [f"${v/1e6:.1f}M" for v in vals]
        fig_dest = _hbar(vals, names, f"Top 10 destinations — {HS_LABELS[hs_sel]} (latest month)",
                         "Blues", texts, height=360)
        st.plotly_chart(fig_dest, use_container_width=True)
    else:
        st.info(f"No trade data for {hs_sel}")

    st.divider()

    # Monthly trend
    hs_trend = st.multiselect("HS codes for trend", list(HS_LABELS.keys()),
                              default=["5407","6006"],
                              format_func=lambda k: HS_LABELS[k])
    if hs_trend:
        trend_data = q_trade_monthly_trend(tuple(hs_trend))
        if trend_data:
            fig_line = go.Figure()
            for i, hs in enumerate(hs_trend):
                d = trend_data.get(hs)
                if not d:
                    continue
                fig_line.add_trace(go.Scatter(
                    x=d["periods"], y=d["values"],
                    name=HS_LABELS.get(hs, hs),
                    mode="lines+markers",
                    line=dict(color=_PAL[i % len(_PAL)], width=2),
                    marker=dict(size=5),
                    hovertemplate=f"{HS_LABELS.get(hs,hs)}: %{{y:.1f}}M USD<extra></extra>",
                ))
            fig_line.update_layout(
                title=dict(text="Monthly export value — Turkey",
                           font=dict(size=13, color="#334155")),
                legend=dict(bgcolor="rgba(0,0,0,0)", title_text=""),
                height=360,
                yaxis=dict(gridcolor=_GRID, tickprefix="$", ticksuffix="M",
                           title="USD million"),
                xaxis=dict(gridcolor=_GRID, tickangle=-30),
                **_CHART_BASE,
            )
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("No trend data for selected HS codes")
    else:
        st.info("Select at least one HS code above")


# ── Tab 4: Internal Data ───────────────────────────────────────────────────────

def tab_internal_data():
    st.subheader("Internal Business Data")
    inner1, inner2, inner3 = st.tabs(["📦 Lescon Sales", "🧶 Yarn Costs", "🛒 Orders"])

    # ── Lescon Sales ─────────────────────────────────────────────────────────────
    with inner1:
        fab_rows = q_lescon_by_fabric()
        months, rev_by_month = q_lescon_monthly()

        if not fab_rows:
            st.info("No Lescon sales data.")
        else:
            total_rev = sum(r[2] for r in fab_rows)
            total_tx  = sum(r[1] for r in fab_rows)
            s1, s2, s3 = st.columns(3)
            s1.metric("Total revenue (excl. returns)", f"${total_rev:,.0f}")
            s2.metric("Total transactions", f"{total_tx:,}")
            s3.metric("Avg transaction value",
                      f"${total_rev/total_tx:,.0f}" if total_tx else "—")

            fabs = [r[0] for r in fab_rows]
            revs = [r[2] for r in fab_rows]
            txs  = [r[1] for r in fab_rows]

            ca, cb = st.columns(2)
            with ca:
                st.plotly_chart(
                    _hbar(revs, fabs, "Revenue by fabric type (USD)", "Teal",
                          [f"${v/1e3:.0f}K" for v in revs]),
                    use_container_width=True,
                )
            with cb:
                st.plotly_chart(
                    _hbar(txs, fabs, "Transaction count by fabric type", "Blues",
                          [str(v) for v in txs]),
                    use_container_width=True,
                )

            if months:
                fig_mon = go.Figure(go.Scatter(
                    x=months, y=rev_by_month,
                    mode="lines", fill="tozeroy",
                    line=dict(color=C_BLUE, width=2.5),
                    fillcolor="rgba(31,119,180,0.10)",
                    hovertemplate="%{x}: $%{y:,.0f}<extra></extra>",
                ))
                fig_mon.update_layout(
                    title=dict(text="Monthly revenue (Lescon account)",
                               font=dict(size=13, color="#334155")),
                    height=270,
                    yaxis=dict(gridcolor=_GRID, tickprefix="$", title="Revenue (USD)"),
                    xaxis=dict(gridcolor=_GRID, tickangle=-30),
                    **_CHART_BASE,
                )
                st.plotly_chart(fig_mon, use_container_width=True)

            prod_rows = q_lescon_top_products()
            if prod_rows:
                st.markdown("**Top 10 products by transaction count**")
                st.table(pd.DataFrame(
                    [(r[0], r[1], f"${r[2]:,.0f}") for r in prod_rows],
                    columns=["Product", "Transactions", "Revenue (USD)"],
                ))

    # ── Yarn Costs ───────────────────────────────────────────────────────────────
    with inner2:
        yarn_rows = q_yarn_cost_trend()
        if not yarn_rows:
            st.info("No yarn cost data.")
        else:
            first, last = yarn_rows[0], yarn_rows[-1]
            chg = (last[1] - first[1]) / first[1] * 100 if first[1] else 0
            y1, y2, y3 = st.columns(3)
            y1.metric(f"Avg cost {last[0]}",  f"${last[1]:.2f}/MT")
            y2.metric(f"Avg cost {first[0]}", f"${first[1]:.2f}/MT")
            y3.metric(f"Change {first[0]} → {last[0]}", f"{chg:+.1f}%",
                      delta_color="inverse")

            years = [str(r[0]) for r in yarn_rows]
            costs = [r[1]      for r in yarn_rows]
            recs  = [r[2]      for r in yarn_rows]

            fig_yarn = go.Figure(go.Bar(
                x=years, y=costs,
                marker_color=C_BLUE,
                text=[f"${v:.2f}" for v in costs],
                textposition="outside",
                customdata=recs,
                hovertemplate="Year %{x}<br><b>$%{y:.2f}/MT</b>"
                              "<br>Records: %{customdata}<extra></extra>",
            ))
            fig_yarn.update_layout(
                title=dict(text="Average yarn unit cost (USD/MT) by year",
                           font=dict(size=13, color="#334155")),
                height=360,
                yaxis=dict(gridcolor=_GRID, tickprefix="$", title="USD/MT"),
                xaxis=dict(title="Year"),
                **_CHART_BASE,
            )
            st.plotly_chart(fig_yarn, use_container_width=True)

            with st.expander("Data by year"):
                st.table(pd.DataFrame(
                    [(r[0], f"${r[1]:.4f}", r[2]) for r in yarn_rows],
                    columns=["Year", "Avg cost (USD/MT)", "Records"],
                ))

    # ── Orders ──────────────────────────────────────────────────────────────────
    with inner3:
        sup_rows = q_orders_by_supplier()
        if not sup_rows:
            st.info("No orders data.")
        else:
            o1, o2 = st.columns(2)
            o1.metric("Total orders", "1,484")
            o2.metric("Distinct suppliers", str(len({r[0] for r in sup_rows})))

            top12 = sup_rows[:12]
            sups  = [r[0] for r in top12]
            ords  = [r[2] for r in top12]
            fig_sup = _hbar(ords, sups, "Top suppliers by order count",
                            "Purples", [str(v) for v in ords], height=420)
            st.plotly_chart(fig_sup, use_container_width=True)

            with st.expander("Full supplier table"):
                st.table(pd.DataFrame(
                    [(r[0], r[1], r[2],
                      f"{r[3]:,.0f}" if r[3] else "—",
                      f"{r[4]:.4f}" if r[4] else "—")
                     for r in sup_rows],
                    columns=["Supplier","Currency","# Orders","Total KG","Avg price"],
                ))


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not DB_URL:
        st.error("DATABASE_URL not set — add it to .env")
        st.stop()

    render_sidebar()

    tab1, tab2, tab3, tab4 = st.tabs([
        "📡  Market Signals",
        "💹  Price Intelligence",
        "🌍  Export Intelligence",
        "🏭  Internal Data",
    ])
    with tab1:
        tab_market_signals()
    with tab2:
        tab_price_intelligence()
    with tab3:
        tab_export_intelligence()
    with tab4:
        tab_internal_data()


if __name__ == "__main__":
    main()
