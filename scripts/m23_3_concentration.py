"""
M2.3.3 — Customer concentration trend chart.

Mirror of M2.2.4 (Procurement concentration). 3 lines (top 1 / top 3 / top 10)
+ horizontal threshold reference at 33%.

Layout: stacked under the existing Gross/Net revenue chart, before the
Top 10 Customers table.

Backups: .bak_m23_3 suffix.
"""
from pathlib import Path

SERVER = Path("dashboard/server.py")
INDEX  = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m23_3")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. Backend — new endpoint
# ─────────────────────────────────────────────────────────────────────────
print("[1/4] Adding /api/internal/customer-concentration-trend endpoint...")
text = SERVER.read_text(encoding="utf-8")

ENDPOINT_MARKER = '@app.get("/api/internal/customer-concentration-trend")'
if ENDPOINT_MARKER in text:
    print("  ⏭  endpoint already present")
else:
    backup(SERVER)

    ANCHOR = "# ── /api/internal/top-customers ───────"
    if ANCHOR not in text:
        print("  ❌ anchor not found")
        raise SystemExit(1)

    NEW_ENDPOINT = '''# ── /api/internal/customer-concentration-trend ─────────────────────────────
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


'''

    text = text.replace(ANCHOR, NEW_ENDPOINT + ANCHOR, 1)
    SERVER.write_text(text, encoding="utf-8")
    print("  ✓ endpoint added")


# ─────────────────────────────────────────────────────────────────────────
# 2. HTML — add chart container after Gross/Net revenue chart
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/4] Inserting Concentration chart container into index.html...")
html = INDEX.read_text(encoding="utf-8")

if 'id="chart-ops-customer-concentration"' in html:
    print("  ⏭  Concentration chart container already present")
else:
    # Insert before the Top 10 Customers table-wrap inside Revenue sub-section.
    # Anchor: closing of the chart-panel that contains chart-ops-revenue.
    # Two indent variants tried (matches HTML layout in this file).

    OLD_8 = '''<div class="chart-panel-title">Monthly Revenue: Gross vs Net (TL, yarn resale excluded)</div>
          <div class="chart-wrap" id="chart-ops-revenue"></div>
        </div>
        <div class="table-wrap">'''
    NEW_8 = '''<div class="chart-panel-title">Monthly Revenue: Gross vs Net (TL, yarn resale excluded)</div>
          <div class="chart-wrap" id="chart-ops-revenue"></div>
        </div>
        <div class="chart-panel" style="margin-bottom:16px">
          <div class="chart-panel-title">Customer Concentration trend (top 1 / top 3 / top 10)</div>
          <div class="chart-wrap" id="chart-ops-customer-concentration"></div>
        </div>
        <div class="table-wrap">'''

    OLD_6 = '''<div class="chart-panel-title">Monthly Revenue: Gross vs Net (TL, yarn resale excluded)</div>
        <div class="chart-wrap" id="chart-ops-revenue"></div>
      </div>
      <div class="table-wrap">'''
    NEW_6 = '''<div class="chart-panel-title">Monthly Revenue: Gross vs Net (TL, yarn resale excluded)</div>
        <div class="chart-wrap" id="chart-ops-revenue"></div>
      </div>
      <div class="chart-panel" style="margin-bottom:16px">
        <div class="chart-panel-title">Customer Concentration trend (top 1 / top 3 / top 10)</div>
        <div class="chart-wrap" id="chart-ops-customer-concentration"></div>
      </div>
      <div class="table-wrap">'''

    if OLD_8 in html:
        backup(INDEX)
        html = html.replace(OLD_8, NEW_8, 1)
        INDEX.write_text(html, encoding="utf-8")
        print("  ✓ Concentration chart container inserted (8-space indent)")
    elif OLD_6 in html:
        backup(INDEX)
        html = html.replace(OLD_6, NEW_6, 1)
        INDEX.write_text(html, encoding="utf-8")
        print("  ✓ Concentration chart container inserted (6-space indent)")
    else:
        print("  ❌ Revenue chart anchor not found")
        idx = html.find('chart-ops-revenue')
        if idx > 0:
            print("  Context: " + repr(html[idx-30:idx+250]))
        raise SystemExit(1)


# ─────────────────────────────────────────────────────────────────────────
# 3. JS — fetch + render
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/4] Adding Concentration chart to app.v5.js...")
js = APP_JS.read_text(encoding="utf-8")

if "renderOpsCustomerConcentrationChart" in js:
    print("  ⏭  Concentration renderer already present")
else:
    backup(APP_JS)

    NEW_FN = '''


/* ── Customer concentration trend chart (M2.3.3) ───────────────────────── */
async function loadCustomerConcentrationChart() {
  try {
    const data = await api('/api/internal/customer-concentration-trend');
    if (!data || !data.data || !data.data.length) return;
    renderOpsCustomerConcentrationChart(data);
  } catch (e) {
    console.error('customer-concentration fetch failed', e);
  }
}

function renderOpsCustomerConcentrationChart(payload) {
  const data = payload?.data || [];
  if (!data.length) return;

  const months = data.map(d => d.month);
  const top1   = data.map(d => d.top_1_share_pct  ?? null);
  const top3   = data.map(d => d.top_3_share_pct  ?? null);
  const top10  = data.map(d => d.top_10_share_pct ?? null);
  const threshold = payload.threshold ?? 33;

  const traces = [
    {
      x: months, y: top10,
      name: 'Top 10 share',
      type: 'scatter', mode: 'lines+markers',
      line:   { color: C.green, width: 2 },
      marker: { color: C.green, size: 5 },
      hovertemplate: 'Top 10: %{y:.1f}%<extra></extra>',
    },
    {
      x: months, y: top3,
      name: 'Top 3 share',
      type: 'scatter', mode: 'lines+markers',
      line:   { color: C.orange, width: 2.5 },
      marker: { color: C.orange, size: 6 },
      hovertemplate: 'Top 3: %{y:.1f}%<extra></extra>',
    },
    {
      x: months, y: top1,
      name: 'Top 1 share',
      type: 'scatter', mode: 'lines+markers',
      line:   { color: C.blue, width: 2 },
      marker: { color: C.blue, size: 5 },
      hovertemplate: 'Top 1: %{y:.1f}%<extra></extra>',
    },
    {
      x: months, y: months.map(_ => threshold),
      name: `Watch zone (${threshold}%)`,
      type: 'scatter', mode: 'lines',
      line: { color: C.red || '#e03131', width: 1.2, dash: 'dash' },
      hovertemplate: `Watch: ${threshold}%<extra></extra>`,
    },
  ];

  Plotly.newPlot('chart-ops-customer-concentration', traces, {
    ...PLOTLY_BASE,
    height: 360,
    margin: { l: 60, r: 16, t: 12, b: 60 },
    legend: { orientation: 'h', y: -0.18, font: { color: C.muted, size: 11 } },
    xaxis: { ...PLOTLY_BASE.xaxis, tickangle: -45 },
    yaxis: {
      ...PLOTLY_BASE.yaxis,
      ticksuffix: '%',
      range: [0, 100],
      tickvals: [0, 25, 50, 75, 100],
    },
    annotations: [
      {
        xref: 'paper', yref: 'y',
        x: 1, xanchor: 'right',
        y: threshold, yanchor: 'bottom',
        text: `Top 3 watch zone (${threshold}%)`,
        showarrow: false,
        font: { color: C.red || '#e03131', size: 10 },
      },
    ],
  }, PLOTLY_CONFIG);
}
'''

    js = js.rstrip() + NEW_FN
    print("  ✓ renderOpsCustomerConcentrationChart appended")


# Wire sub-tab activation hook
WIRE_MARKER = "loadCustomerConcentrationChart hook"
if WIRE_MARKER in js:
    print("  ⏭  sub-tab hook already wired")
else:
    OLD_WIRE = '''      // loadRevenueKpis hook (M2.3.2)
      if (btn.dataset.sub === 'ops-revenue' && typeof loadRevenueKpis === 'function') {
        if (!window._revenueKpisLoaded) {
          loadRevenueKpis();
          window._revenueKpisLoaded = true;
        }
      }'''

    NEW_WIRE = '''      // loadRevenueKpis hook (M2.3.2)
      if (btn.dataset.sub === 'ops-revenue' && typeof loadRevenueKpis === 'function') {
        if (!window._revenueKpisLoaded) {
          loadRevenueKpis();
          window._revenueKpisLoaded = true;
        }
      }
      // loadCustomerConcentrationChart hook (M2.3.3)
      if (btn.dataset.sub === 'ops-revenue' && typeof loadCustomerConcentrationChart === 'function') {
        if (!window._custConcentrationLoaded) {
          loadCustomerConcentrationChart();
          window._custConcentrationLoaded = true;
        }
      }'''

    if OLD_WIRE in js:
        js = js.replace(OLD_WIRE, NEW_WIRE, 1)
        print("  ✓ sub-tab activation wired to loadCustomerConcentrationChart")
    else:
        print("  ⚠️  Revenue KPI hook anchor not found — manual wiring may be needed")

APP_JS.write_text(js, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 4. Cache buster
# ─────────────────────────────────────────────────────────────────────────
print("\n[4/4] Updating cache buster on app.v5.js reference...")
import re
import time as _time
html = INDEX.read_text(encoding="utf-8")
ts = _time.strftime("%Y%m%d%H%M%S")
new_html = re.sub(r'app\.v5\.js(\?[^"]*)?"', f'app.v5.js?v={ts}"', html)
if new_html != html:
    INDEX.write_text(new_html, encoding="utf-8")
    print(f"  ✓ cache buster updated to v={ts}")
else:
    print("  ⏭  no app.v5.js reference found")


print()
print("=" * 60)
print("M2.3.3 — Customer concentration trend complete.")
print("=" * 60)
print()
print("Restart uvicorn (new endpoint added):")
print("  Ctrl+C, then: python -m uvicorn dashboard.server:app --port 8000")
print()
print("Browser: hard-refresh, Operations Intelligence > Revenue Reality.")
print("Order: KPIs > Gross/Net chart > Concentration trend > Top 10 table")
