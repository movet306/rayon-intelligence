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
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import psycopg2
import streamlit as st
from dotenv import load_dotenv
from plotly.subplots import make_subplots

# Qualitative colour palette (replaces px.colors.qualitative.Bold)
_BOLD = ["#7F3C8D", "#11A579", "#3969AC", "#F2B701", "#E73F74",
         "#80BA5A", "#E68310", "#008695", "#CF1C90", "#f97b72"]

load_dotenv()

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Rayon Intelligence",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ──────────────────────────────────────────────────────────────────
RMB_USD_RATE = float(os.getenv("RMB_USD_RATE", "0.138"))

SIGNAL_COLORS = {
    "competitor_mention": "#FF6B35",
    "price_move":         "#4CAF50",
    "price_signal":       "#2196F3",
    "capacity_change":    "#AB47BC",
    "regulation":         "#EF5350",
    "trend":              "#26C6DA",
    "new_market":         "#9CCC65",
    "fair_participation": "#FFA726",
    "other":              "#78909C",
}
SEVERITY_COLORS = {
    "alert":   "#EF5350",
    "warning": "#FFA726",
    "info":    "#42A5F5",
}

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
    "US": "USA", "DE": "Germany", "NL": "Netherlands", "GB": "UK",
    "FR": "France", "IT": "Italy", "ES": "Spain", "PL": "Poland",
    "RU": "Russia", "UA": "Ukraine", "BY": "Belarus", "KZ": "Kazakhstan",
    "RO": "Romania", "BG": "Bulgaria", "IQ": "Iraq", "SA": "Saudi Arabia",
    "AE": "UAE", "EG": "Egypt", "MA": "Morocco", "GE": "Georgia",
    "AZ": "Azerbaijan", "AM": "Armenia", "UZ": "Uzbekistan", "TM": "Turkmenistan",
    "IR": "Iran", "IL": "Israel", "GR": "Greece", "CZ": "Czech Rep.",
    "SK": "Slovakia", "HU": "Hungary", "HR": "Croatia", "RS": "Serbia",
    "PT": "Portugal", "BE": "Belgium", "SE": "Sweden", "DK": "Denmark",
    "AT": "Austria", "CH": "Switzerland", "CN": "China", "TW": "Taiwan",
    "PK": "Pakistan", "BD": "Bangladesh", "IN": "India", "VN": "Vietnam",
    "MX": "Mexico", "BR": "Brazil", "TR": "Turkey (re-export)",
    "NG": "Nigeria", "ZA": "South Africa", "TN": "Tunisia", "DZ": "Algeria",
}

DB_URL = os.environ.get("DATABASE_URL", "")


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _conn():
    return psycopg2.connect(DB_URL)


@st.cache_data(ttl=3600, show_spinner=False)
def q_market_signals(days_back: int, types_filter: tuple, sev_filter: tuple) -> pd.DataFrame:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    sql = """
        SELECT
            ms.id,
            ms.signal_type,
            ms.severity,
            ms.title,
            ms.body,
            ms.source_table,
            ms.detected_at,
            ms.tags,
            c.name AS company_name
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
        SELECT material, period, price_usd, unit
        FROM price_signals
        WHERE source = 'sunsirs'
        ORDER BY material, period
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn, parse_dates=["period"])


@st.cache_data(ttl=3600, show_spinner=False)
def q_trade_top_destinations(hs_code: str) -> pd.DataFrame:
    sql = """
        SELECT
            partner_country,
            SUM(value_usd) AS value_usd
        FROM trade_flows
        WHERE hs_code = %s
          AND flow_direction = 'export'
          AND period = (
              SELECT MAX(period) FROM trade_flows
              WHERE hs_code = %s AND flow_direction = 'export'
          )
          AND partner_country IS NOT NULL
        GROUP BY partner_country
        ORDER BY value_usd DESC
        LIMIT 12
    """
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn, params=(hs_code, hs_code))
    df["country_name"] = df["partner_country"].map(lambda c: COUNTRY_NAMES.get(c, c))
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def q_trade_monthly_trend(hs_codes: tuple) -> pd.DataFrame:
    placeholders = ",".join(["%s"] * len(hs_codes))
    sql = f"""
        SELECT
            hs_code,
            period,
            SUM(value_usd) / 1e6 AS value_usd_mn
        FROM trade_flows
        WHERE hs_code IN ({placeholders})
          AND flow_direction = 'export'
          AND partner_country IS NOT NULL
        GROUP BY hs_code, period
        ORDER BY period, hs_code
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn, params=list(hs_codes), parse_dates=["period"])


@st.cache_data(ttl=3600, show_spinner=False)
def q_trade_metrics(hs_code: str) -> dict:
    sql = """
        SELECT
            period,
            SUM(value_usd) AS total_usd,
            MAX(CASE WHEN partner_country IS NOT NULL THEN partner_country END) FILTER (
                WHERE partner_country IS NOT NULL
            ) AS something
        FROM trade_flows
        WHERE hs_code = %s AND flow_direction = 'export'
        GROUP BY period
        ORDER BY period DESC
        LIMIT 2
    """
    # Simpler approach
    sql = """
        SELECT period, SUM(value_usd) AS total_usd
        FROM trade_flows
        WHERE hs_code = %s AND flow_direction = 'export' AND partner_country IS NOT NULL
        GROUP BY period
        ORDER BY period DESC
        LIMIT 2
    """
    sql_top = """
        SELECT partner_country, SUM(value_usd) AS v
        FROM trade_flows
        WHERE hs_code = %s AND flow_direction = 'export'
          AND period = (SELECT MAX(period) FROM trade_flows WHERE hs_code = %s AND flow_direction = 'export')
          AND partner_country IS NOT NULL
        GROUP BY partner_country
        ORDER BY v DESC
        LIMIT 1
    """
    with _conn() as conn:
        df_periods = pd.read_sql_query(sql, conn, params=(hs_code,))
        df_top = pd.read_sql_query(sql_top, conn, params=(hs_code, hs_code))

    result = {}
    if not df_periods.empty:
        result["latest_period"] = df_periods.iloc[0]["period"]
        result["latest_total"] = float(df_periods.iloc[0]["total_usd"])
        if len(df_periods) > 1:
            prev = float(df_periods.iloc[1]["total_usd"])
            result["mom_pct"] = (result["latest_total"] - prev) / prev * 100 if prev else 0
        else:
            result["mom_pct"] = None
    if not df_top.empty:
        iso = df_top.iloc[0]["partner_country"]
        result["top_dest"] = COUNTRY_NAMES.get(iso, iso)
        result["top_dest_val"] = float(df_top.iloc[0]["v"])
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def q_lescon_by_fabric() -> pd.DataFrame:
    sql = """
        SELECT
            COALESCE(NULLIF(TRIM(fabric_type), ''), 'Unknown') AS fabric_type,
            COUNT(*) AS tx_count,
            ROUND(SUM(miktar * unit_price_usd)::numeric, 2) AS revenue_usd
        FROM lescon_sales
        WHERE NOT is_return
          AND unit_price_usd IS NOT NULL
          AND miktar IS NOT NULL
          AND unit_price_usd > 0
        GROUP BY 1
        ORDER BY revenue_usd DESC
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=3600, show_spinner=False)
def q_lescon_monthly() -> pd.DataFrame:
    sql = """
        SELECT
            DATE_TRUNC('month', tarih)::date AS month,
            ROUND(SUM(miktar * unit_price_usd)::numeric, 2) AS revenue_usd,
            COUNT(*) AS tx_count
        FROM lescon_sales
        WHERE NOT is_return
          AND tarih IS NOT NULL
          AND unit_price_usd IS NOT NULL
          AND miktar IS NOT NULL
          AND unit_price_usd > 0
        GROUP BY 1
        ORDER BY 1
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn, parse_dates=["month"])


@st.cache_data(ttl=3600, show_spinner=False)
def q_lescon_top_products() -> pd.DataFrame:
    sql = """
        SELECT
            COALESCE(NULLIF(TRIM(urun_aciklamasi), ''), 'Unknown') AS product,
            COUNT(*) AS tx_count,
            ROUND(SUM(miktar * unit_price_usd)::numeric, 2) AS revenue_usd
        FROM lescon_sales
        WHERE NOT is_return
          AND unit_price_usd IS NOT NULL
          AND miktar IS NOT NULL
          AND unit_price_usd > 0
        GROUP BY 1
        ORDER BY tx_count DESC
        LIMIT 10
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=3600, show_spinner=False)
def q_yarn_cost_trend() -> pd.DataFrame:
    sql = """
        SELECT
            EXTRACT(YEAR FROM factory_entry_date)::int AS year,
            ROUND(AVG(unit_cost_usd)::numeric, 4) AS avg_cost_usd_per_mt,
            COUNT(*) AS records
        FROM yarn_costs
        WHERE unit_cost_usd IS NOT NULL
          AND factory_entry_date IS NOT NULL
          AND unit_cost_usd > 0
        GROUP BY 1
        ORDER BY 1
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


@st.cache_data(ttl=3600, show_spinner=False)
def q_orders_by_supplier() -> pd.DataFrame:
    sql = """
        SELECT
            COALESCE(supplier_clean, supplier_raw, 'Unknown') AS supplier,
            currency_clean,
            COUNT(*) AS order_count,
            ROUND(SUM(qty_numeric)::numeric, 0) AS total_kg,
            ROUND(AVG(price_numeric)::numeric, 4) AS avg_price
        FROM orders
        WHERE record_status IS DISTINCT FROM 'exclude'
        GROUP BY 1, 2
        ORDER BY order_count DESC
        LIMIT 15
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


# ── Style helpers ──────────────────────────────────────────────────────────────

def badge(text: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:2px 9px;'
        f'border-radius:4px;font-size:11px;font-weight:600;'
        f'letter-spacing:0.5px">{text.replace("_", " ").upper()}</span>'
    )


def signal_card_html(row: pd.Series) -> str:
    type_color = SIGNAL_COLORS.get(row["signal_type"], "#78909C")
    sev_color  = SEVERITY_COLORS.get(row["severity"], "#42A5F5")
    dt = pd.to_datetime(row["detected_at"])
    dt_str = dt.strftime("%Y-%m-%d %H:%M") if pd.notna(dt) else ""
    title = str(row["title"] or "")[:140]
    body  = str(row["body"]  or "")
    company_html = ""
    if row.get("company_name"):
        company_html = (
            f'<div style="margin-top:5px;color:{type_color};font-size:12px;font-weight:600">'
            f'&#127970; {row["company_name"]}</div>'
        )
    src = str(row.get("source_table") or "").replace("_", " ")
    return f"""
<div style="
    background:#1c1c2e;
    border-left:4px solid {type_color};
    padding:12px 16px;
    margin:5px 0;
    border-radius:0 6px 6px 0;
">
  <div style="display:flex;gap:7px;align-items:center;margin-bottom:7px;flex-wrap:wrap">
    {badge(row['signal_type'], type_color)}
    {badge(row['severity'], sev_color)}
    <span style="color:#888;font-size:12px;margin-left:auto">{dt_str} &nbsp;·&nbsp; {src}</span>
  </div>
  <div style="font-weight:600;font-size:14px;color:#e8e8f0;margin-bottom:5px">{title}</div>
  <div style="color:#aab;font-size:13px;line-height:1.5">{body}</div>
  {company_html}
</div>
"""


def price_dual_chart(df_mat: pd.DataFrame, title: str) -> go.Figure:
    """Dual-axis chart: RMB/ton (left) + USD/ton (right)."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    rmb = df_mat["price_usd"].astype(float)  # stored as RMB/ton for sunsirs
    usd = rmb * RMB_USD_RATE

    fig.add_trace(
        go.Scatter(
            x=df_mat["period"], y=rmb,
            name="RMB/ton", line=dict(color="#26C6DA", width=2),
            hovertemplate="%{x|%b %d}<br><b>%{y:,.0f} RMB/ton</b><extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df_mat["period"], y=usd,
            name="USD/ton", line=dict(color="#FF8A65", width=1.5, dash="dot"),
            hovertemplate="%{x|%b %d}<br><b>%{y:,.0f} USD/ton</b><extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#ccc"),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        margin=dict(l=0, r=0, t=40, b=0),
        height=260,
        hovermode="x unified",
    )
    fig.update_yaxes(
        title_text="RMB / ton", secondary_y=False,
        gridcolor="#2a2a3a", tickformat=",",
    )
    fig.update_yaxes(
        title_text="USD / ton", secondary_y=True,
        gridcolor="#2a2a3a", tickformat=",",
    )
    fig.update_xaxes(gridcolor="#2a2a3a", tickformat="%b %d")
    return fig


def price_delta(df_mat: pd.DataFrame):
    """Return (current_rmb, delta_pct_or_None)."""
    if df_mat.empty:
        return None, None
    vals = df_mat["price_usd"].astype(float)
    cur = vals.iloc[-1]
    first = vals.iloc[0]
    delta = (cur - first) / first * 100 if first else None
    return cur, delta


# ── Sidebar ────────────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown(
            """
            <div style="text-align:center;padding:16px 0 8px">
              <div style="font-size:28px">🧵</div>
              <div style="font-size:18px;font-weight:700;color:#e0e0ff">Rayon Intelligence</div>
              <div style="font-size:11px;color:#888;margin-top:2px">Rayon Tekstil Sanayi</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.divider()
        st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        st.caption(f"RMB/USD rate: {RMB_USD_RATE}")
        if st.button("🔄 Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()


# ── Tab 1: Market Signals ──────────────────────────────────────────────────────

def tab_market_signals():
    st.subheader("Market Signals")

    # Filters row
    col_days, col_types, col_sev = st.columns([1, 2, 2])
    with col_days:
        days_back = st.selectbox(
            "Time window",
            [7, 14, 30, 60, 90, 365],
            format_func=lambda d: f"Last {d} days",
            index=0,
        )
    with col_types:
        all_types = list(SIGNAL_COLORS.keys())
        types_sel = st.multiselect(
            "Signal type",
            all_types,
            default=[],
            placeholder="All types",
            format_func=lambda t: t.replace("_", " ").title(),
        )
    with col_sev:
        sev_sel = st.multiselect(
            "Severity",
            ["info", "warning", "alert"],
            default=[],
            placeholder="All severities",
        )

    df = q_market_signals(
        days_back=days_back,
        types_filter=tuple(types_sel),
        sev_filter=tuple(sev_sel),
    )

    # Summary metrics
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Total signals", len(df))
    mc2.metric("Competitor mentions", int((df["signal_type"] == "competitor_mention").sum()))
    mc3.metric("Alerts", int((df["severity"] == "alert").sum()))
    mc4.metric("Warnings", int((df["severity"] == "warning").sum()))

    st.divider()

    if df.empty:
        st.info("No signals in this period. Try expanding the time window.")
        return

    # Signal cards
    html_parts = []
    for _, row in df.iterrows():
        html_parts.append(signal_card_html(row))

    st.markdown("\n".join(html_parts), unsafe_allow_html=True)


# ── Tab 2: Price Intelligence ──────────────────────────────────────────────────

def tab_price_intelligence():
    st.subheader("Commodity Price Intelligence")
    st.caption("Source: SunSirs (sunsirs.com) · RMB/ton · dual axis shows USD equivalent")

    df_all = q_price_signals()
    if df_all.empty:
        st.info("No price data yet. Run scrapers/price_scraper.py to populate.")
        return

    # ── Row 1: Polyester Staple Fibre + Nylon FDY ──────────────────────────────
    c1, c2 = st.columns(2)

    with c1:
        mat = "polyester_staple_fiber"
        label = MATERIAL_LABELS.get(mat, mat)
        df_mat = df_all[df_all["material"] == mat].copy()
        cur, delta = price_delta(df_mat)
        if cur is not None:
            st.metric(
                label,
                f"{cur:,.0f} RMB/ton  ({cur * RMB_USD_RATE:,.0f} USD/ton)",
                delta=f"{delta:+.1f}% vs dataset start" if delta is not None else None,
                delta_color="inverse",
            )
            st.plotly_chart(price_dual_chart(df_mat, label), use_container_width=True)
        else:
            st.info(f"No data for {label}")

    with c2:
        mat = "polyamide_fdy"
        label = MATERIAL_LABELS.get(mat, mat)
        df_mat = df_all[df_all["material"] == mat].copy()
        cur, delta = price_delta(df_mat)
        if cur is not None:
            st.metric(
                label,
                f"{cur:,.0f} RMB/ton  ({cur * RMB_USD_RATE:,.0f} USD/ton)",
                delta=f"{delta:+.1f}% vs dataset start" if delta is not None else None,
                delta_color="inverse",
            )
            st.plotly_chart(price_dual_chart(df_mat, label), use_container_width=True)
        else:
            st.info(f"No data for {label}")

    st.divider()

    # ── Row 2: Cotton Lint + PA6 vs PA66 ───────────────────────────────────────
    c3, c4 = st.columns(2)

    with c3:
        mat = "cotton_lint"
        label = MATERIAL_LABELS.get(mat, mat)
        df_mat = df_all[df_all["material"] == mat].copy()
        cur, delta = price_delta(df_mat)
        if cur is not None:
            st.metric(
                label,
                f"{cur:,.0f} RMB/ton  ({cur * RMB_USD_RATE:,.0f} USD/ton)",
                delta=f"{delta:+.1f}% vs dataset start" if delta is not None else None,
                delta_color="inverse",
            )
            st.plotly_chart(price_dual_chart(df_mat, label), use_container_width=True)
        else:
            st.info(f"No data for {label}")

    with c4:
        label = "PA6 Chip vs PA66 Chip"
        df_pa6  = df_all[df_all["material"] == "pa6_chip"].copy()
        df_pa66 = df_all[df_all["material"] == "pa66_chip"].copy()

        if not df_pa6.empty or not df_pa66.empty:
            fig = go.Figure()
            if not df_pa6.empty:
                cur6, _ = price_delta(df_pa6)
                fig.add_trace(go.Scatter(
                    x=df_pa6["period"], y=df_pa6["price_usd"].astype(float),
                    name="PA6 Chip", line=dict(color="#26C6DA", width=2),
                    hovertemplate="%{x|%b %d}<br><b>PA6: %{y:,.0f} RMB/ton</b><extra></extra>",
                ))
            if not df_pa66.empty:
                cur66, _ = price_delta(df_pa66)
                fig.add_trace(go.Scatter(
                    x=df_pa66["period"], y=df_pa66["price_usd"].astype(float),
                    name="PA66 Chip", line=dict(color="#FF8A65", width=2),
                    hovertemplate="%{x|%b %d}<br><b>PA66: %{y:,.0f} RMB/ton</b><extra></extra>",
                ))
            fig.update_layout(
                title=dict(text=label, font=dict(size=14)),
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                font=dict(color="#ccc"),
                legend=dict(bgcolor="rgba(0,0,0,0)"),
                margin=dict(l=0, r=0, t=40, b=0),
                height=260,
                hovermode="x unified",
                yaxis=dict(title="RMB / ton", gridcolor="#2a2a3a", tickformat=","),
                xaxis=dict(gridcolor="#2a2a3a", tickformat="%b %d"),
            )
            pa_col1, pa_col2 = st.columns(2)
            if not df_pa6.empty:
                pa_col1.metric("PA6 Chip", f"{cur6:,.0f} RMB/ton")
            if not df_pa66.empty:
                pa_col2.metric("PA66 Chip", f"{cur66:,.0f} RMB/ton")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No PA chip data yet")

    st.divider()

    # ── All materials table ─────────────────────────────────────────────────────
    with st.expander("All materials — latest prices"):
        latest = (
            df_all.sort_values("period")
            .groupby("material")
            .last()
            .reset_index()[["material", "period", "price_usd", "unit"]]
        )
        latest["label"] = latest["material"].map(lambda m: MATERIAL_LABELS.get(m, m))
        latest["price_usd_ton"] = latest.apply(
            lambda r: r["price_usd"] * RMB_USD_RATE
            if "RMB" in str(r["unit"]) else r["price_usd"],
            axis=1,
        )
        st.dataframe(
            latest[["label", "period", "price_usd", "unit", "price_usd_ton"]].rename(columns={
                "label": "Material", "period": "Date",
                "price_usd": "Price (source unit)", "unit": "Unit",
                "price_usd_ton": "USD equiv. / ton",
            }),
            hide_index=True,
            use_container_width=True,
        )


# ── Tab 3: Export Intelligence ─────────────────────────────────────────────────

def tab_export_intelligence():
    st.subheader("Turkey Textile Export Intelligence")
    st.caption("Source: UN Comtrade · Turkey (HS reporter) · Export flows · Monthly")

    # ── Metric cards ────────────────────────────────────────────────────────────
    metrics = q_trade_metrics("5407")
    m1, m2, m3, m4 = st.columns(4)

    if metrics:
        period_label = (
            pd.to_datetime(metrics["latest_period"]).strftime("%b %Y")
            if "latest_period" in metrics else "—"
        )
        m1.metric(
            f"HS 5407 exports ({period_label})",
            f"${metrics.get('latest_total', 0) / 1e6:.1f}M",
            delta=f"{metrics['mom_pct']:+.1f}% MoM" if metrics.get("mom_pct") is not None else None,
        )
        m2.metric("Top destination", metrics.get("top_dest", "—"))
        m3.metric(
            "Top dest. value",
            f"${metrics.get('top_dest_val', 0) / 1e6:.1f}M" if "top_dest_val" in metrics else "—",
        )

    metrics6 = q_trade_metrics("6006")
    if metrics6:
        period_label6 = (
            pd.to_datetime(metrics6["latest_period"]).strftime("%b %Y")
            if "latest_period" in metrics6 else "—"
        )
        m4.metric(
            f"HS 6006 exports ({period_label6})",
            f"${metrics6.get('latest_total', 0) / 1e6:.1f}M",
            delta=f"{metrics6['mom_pct']:+.1f}% MoM" if metrics6.get("mom_pct") is not None else None,
        )

    st.divider()

    # ── Top destinations bar chart ───────────────────────────────────────────────
    hs_sel = st.selectbox(
        "HS code for top destinations",
        list(HS_LABELS.keys()),
        format_func=lambda k: HS_LABELS[k],
        index=0,
    )

    df_top = q_trade_top_destinations(hs_sel)
    if not df_top.empty:
        d10 = df_top.head(10)
        fig_bar = go.Figure(go.Bar(
            x=d10["value_usd"].tolist(),
            y=d10["country_name"].tolist(),
            orientation="h",
            text=[f"${v/1e6:.1f}M" for v in d10["value_usd"]],
            textposition="outside",
            marker=dict(
                color=d10["value_usd"].tolist(),
                colorscale="Teal",
                showscale=False,
            ),
            hovertemplate="%{y}: $%{x:,.0f}<extra></extra>",
        ))
        fig_bar.update_layout(
            title=f"Top 10 destinations — {HS_LABELS[hs_sel]} (latest month)",
            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            font=dict(color="#ccc"),
            yaxis=dict(autorange="reversed"),
            margin=dict(l=0, r=80, t=40, b=0),
            height=360,
        )
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info(f"No trade data for {hs_sel}")

    st.divider()

    # ── Monthly trend line chart ─────────────────────────────────────────────────
    hs_trend = st.multiselect(
        "HS codes for trend chart",
        list(HS_LABELS.keys()),
        default=["5407", "6006"],
        format_func=lambda k: HS_LABELS[k],
    )

    if hs_trend:
        df_trend = q_trade_monthly_trend(tuple(hs_trend))
        if not df_trend.empty:
            df_trend["label"] = df_trend["hs_code"].map(lambda k: HS_LABELS.get(k, k))
            fig_line = go.Figure()
            for i, (label, grp) in enumerate(df_trend.groupby("label", sort=False)):
                grp = grp.sort_values("period")
                fig_line.add_trace(go.Scatter(
                    x=grp["period"].tolist(),
                    y=grp["value_usd_mn"].tolist(),
                    name=label,
                    mode="lines+markers",
                    line=dict(color=_BOLD[i % len(_BOLD)], width=2),
                    marker=dict(size=6),
                    hovertemplate=f"{label}: %{{y:.1f}}M USD<extra></extra>",
                ))
            fig_line.update_layout(
                title="Monthly export value — Turkey",
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                font=dict(color="#ccc"),
                legend=dict(bgcolor="rgba(0,0,0,0)", title_text=""),
                margin=dict(l=0, r=0, t=40, b=0),
                height=350,
                hovermode="x unified",
                yaxis=dict(gridcolor="#2a2a3a", tickprefix="$", ticksuffix="M", title="USD million"),
                xaxis=dict(gridcolor="#2a2a3a", tickformat="%b %Y"),
            )
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("No trend data for selected HS codes")
    else:
        st.info("Select at least one HS code above")


# ── Tab 4: Internal Data ───────────────────────────────────────────────────────

def tab_internal_data():
    st.subheader("Internal Business Data")

    inner_tab1, inner_tab2, inner_tab3 = st.tabs(
        ["📦 Lescon Sales", "🧶 Yarn Costs", "🛒 Orders"]
    )

    # ── Lescon Sales ─────────────────────────────────────────────────────────────
    with inner_tab1:
        df_fab = q_lescon_by_fabric()
        df_mon = q_lescon_monthly()

        if df_fab.empty:
            st.info("No Lescon sales data.")
        else:
            # Summary metrics
            total_rev = float(df_fab["revenue_usd"].sum())
            total_tx  = int(df_fab["tx_count"].sum())
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Total revenue (excl. returns)", f"${total_rev:,.0f}")
            sc2.metric("Total transactions", f"{total_tx:,}")
            sc3.metric("Avg transaction value", f"${total_rev/total_tx:,.0f}" if total_tx else "—")

            col_a, col_b = st.columns(2)
            with col_a:
                fig_fab = go.Figure(go.Bar(
                    x=df_fab["revenue_usd"].tolist(),
                    y=df_fab["fabric_type"].tolist(),
                    orientation="h",
                    text=[f"${v/1e3:.0f}K" for v in df_fab["revenue_usd"]],
                    textposition="outside",
                    marker=dict(
                        color=df_fab["revenue_usd"].tolist(),
                        colorscale="Teal",
                        showscale=False,
                    ),
                    hovertemplate="%{y}: $%{x:,.0f}<extra></extra>",
                ))
                fig_fab.update_layout(
                    title="Revenue by fabric type (USD)",
                    paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                    font=dict(color="#ccc"),
                    yaxis=dict(autorange="reversed"),
                    margin=dict(l=0, r=60, t=40, b=0),
                    height=360,
                )
                st.plotly_chart(fig_fab, use_container_width=True)

            with col_b:
                fig_tx = go.Figure(go.Bar(
                    x=df_fab["tx_count"].tolist(),
                    y=df_fab["fabric_type"].tolist(),
                    orientation="h",
                    text=df_fab["tx_count"].tolist(),
                    textposition="outside",
                    marker=dict(
                        color=df_fab["tx_count"].tolist(),
                        colorscale="Blues",
                        showscale=False,
                    ),
                    hovertemplate="%{y}: %{x} transactions<extra></extra>",
                ))
                fig_tx.update_layout(
                    title="Transaction count by fabric type",
                    paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                    font=dict(color="#ccc"),
                    yaxis=dict(autorange="reversed"),
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=360,
                )
                st.plotly_chart(fig_tx, use_container_width=True)

            # Monthly revenue trend
            if not df_mon.empty:
                fig_mon = go.Figure(go.Scatter(
                    x=df_mon["month"].tolist(),
                    y=df_mon["revenue_usd"].tolist(),
                    mode="lines",
                    fill="tozeroy",
                    line=dict(color="#26C6DA", width=2),
                    fillcolor="rgba(38,198,218,0.15)",
                    hovertemplate="%{x|%b %Y}: $%{y:,.0f}<extra></extra>",
                ))
                fig_mon.update_layout(
                    title="Monthly revenue trend (Lescon account)",
                    paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                    font=dict(color="#ccc"),
                    margin=dict(l=0, r=0, t=40, b=0),
                    height=280,
                    yaxis=dict(gridcolor="#2a2a3a", tickprefix="$", title="Revenue (USD)"),
                    xaxis=dict(gridcolor="#2a2a3a", tickformat="%b %Y"),
                )
                st.plotly_chart(fig_mon, use_container_width=True)

            # Top products table
            df_prod = q_lescon_top_products()
            if not df_prod.empty:
                st.markdown("**Top 10 products by transaction count**")
                st.dataframe(
                    df_prod.rename(columns={
                        "product": "Product description",
                        "tx_count": "# Transactions",
                        "revenue_usd": "Revenue (USD)",
                    }),
                    hide_index=True,
                    use_container_width=True,
                )

    # ── Yarn Costs ───────────────────────────────────────────────────────────────
    with inner_tab2:
        df_yarn = q_yarn_cost_trend()

        if df_yarn.empty:
            st.info("No yarn cost data.")
        else:
            yc1, yc2, yc3 = st.columns(3)
            latest_year = df_yarn.iloc[-1]
            earliest_year = df_yarn.iloc[0]
            chg = (
                (float(latest_year["avg_cost_usd_per_mt"]) - float(earliest_year["avg_cost_usd_per_mt"]))
                / float(earliest_year["avg_cost_usd_per_mt"]) * 100
                if float(earliest_year["avg_cost_usd_per_mt"]) else 0
            )
            yc1.metric(
                f"Avg unit cost {int(latest_year['year'])}",
                f"${float(latest_year['avg_cost_usd_per_mt']):.2f} / MT",
            )
            yc2.metric(
                f"Avg unit cost {int(earliest_year['year'])}",
                f"${float(earliest_year['avg_cost_usd_per_mt']):.2f} / MT",
            )
            yc3.metric(
                f"Change {int(earliest_year['year'])} → {int(latest_year['year'])}",
                f"{chg:+.1f}%",
                delta_color="inverse",
            )

            fig_yarn = go.Figure()
            fig_yarn.add_trace(go.Bar(
                x=df_yarn["year"].astype(str),
                y=df_yarn["avg_cost_usd_per_mt"].astype(float),
                marker_color="#26C6DA",
                text=df_yarn["avg_cost_usd_per_mt"].astype(float).apply(lambda v: f"${v:.2f}"),
                textposition="outside",
                name="Avg USD/MT",
                hovertemplate="Year %{x}<br><b>%{y:.2f} USD/MT</b><br>Records: %{customdata}<extra></extra>",
                customdata=df_yarn["records"],
            ))
            fig_yarn.update_layout(
                title="Average yarn unit cost USD/MT by year",
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                font=dict(color="#ccc"),
                margin=dict(l=0, r=0, t=40, b=0),
                height=360,
                yaxis=dict(gridcolor="#2a2a3a", tickprefix="$", title="USD / MT"),
                xaxis=dict(title="Year"),
            )
            st.plotly_chart(fig_yarn, use_container_width=True)

            with st.expander("Raw data by year"):
                st.dataframe(
                    df_yarn.rename(columns={
                        "year": "Year",
                        "avg_cost_usd_per_mt": "Avg cost (USD/MT)",
                        "records": "Records",
                    }),
                    hide_index=True,
                    use_container_width=True,
                )

    # ── Orders ──────────────────────────────────────────────────────────────────
    with inner_tab3:
        df_sup = q_orders_by_supplier()

        if df_sup.empty:
            st.info("No orders data.")
        else:
            oc1, oc2 = st.columns(2)
            oc1.metric("Total orders", "1,484")
            oc2.metric("Total suppliers", str(df_sup["supplier"].nunique()))

            d12 = df_sup.head(12)
            fig_sup = go.Figure(go.Bar(
                x=d12["order_count"].tolist(),
                y=d12["supplier"].tolist(),
                orientation="h",
                text=d12["order_count"].tolist(),
                textposition="outside",
                marker=dict(
                    color=d12["order_count"].tolist(),
                    colorscale="Purples",
                    showscale=False,
                ),
                hovertemplate="%{y}: %{x} orders<extra></extra>",
            ))
            fig_sup.update_layout(
                title="Top suppliers by order count",
                paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                font=dict(color="#ccc"),
                yaxis=dict(autorange="reversed"),
                margin=dict(l=0, r=40, t=40, b=0),
                height=420,
            )
            st.plotly_chart(fig_sup, use_container_width=True)

            with st.expander("Full supplier table"):
                st.dataframe(
                    df_sup.rename(columns={
                        "supplier": "Supplier",
                        "currency_clean": "Currency",
                        "order_count": "# Orders",
                        "total_kg": "Total KG",
                        "avg_price": "Avg price",
                    }),
                    hide_index=True,
                    use_container_width=True,
                )


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
