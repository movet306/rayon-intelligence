"""
M2.2.4 — Supplier concentration trend chart.

Backend: new endpoint /api/internal/procurement-concentration-trend
Frontend: 3-line chart (top 1, top 3, top 10) + horizontal threshold reference at 33%
Layout: stacked under Mix % chart (B layout sequence)

Backups: .bak_m22_4 suffix
"""
from pathlib import Path

SERVER = Path("dashboard/server.py")
INDEX  = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m22_4")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. Backend — new endpoint
# ─────────────────────────────────────────────────────────────────────────
print("[1/3] Adding /api/internal/procurement-concentration-trend endpoint...")
text = SERVER.read_text(encoding="utf-8")

ENDPOINT_MARKER = '@app.get("/api/internal/procurement-concentration-trend")'
if ENDPOINT_MARKER in text:
    print("  ⏭  endpoint already present")
else:
    backup(SERVER)

    # Insert just before /api/internal/top-suppliers comment block
    ANCHOR = "# ── /api/internal/top-suppliers ───────"
    if ANCHOR not in text:
        print("  ❌ anchor not found")
        raise SystemExit(1)

    NEW_ENDPOINT = '''# ── /api/internal/procurement-concentration-trend ──────────────────────────
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


'''

    text = text.replace(ANCHOR, NEW_ENDPOINT + ANCHOR, 1)
    SERVER.write_text(text, encoding="utf-8")
    print("  ✓ endpoint added")


# ─────────────────────────────────────────────────────────────────────────
# 2. HTML — add chart container after Mix % chart panel
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/3] Inserting Concentration chart container into index.html...")
html = INDEX.read_text(encoding="utf-8")

if 'id="chart-ops-procurement-concentration"' in html:
    print("  ⏭  Concentration chart container already present")
else:
    backup(INDEX)

    OLD = '<div class="chart-panel-title">Procurement Mix % over time</div>\n        <div class="chart-wrap" id="chart-ops-procurement-mix"></div>\n      </div>'
    NEW = '<div class="chart-panel-title">Procurement Mix % over time</div>\n        <div class="chart-wrap" id="chart-ops-procurement-mix"></div>\n      </div>\n      <div class="chart-panel" style="margin-bottom:16px">\n        <div class="chart-panel-title">Supplier Concentration trend (top 1 / top 3 / top 10)</div>\n        <div class="chart-wrap" id="chart-ops-procurement-concentration"></div>\n      </div>'

    if OLD not in html:
        print("  ❌ Mix chart anchor not found")
        idx = html.find('chart-ops-procurement-mix')
        if idx > 0:
            print("  Context: " + repr(html[idx-50:idx+250]))
        raise SystemExit(1)

    html = html.replace(OLD, NEW, 1)
    INDEX.write_text(html, encoding="utf-8")
    print("  ✓ Concentration chart container inserted after Mix % chart")


# ─────────────────────────────────────────────────────────────────────────
# 3. JS — fetch + render
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/3] Adding Concentration chart fetch+render to app.v5.js...")
js = APP_JS.read_text(encoding="utf-8")

if "renderOpsProcurementConcentrationChart" in js:
    print("  ⏭  Concentration renderer already present")
else:
    backup(APP_JS)

    NEW_FN = '''

/* ── Procurement concentration trend chart (M2.2.4) ────────────────────── */
async function loadProcurementConcentrationChart() {
  try {
    const data = await api('/api/internal/procurement-concentration-trend');
    if (!data || !data.data || !data.data.length) return;
    renderOpsProcurementConcentrationChart(data);
  } catch (e) {
    console.error('procurement-concentration fetch failed', e);
  }
}

function renderOpsProcurementConcentrationChart(payload) {
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

  Plotly.newPlot('chart-ops-procurement-concentration', traces, {
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

    # Insert after renderOpsProcurementMixChart's closing brace
    fn_start = js.find("function renderOpsProcurementMixChart(payload) {")
    if fn_start < 0:
        print("  ❌ renderOpsProcurementMixChart not found — patch aborted")
        raise SystemExit(1)

    brace_open = js.find("{", fn_start)
    depth = 1
    i = brace_open + 1
    while i < len(js) and depth > 0:
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
        i += 1
    fn_end = i

    js = js[:fn_end] + NEW_FN + js[fn_end:]
    print("  ✓ renderOpsProcurementConcentrationChart inserted")


# Wire the call. Two ways: (a) trigger from sub-tab activation hook, (b) call from
# the existing internal data loader. The mix chart uses route (b) — same payload as
# absolute chart. Concentration is a *separate endpoint*, so we use route (a) —
# load when Procurement sub-tab activates.

WIRE_MARKER = "loadProcurementConcentrationChart hook"
if WIRE_MARKER in js:
    print("  ⏭  concentration chart wiring already present")
else:
    OLD_WIRE = '''      // loadProcurementKpis hook (M2.2.2)
      if (btn.dataset.sub === 'ops-procurement' && typeof loadProcurementKpis === 'function') {
        if (!window._procKpisLoaded) {
          loadProcurementKpis();
          window._procKpisLoaded = true;
        }
      }'''

    NEW_WIRE = '''      // loadProcurementKpis hook (M2.2.2)
      if (btn.dataset.sub === 'ops-procurement' && typeof loadProcurementKpis === 'function') {
        if (!window._procKpisLoaded) {
          loadProcurementKpis();
          window._procKpisLoaded = true;
        }
      }
      // loadProcurementConcentrationChart hook (M2.2.4)
      if (btn.dataset.sub === 'ops-procurement' && typeof loadProcurementConcentrationChart === 'function') {
        if (!window._procConcentrationLoaded) {
          loadProcurementConcentrationChart();
          window._procConcentrationLoaded = true;
        }
      }'''

    if OLD_WIRE in js:
        js = js.replace(OLD_WIRE, NEW_WIRE, 1)
        print("  ✓ sub-tab activation wired to loadProcurementConcentrationChart")
    else:
        print("  ⚠️  sub-tab anchor not found — manual wiring may be needed")

APP_JS.write_text(js, encoding="utf-8")


print()
print("=" * 60)
print("M2.2.4 — Procurement concentration trend complete.")
print("=" * 60)
print()
print("Restart uvicorn (new endpoint added):")
print("  Ctrl+C, then: python -m uvicorn dashboard.server:app --port 8000")
print()
print("Browser: hard-refresh, Operations Intelligence > Procurement.")
print("Order: KPIs > absolute chart > Mix % > Concentration trend > Top 10 table")
