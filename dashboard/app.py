"""
dashboard/app.py
Rayon Tekstil Intelligence Platform — Streamlit dashboard.

Tabs:
  1. Market Signals   — latest signals with filters
  2. Price Intelligence — commodity price charts from price_signals
  3. Export Intelligence — Turkey textile export data from trade_flows
  4. Internal Data    — Lescon sales + yarn cost trends

Run:
    streamlit run dashboard/app.py
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

# ── Page config (must be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="Rayon Intelligence",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Colour palette ─────────────────────────────────────────────────────────────
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
_PALETTE = [C_BLUE, C_ORANGE, C_GREEN, C_RED, C_PURPLE, C_TEAL, "#8c564b", "#e377c2"]

# Shared plotly layout for light theme
_CHART = dict(
    paper_bgcolor="white",
    plot_bgcolor="#fafafa",
    font=dict(color="#333", size=12),
    margin=dict(l=10, r=10, t=40, b=10),
    hovermode="x unified",
)
_GRID = "#e5e5e5"

# ── Constants ──────────────────────────────────────────────────────────────────
RMB_USD_RATE = float(os.getenv("RMB_USD_RATE", "0.138"))

MATERIAL_LABELS = {
    "polyester_staple_fiber": "Polyester Staple Fibre",
    "polyester_poy":          "Polyester POY",
    "polyester_fdy":          "Polyester FDY",
    "polyester_dty":          "Polyester DTY",
    "polyester_yarn":         "Polyester Yarn",
    "polyamide_fdy":          "Nylon FDY (PA6)",
    "pa6_chip":               "PA6 Chip",
    "pa66_chip":              "PA66 Chip",
    "cotton_lint":            "Cotton Lint",
    "cotton_yarn":            "Cotton Yarn",
    "adipic_acid":            "Adipic Acid",
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


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _conn():
    return psycopg2.connect(DB_URL)


@st.cache_data(ttl=3600, show_spinner=False)
def q_market_signals(days_back: int, types_filter: tuple, sev_filter: tuple) -> pd.DataFrame:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    sql = """
        SELECT ms.id, ms.signal_type, ms.severity, ms.title, ms.body,
               ms.source_table, ms.detected_at, c.name AS company_name
        FROM market_signals ms
        LEFT JOIN companies c ON ms.company_id = c.id
        WHERE ms.detected_at >= %s
        ORDER BY ms.detected_at DESC
    """
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn, params=(cutoff,))
    if types_filter:
        df = df[df["signal_type"].isin(types_filter)]
    if sev_filter:
        df = df[df["severity"].isin(sev_filter)]
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def q_price_signals() -> pd.DataFrame:
    sql = """
        SELECT material, period::text AS period, price_usd::float AS price_usd, unit
        FROM price_signals WHERE source = 'sunsirs'
        ORDER BY material, period
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=3600, show_spinner=False)
def q_trade_top_destinations(hs_code: str) -> pd.DataFrame:
    sql = """
        SELECT partner_country, SUM(value_usd)::float AS value_usd
        FROM trade_flows
        WHERE hs_code = %s AND flow_direction = 'export'
          AND period = (SELECT MAX(period) FROM trade_flows
                        WHERE hs_code = %s AND flow_direction = 'export')
          AND partner_country IS NOT NULL
        GROUP BY partner_country ORDER BY value_usd DESC LIMIT 12
    """
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn, params=(hs_code, hs_code))
    df["country_name"] = df["partner_country"].map(lambda c: COUNTRY_NAMES.get(c, c))
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def q_trade_monthly_trend(hs_codes: tuple) -> pd.DataFrame:
    placeholders = ",".join(["%s"] * len(hs_codes))
    sql = f"""
        SELECT hs_code, period::text AS period,
               (SUM(value_usd) / 1e6)::float AS value_usd_mn
        FROM trade_flows
        WHERE hs_code IN ({placeholders})
          AND flow_direction = 'export' AND partner_country IS NOT NULL
        GROUP BY hs_code, period ORDER BY period, hs_code
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn, params=list(hs_codes))


@st.cache_data(ttl=3600, show_spinner=False)
def q_trade_metrics(hs_code: str) -> dict:
    sql_periods = """
        SELECT period::text AS period, SUM(value_usd)::float AS total_usd
        FROM trade_flows
        WHERE hs_code = %s AND flow_direction = 'export' AND partner_country IS NOT NULL
        GROUP BY period ORDER BY period DESC LIMIT 2
    """
    sql_top = """
        SELECT partner_country, SUM(value_usd)::float AS v
        FROM trade_flows
        WHERE hs_code = %s AND flow_direction = 'export'
          AND period = (SELECT MAX(period) FROM trade_flows
                        WHERE hs_code = %s AND flow_direction = 'export')
          AND partner_country IS NOT NULL
        GROUP BY partner_country ORDER BY v DESC LIMIT 1
    """
    with _conn() as conn:
        df_p = pd.read_sql_query(sql_periods, conn, params=(hs_code,))
        df_t = pd.read_sql_query(sql_top, conn, params=(hs_code, hs_code))

    result: dict = {}
    if not df_p.empty:
        result["latest_period"] = str(df_p.iloc[0]["period"])[:7]   # "YYYY-MM"
        result["latest_total"]  = float(df_p.iloc[0]["total_usd"])
        if len(df_p) > 1:
            prev = float(df_p.iloc[1]["total_usd"])
            result["mom_pct"] = (result["latest_total"] - prev) / prev * 100 if prev else 0
    if not df_t.empty:
        iso = df_t.iloc[0]["partner_country"]
        result["top_dest"]     = COUNTRY_NAMES.get(iso, iso)
        result["top_dest_val"] = float(df_t.iloc[0]["v"])
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def q_lescon_by_fabric() -> pd.DataFrame:
    sql = """
        SELECT COALESCE(NULLIF(TRIM(fabric_type),''),'Unknown') AS fabric_type,
               COUNT(*)::int AS tx_count,
               ROUND(SUM(miktar*unit_price_usd)::numeric,2)::float AS revenue_usd
        FROM lescon_sales
        WHERE NOT is_return AND unit_price_usd > 0
          AND unit_price_usd IS NOT NULL AND miktar IS NOT NULL
        GROUP BY 1 ORDER BY revenue_usd DESC
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=3600, show_spinner=False)
def q_lescon_monthly() -> pd.DataFrame:
    sql = """
        SELECT DATE_TRUNC('month',tarih)::date::text AS month,
               ROUND(SUM(miktar*unit_price_usd)::numeric,2)::float AS revenue_usd,
               COUNT(*)::int AS tx_count
        FROM lescon_sales
        WHERE NOT is_return AND tarih IS NOT NULL
          AND unit_price_usd > 0 AND unit_price_usd IS NOT NULL AND miktar IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=3600, show_spinner=False)
def q_lescon_top_products() -> pd.DataFrame:
    sql = """
        SELECT COALESCE(NULLIF(TRIM(urun_aciklamasi),''),'Unknown') AS product,
               COUNT(*)::int AS tx_count,
               ROUND(SUM(miktar*unit_price_usd)::numeric,2)::float AS revenue_usd
        FROM lescon_sales
        WHERE NOT is_return AND unit_price_usd > 0
          AND unit_price_usd IS NOT NULL AND miktar IS NOT NULL
        GROUP BY 1 ORDER BY tx_count DESC LIMIT 10
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=3600, show_spinner=False)
def q_yarn_cost_trend() -> pd.DataFrame:
    sql = """
        SELECT EXTRACT(YEAR FROM factory_entry_date)::int AS year,
               ROUND(AVG(unit_cost_usd)::numeric,4)::float AS avg_cost_usd_per_mt,
               COUNT(*)::int AS records
        FROM yarn_costs
        WHERE unit_cost_usd > 0 AND unit_cost_usd IS NOT NULL
          AND factory_entry_date IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=3600, show_spinner=False)
def q_orders_by_supplier() -> pd.DataFrame:
    sql = """
        SELECT COALESCE(supplier_clean,supplier_raw,'Unknown') AS supplier,
               currency_clean,
               COUNT(*)::int AS order_count,
               ROUND(SUM(qty_numeric)::numeric,0)::float AS total_kg,
               ROUND(AVG(price_numeric)::numeric,4)::float AS avg_price
        FROM orders
        WHERE record_status IS DISTINCT FROM 'exclude'
        GROUP BY 1,2 ORDER BY order_count DESC LIMIT 15
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


# ── Rendering helpers ──────────────────────────────────────────────────────────

def _html_table(df: pd.DataFrame) -> None:
    """Render a DataFrame as a plain HTML table — avoids pyarrow used by st.dataframe()."""
    cols = list(df.columns)
    th_style = (
        "text-align:left;padding:6px 12px;background:#f0f4f8;"
        "border-bottom:2px solid #d0d7de;font-size:12px;white-space:nowrap"
    )
    td_style = "padding:5px 12px;border-bottom:1px solid #eaecef;font-size:12px"
    header = "".join(f'<th style="{th_style}">{c}</th>' for c in cols)
    rows_html = ""
    for i, (_, row) in enumerate(df.iterrows()):
        bg = "white" if i % 2 == 0 else "#f8f9fa"
        cells = "".join(f'<td style="{td_style};background:{bg}">{v}</td>' for v in row)
        rows_html += f"<tr>{cells}</tr>"
    st.markdown(
        f'<div style="overflow-x:auto">'
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>{header}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table></div>',
        unsafe_allow_html=True,
    )


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:white;padding:2px 8px;'
        f'border-radius:3px;font-size:11px;font-weight:600;'
        f'letter-spacing:0.4px">{text.replace("_"," ").upper()}</span>'
    )


def _signal_card(row: pd.Series) -> str:
    type_color = SIGNAL_COLORS.get(str(row["signal_type"]), C_GREY)
    sev_color  = SEVERITY_COLORS.get(str(row["severity"]), C_BLUE)
    raw_dt     = row["detected_at"]
    try:
        dt_str = pd.to_datetime(raw_dt).strftime("%Y-%m-%d %H:%M")
    except Exception:
        dt_str = str(raw_dt)[:16]
    title   = str(row["title"] or "")[:140]
    body    = str(row["body"]  or "")
    src     = str(row.get("source_table") or "").replace("_", " ")
    co_html = ""
    if row.get("company_name"):
        co_html = (
            f'<div style="margin-top:4px;color:{type_color};font-size:12px;font-weight:600">'
            f'&#128198; {row["company_name"]}</div>'
        )
    return (
        f'<div style="background:white;border:1px solid #e0e0e0;'
        f'border-left:3px solid {type_color};padding:11px 15px;margin:4px 0;border-radius:0 5px 5px 0">'
        f'<div style="display:flex;gap:6px;align-items:center;margin-bottom:6px;flex-wrap:wrap">'
        f'{_badge(row["signal_type"], type_color)}'
        f'{_badge(row["severity"], sev_color)}'
        f'<span style="color:#888;font-size:11px;margin-left:auto">{dt_str} · {src}</span>'
        f'</div>'
        f'<div style="font-weight:600;font-size:13px;color:#1a1a2e;margin-bottom:3px">{title}</div>'
        f'<div style="color:#555;font-size:12px;line-height:1.5">{body}</div>'
        f'{co_html}</div>'
    )


def _price_chart(df_mat: pd.DataFrame, title: str) -> go.Figure:
    """Dual-axis price chart: RMB/ton (left) + USD/ton (right)."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    rmb = [float(v) for v in df_mat["price_usd"]]
    usd = [v * RMB_USD_RATE for v in rmb]
    xs  = df_mat["period"].tolist()

    fig.add_trace(
        go.Scatter(x=xs, y=rmb, name="RMB/ton",
                   line=dict(color=C_BLUE, width=2),
                   hovertemplate="%{x}<br><b>%{y:,.0f} RMB/ton</b><extra></extra>"),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=xs, y=usd, name="USD/ton",
                   line=dict(color=C_ORANGE, width=1.5, dash="dot"),
                   hovertemplate="%{x}<br><b>%{y:,.0f} USD/ton</b><extra></extra>"),
        secondary_y=True,
    )
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#333")),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        height=240,
        **_CHART,
    )
    fig.update_yaxes(title_text="RMB/ton", secondary_y=False,
                     gridcolor=_GRID, tickformat=",")
    fig.update_yaxes(title_text="USD/ton", secondary_y=True,
                     gridcolor=_GRID, tickformat=",")
    fig.update_xaxes(gridcolor=_GRID)
    return fig


def _price_delta(df_mat: pd.DataFrame):
    if df_mat.empty:
        return None, None
    vals  = [float(v) for v in df_mat["price_usd"]]
    cur   = vals[-1]
    first = vals[0]
    delta = (cur - first) / first * 100 if first else None
    return cur, delta


# ── Sidebar ────────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.title("🧵 Rayon Intelligence")
        st.caption("Rayon Tekstil Sanayi ve Dış Tic.")
        st.divider()
        st.caption(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        if st.button("↺  Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()


# ── Tab 1: Market Signals ──────────────────────────────────────────────────────

def tab_market_signals():
    st.subheader("Market Signals")

    col_days, col_types, col_sev = st.columns([1, 2, 2])
    with col_days:
        days_back = st.selectbox(
            "Time window", [7, 14, 30, 60, 90, 365],
            format_func=lambda d: f"Last {d} days", index=2,
        )
    with col_types:
        types_sel = st.multiselect(
            "Signal type", list(SIGNAL_COLORS.keys()), default=[],
            placeholder="All types",
            format_func=lambda t: t.replace("_", " ").title(),
        )
    with col_sev:
        sev_sel = st.multiselect(
            "Severity", ["info", "warning", "alert"],
            default=[], placeholder="All severities",
        )

    df = q_market_signals(days_back=days_back,
                          types_filter=tuple(types_sel),
                          sev_filter=tuple(sev_sel))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total signals", len(df))
    m2.metric("Competitor mentions",
              int((df["signal_type"] == "competitor_mention").sum()))
    m3.metric("Alerts",   int((df["severity"] == "alert").sum()))
    m4.metric("Warnings", int((df["severity"] == "warning").sum()))

    st.divider()

    if df.empty:
        st.info("No signals in this period. Try expanding the time window.")
        return

    st.markdown(
        "\n".join(_signal_card(row) for _, row in df.iterrows()),
        unsafe_allow_html=True,
    )


# ── Tab 2: Price Intelligence ──────────────────────────────────────────────────

def tab_price_intelligence():
    st.subheader("Commodity Price Intelligence")
    st.caption("Source: SunSirs · prices in RMB/ton · right axis shows USD equivalent")

    df_all = q_price_signals()
    if df_all.empty:
        st.info("No price data yet.")
        return

    # Row 1: Polyester Staple + Nylon FDY
    c1, c2 = st.columns(2)
    for col, mat in [(c1, "polyester_staple_fiber"), (c2, "polyamide_fdy")]:
        with col:
            label  = MATERIAL_LABELS.get(mat, mat)
            df_mat = df_all[df_all["material"] == mat].copy()
            cur, delta = _price_delta(df_mat)
            if cur is not None:
                st.metric(
                    label,
                    f"{cur:,.0f} RMB  /  {cur*RMB_USD_RATE:,.0f} USD  (per ton)",
                    delta=f"{delta:+.1f}% vs period start" if delta is not None else None,
                    delta_color="inverse",
                )
                st.plotly_chart(_price_chart(df_mat, label), use_container_width=True)
            else:
                st.info(f"No data for {label}")

    st.divider()

    # Row 2: Cotton Lint + PA6 vs PA66
    c3, c4 = st.columns(2)
    with c3:
        mat   = "cotton_lint"
        label = MATERIAL_LABELS.get(mat, mat)
        df_mat = df_all[df_all["material"] == mat].copy()
        cur, delta = _price_delta(df_mat)
        if cur is not None:
            st.metric(
                label,
                f"{cur:,.0f} RMB  /  {cur*RMB_USD_RATE:,.0f} USD  (per ton)",
                delta=f"{delta:+.1f}% vs period start" if delta is not None else None,
                delta_color="inverse",
            )
            st.plotly_chart(_price_chart(df_mat, label), use_container_width=True)
        else:
            st.info(f"No data for {label}")

    with c4:
        df_pa6  = df_all[df_all["material"] == "pa6_chip"].copy()
        df_pa66 = df_all[df_all["material"] == "pa66_chip"].copy()
        if not df_pa6.empty or not df_pa66.empty:
            fig = go.Figure()
            if not df_pa6.empty:
                cur6, _ = _price_delta(df_pa6)
                fig.add_trace(go.Scatter(
                    x=df_pa6["period"].tolist(),
                    y=[float(v) for v in df_pa6["price_usd"]],
                    name="PA6 Chip", mode="lines+markers",
                    line=dict(color=C_BLUE, width=2),
                    hovertemplate="PA6: %{y:,.0f} RMB/ton<extra></extra>",
                ))
            if not df_pa66.empty:
                cur66, _ = _price_delta(df_pa66)
                fig.add_trace(go.Scatter(
                    x=df_pa66["period"].tolist(),
                    y=[float(v) for v in df_pa66["price_usd"]],
                    name="PA66 Chip", mode="lines+markers",
                    line=dict(color=C_ORANGE, width=2),
                    hovertemplate="PA66: %{y:,.0f} RMB/ton<extra></extra>",
                ))
            fig.update_layout(
                title="PA6 Chip vs PA66 Chip (RMB/ton)",
                legend=dict(bgcolor="rgba(0,0,0,0)"),
                height=240,
                yaxis=dict(title="RMB/ton", gridcolor=_GRID, tickformat=","),
                xaxis=dict(gridcolor=_GRID),
                **_CHART,
            )
            pa1, pa2 = st.columns(2)
            if not df_pa6.empty:
                pa1.metric("PA6 Chip",  f"{cur6:,.0f} RMB/ton")
            if not df_pa66.empty:
                pa2.metric("PA66 Chip", f"{cur66:,.0f} RMB/ton")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No PA chip data yet")

    st.divider()

    with st.expander("All materials — latest prices"):
        rows = (
            df_all.sort_values("period")
            .groupby("material", sort=False)
            .last()
            .reset_index()
        )
        out_rows = []
        for _, r in rows.iterrows():
            mat_label = MATERIAL_LABELS.get(r["material"], r["material"])
            price_f   = float(r["price_usd"])
            unit_str  = str(r["unit"])
            usd_eq    = f"{price_f * RMB_USD_RATE:,.0f}" if "RMB" in unit_str else "—"
            out_rows.append([mat_label, str(r["period"])[:10],
                             f"{price_f:,.2f}", unit_str, usd_eq])
        tbl_df = pd.DataFrame(
            out_rows,
            columns=["Material", "Date", "Price", "Unit", "USD equiv./ton"],
        )
        _html_table(tbl_df)


# ── Tab 3: Export Intelligence ─────────────────────────────────────────────────

def tab_export_intelligence():
    st.subheader("Turkey Textile Export Intelligence")
    st.caption("Source: UN Comtrade · reporter: Turkey · flow: export · monthly")

    # Metric cards
    metrics  = q_trade_metrics("5407")
    metrics6 = q_trade_metrics("6006")
    m1, m2, m3, m4 = st.columns(4)

    if metrics:
        m1.metric(
            f"HS 5407 ({metrics.get('latest_period','—')})",
            f"${metrics.get('latest_total',0)/1e6:.1f}M",
            delta=f"{metrics['mom_pct']:+.1f}% MoM"
            if metrics.get("mom_pct") is not None else None,
        )
        m2.metric("Top destination (5407)", metrics.get("top_dest", "—"))
        m3.metric(
            "Top dest. value",
            f"${metrics.get('top_dest_val',0)/1e6:.1f}M"
            if "top_dest_val" in metrics else "—",
        )
    if metrics6:
        m4.metric(
            f"HS 6006 ({metrics6.get('latest_period','—')})",
            f"${metrics6.get('latest_total',0)/1e6:.1f}M",
            delta=f"{metrics6['mom_pct']:+.1f}% MoM"
            if metrics6.get("mom_pct") is not None else None,
        )

    st.divider()

    # Top destinations bar
    hs_sel = st.selectbox(
        "HS code for top destinations", list(HS_LABELS.keys()),
        format_func=lambda k: HS_LABELS[k], index=0,
    )
    df_top = q_trade_top_destinations(hs_sel)
    if not df_top.empty:
        d10 = df_top.head(10)
        vals  = d10["value_usd"].tolist()
        names = d10["country_name"].tolist()
        fig_bar = go.Figure(go.Bar(
            x=vals, y=names, orientation="h",
            text=[f"${v/1e6:.1f}M" for v in vals],
            textposition="outside",
            marker=dict(color=vals, colorscale="Blues", showscale=False),
            hovertemplate="%{y}: $%{x:,.0f}<extra></extra>",
        ))
        fig_bar.update_layout(
            title=f"Top 10 destinations — {HS_LABELS[hs_sel]} (latest month)",
            yaxis=dict(autorange="reversed"),
            xaxis=dict(gridcolor=_GRID),
            height=360,
            **_CHART,
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info(f"No trade data for {hs_sel}")

    st.divider()

    # Monthly trend
    hs_trend = st.multiselect(
        "HS codes for trend chart", list(HS_LABELS.keys()),
        default=["5407", "6006"],
        format_func=lambda k: HS_LABELS[k],
    )
    if hs_trend:
        df_trend = q_trade_monthly_trend(tuple(hs_trend))
        if not df_trend.empty:
            fig_line = go.Figure()
            for i, hs in enumerate(hs_trend):
                grp = df_trend[df_trend["hs_code"] == hs].sort_values("period")
                if grp.empty:
                    continue
                fig_line.add_trace(go.Scatter(
                    x=grp["period"].tolist(),
                    y=grp["value_usd_mn"].tolist(),
                    name=HS_LABELS.get(hs, hs),
                    mode="lines+markers",
                    line=dict(color=_PALETTE[i % len(_PALETTE)], width=2),
                    marker=dict(size=5),
                    hovertemplate=f"{HS_LABELS.get(hs,hs)}: %{{y:.1f}}M USD<extra></extra>",
                ))
            fig_line.update_layout(
                title="Monthly export value — Turkey",
                legend=dict(bgcolor="rgba(0,0,0,0)", title_text=""),
                height=350,
                yaxis=dict(gridcolor=_GRID, tickprefix="$", ticksuffix="M",
                           title="USD million"),
                xaxis=dict(gridcolor=_GRID, tickangle=-30),
                **_CHART,
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
        df_fab = q_lescon_by_fabric()
        df_mon = q_lescon_monthly()

        if df_fab.empty:
            st.info("No Lescon sales data.")
        else:
            total_rev = float(df_fab["revenue_usd"].sum())
            total_tx  = int(df_fab["tx_count"].sum())
            s1, s2, s3 = st.columns(3)
            s1.metric("Total revenue (excl. returns)", f"${total_rev:,.0f}")
            s2.metric("Total transactions", f"{total_tx:,}")
            s3.metric("Avg transaction value",
                      f"${total_rev/total_tx:,.0f}" if total_tx else "—")

            ca, cb = st.columns(2)
            with ca:
                revs  = df_fab["revenue_usd"].tolist()
                fabs  = df_fab["fabric_type"].tolist()
                fig_r = go.Figure(go.Bar(
                    x=revs, y=fabs, orientation="h",
                    text=[f"${v/1e3:.0f}K" for v in revs],
                    textposition="outside",
                    marker=dict(color=revs, colorscale="Teal", showscale=False),
                    hovertemplate="%{y}: $%{x:,.0f}<extra></extra>",
                ))
                fig_r.update_layout(
                    title="Revenue by fabric type (USD)",
                    yaxis=dict(autorange="reversed"),
                    xaxis=dict(gridcolor=_GRID),
                    height=360,
                    **_CHART,
                )
                st.plotly_chart(fig_r, use_container_width=True)

            with cb:
                txs   = df_fab["tx_count"].tolist()
                fig_t = go.Figure(go.Bar(
                    x=txs, y=fabs, orientation="h",
                    text=txs, textposition="outside",
                    marker=dict(color=txs, colorscale="Blues", showscale=False),
                    hovertemplate="%{y}: %{x} transactions<extra></extra>",
                ))
                fig_t.update_layout(
                    title="Transaction count by fabric type",
                    yaxis=dict(autorange="reversed"),
                    xaxis=dict(gridcolor=_GRID),
                    height=360,
                    **_CHART,
                )
                st.plotly_chart(fig_t, use_container_width=True)

            if not df_mon.empty:
                fig_mon = go.Figure(go.Scatter(
                    x=df_mon["month"].tolist(),
                    y=df_mon["revenue_usd"].tolist(),
                    mode="lines",
                    fill="tozeroy",
                    line=dict(color=C_BLUE, width=2),
                    fillcolor="rgba(31,119,180,0.12)",
                    hovertemplate="%{x}: $%{y:,.0f}<extra></extra>",
                ))
                fig_mon.update_layout(
                    title="Monthly revenue trend (Lescon account)",
                    height=280,
                    yaxis=dict(gridcolor=_GRID, tickprefix="$", title="Revenue (USD)"),
                    xaxis=dict(gridcolor=_GRID, tickangle=-30),
                    **_CHART,
                )
                st.plotly_chart(fig_mon, use_container_width=True)

            df_prod = q_lescon_top_products()
            if not df_prod.empty:
                st.markdown("**Top 10 products by transaction count**")
                disp = df_prod.copy()
                disp.columns = ["Product", "# Transactions", "Revenue (USD)"]
                disp["Revenue (USD)"] = disp["Revenue (USD)"].apply(
                    lambda v: f"${float(v):,.0f}"
                )
                _html_table(disp)

    # ── Yarn Costs ───────────────────────────────────────────────────────────────
    with inner2:
        df_yarn = q_yarn_cost_trend()
        if df_yarn.empty:
            st.info("No yarn cost data.")
        else:
            last  = df_yarn.iloc[-1]
            first = df_yarn.iloc[0]
            chg   = (
                (float(last["avg_cost_usd_per_mt"]) - float(first["avg_cost_usd_per_mt"]))
                / float(first["avg_cost_usd_per_mt"]) * 100
                if float(first["avg_cost_usd_per_mt"]) else 0
            )
            y1, y2, y3 = st.columns(3)
            y1.metric(f"Avg cost {int(last['year'])}",
                      f"${float(last['avg_cost_usd_per_mt']):.2f}/MT")
            y2.metric(f"Avg cost {int(first['year'])}",
                      f"${float(first['avg_cost_usd_per_mt']):.2f}/MT")
            y3.metric(f"Change {int(first['year'])} → {int(last['year'])}",
                      f"{chg:+.1f}%", delta_color="inverse")

            years = [str(int(v)) for v in df_yarn["year"].tolist()]
            costs = [float(v) for v in df_yarn["avg_cost_usd_per_mt"].tolist()]
            recs  = df_yarn["records"].tolist()

            fig_yarn = go.Figure(go.Bar(
                x=years, y=costs,
                marker_color=C_BLUE,
                text=[f"${v:.2f}" for v in costs],
                textposition="outside",
                customdata=recs,
                hovertemplate="Year %{x}<br><b>%{y:.2f} USD/MT</b>"
                              "<br>Records: %{customdata}<extra></extra>",
            ))
            fig_yarn.update_layout(
                title="Average yarn unit cost (USD/MT) by year",
                height=360,
                yaxis=dict(gridcolor=_GRID, tickprefix="$", title="USD/MT"),
                xaxis=dict(title="Year"),
                **_CHART,
            )
            st.plotly_chart(fig_yarn, use_container_width=True)

            with st.expander("Raw data by year"):
                disp = df_yarn.copy()
                disp.columns = ["Year", "Avg cost (USD/MT)", "Records"]
                disp["Avg cost (USD/MT)"] = disp["Avg cost (USD/MT)"].apply(
                    lambda v: f"${float(v):.4f}"
                )
                _html_table(disp)

    # ── Orders ──────────────────────────────────────────────────────────────────
    with inner3:
        df_sup = q_orders_by_supplier()
        if df_sup.empty:
            st.info("No orders data.")
        else:
            o1, o2 = st.columns(2)
            o1.metric("Total orders", "1,484")
            o2.metric("Distinct suppliers", str(int(df_sup["supplier"].nunique())))

            d12  = df_sup.head(12)
            ords = d12["order_count"].tolist()
            sups = d12["supplier"].tolist()
            fig_sup = go.Figure(go.Bar(
                x=ords, y=sups, orientation="h",
                text=ords, textposition="outside",
                marker=dict(color=ords, colorscale="Purples", showscale=False),
                hovertemplate="%{y}: %{x} orders<extra></extra>",
            ))
            fig_sup.update_layout(
                title="Top suppliers by order count",
                yaxis=dict(autorange="reversed"),
                xaxis=dict(gridcolor=_GRID),
                height=420,
                **_CHART,
            )
            st.plotly_chart(fig_sup, use_container_width=True)

            with st.expander("Full supplier table"):
                disp = df_sup.copy()
                disp.columns = ["Supplier", "Currency", "# Orders",
                                 "Total KG", "Avg price"]
                disp["Total KG"]  = disp["Total KG"].apply(
                    lambda v: f"{float(v):,.0f}" if v is not None else "—"
                )
                disp["Avg price"] = disp["Avg price"].apply(
                    lambda v: f"{float(v):.4f}" if v is not None else "—"
                )
                _html_table(disp)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not DB_URL:
        st.error("DATABASE_URL is not set. Add it to your .env file.")
        st.stop()

    render_sidebar()

    tab1, tab2, tab3, tab4 = st.tabs([
        "📡 Market Signals",
        "💹 Price Intelligence",
        "🌍 Export Intelligence",
        "🏭 Internal Data",
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
