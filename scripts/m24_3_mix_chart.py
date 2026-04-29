"""
M2.4.3 — Cost Structure mix % chart.

Frontend-only. Reuses /api/internal/cost-structure-trend (no backend change).
Inserts a new chart panel below the existing absolute-TL chart, showing the
same data normalized to monthly bucket %.

Mirror of M2.2.3 (Procurement mix chart).

Backups: .bak_m24_3 suffix.
"""
from pathlib import Path

INDEX  = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m24_3")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. HTML — insert mix chart panel after the absolute chart
# ─────────────────────────────────────────────────────────────────────────
print("[1/3] Inserting Cost mix chart panel into HTML...")
html = INDEX.read_text(encoding="utf-8")

if 'id="chart-ops-cost-mix"' in html:
    print("  ⏭  Mix chart container already present")
else:
    OLD_8 = '''<div class="chart-panel-title">Monthly Cost Structure (TL)</div>
          <div class="chart-wrap" id="chart-ops-cost"></div>
        </div>
        <div class="ops-note" id="ops-cost-note">'''
    NEW_8 = '''<div class="chart-panel-title">Monthly Cost Structure (TL)</div>
          <div class="chart-wrap" id="chart-ops-cost"></div>
        </div>
        <div class="chart-panel" style="margin-top:16px">
          <div class="chart-panel-title">Cost Mix Over Time (% share)</div>
          <div class="chart-wrap" id="chart-ops-cost-mix"></div>
        </div>
        <div class="ops-note" id="ops-cost-note">'''

    OLD_6 = '''<div class="chart-panel-title">Monthly Cost Structure (TL)</div>
        <div class="chart-wrap" id="chart-ops-cost"></div>
      </div>
      <div class="ops-note" id="ops-cost-note">'''
    NEW_6 = '''<div class="chart-panel-title">Monthly Cost Structure (TL)</div>
        <div class="chart-wrap" id="chart-ops-cost"></div>
      </div>
      <div class="chart-panel" style="margin-top:16px">
        <div class="chart-panel-title">Cost Mix Over Time (% share)</div>
        <div class="chart-wrap" id="chart-ops-cost-mix"></div>
      </div>
      <div class="ops-note" id="ops-cost-note">'''

    if OLD_8 in html:
        backup(INDEX)
        html = html.replace(OLD_8, NEW_8, 1)
        INDEX.write_text(html, encoding="utf-8")
        print("  ✓ Mix chart panel inserted (8-space indent)")
    elif OLD_6 in html:
        backup(INDEX)
        html = html.replace(OLD_6, NEW_6, 1)
        INDEX.write_text(html, encoding="utf-8")
        print("  ✓ Mix chart panel inserted (6-space indent)")
    else:
        print("  ❌ chart-ops-cost anchor not found")
        idx = html.find('chart-ops-cost')
        if idx > 0:
            print("  Context: " + repr(html[idx-30:idx+250]))
        raise SystemExit(1)


# ─────────────────────────────────────────────────────────────────────────
# 2. JS — render fn (uses same data; the absolute chart already fetches it)
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/3] Adding Cost mix chart renderer to app.v5.js...")
js = APP_JS.read_text(encoding="utf-8")

if "renderOpsCostMixChart" in js:
    print("  ⏭  renderOpsCostMixChart already present")
else:
    backup(APP_JS)

    NEW_FN = '''


/* ── Cost mix-% chart (M2.4.3) ───────────────────────────────────────── */
/* Frontend-only. Re-uses cost-structure-trend payload that the absolute  */
/* chart already fetches (renderOpsCostChart receives it).                */
/* The activation hook below calls renderOpsCostMixChart(_opsData.cost)   */
/* whenever the user opens the Cost sub-tab.                              */
function renderOpsCostMixChart(payload) {
  const data = payload?.data || [];
  if (!data.length) return;

  // Group by month, then compute per-bucket share within each month
  const months = [...new Set(data.map(d => d.month))].sort();
  const buckets = [...new Set(data.map(d => d.business_bucket))];

  // Build month -> bucket -> tl map
  const lookup = {};
  data.forEach(r => {
    if (!lookup[r.month]) lookup[r.month] = {};
    lookup[r.month][r.business_bucket] = r.amount_tl || 0;
  });

  // Per-bucket trace (% of monthly total)
  const bucketColor = {
    utilities:              '#4dabf7',
    maintenance_factory:    '#ffd43b',
    packaging:              '#74c0fc',
    factory_overhead:       '#a78bfa',
    outsourced_processing:  '#69db7c',
    logistics_distribution: '#ff8787',
  };

  const traces = buckets.map(b => {
    const y = months.map(m => {
      const monthRow = lookup[m] || {};
      const total = Object.values(monthRow).reduce((s, v) => s + (v || 0), 0);
      const val = monthRow[b] || 0;
      return total > 0 ? 100.0 * val / total : 0;
    });
    return {
      x: months, y: y,
      name: b,
      type: 'scatter', mode: 'lines',
      stackgroup: 'one',
      line: { width: 0.5, color: bucketColor[b] || C.muted },
      fillcolor: bucketColor[b] || C.muted,
      hovertemplate: `${b}: %{y:.1f}%<extra></extra>`,
    };
  });

  Plotly.newPlot('chart-ops-cost-mix', traces, {
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
  }, PLOTLY_CONFIG);
}
'''
    js = js.rstrip() + NEW_FN
    print("  ✓ renderOpsCostMixChart appended")


# Wire mix chart into the sub-tab activation. The mix chart re-uses the
# `cost` payload that loadInternal already fetched and passed to
# renderOpsCostChart. We add a parallel call so opening the Cost sub-tab
# triggers the mix render too.
WIRE_MARKER = "renderOpsCostMixChart hook"
if WIRE_MARKER in js:
    print("  ⏭  sub-tab hook already wired")
else:
    OLD_WIRE = '''      // loadCostKpis hook (M2.4.2)
      if (btn.dataset.sub === 'ops-cost' && typeof loadCostKpis === 'function') {
        if (!window._costKpisLoaded) {
          loadCostKpis();
          window._costKpisLoaded = true;
        }
      }'''

    NEW_WIRE = '''      // loadCostKpis hook (M2.4.2)
      if (btn.dataset.sub === 'ops-cost' && typeof loadCostKpis === 'function') {
        if (!window._costKpisLoaded) {
          loadCostKpis();
          window._costKpisLoaded = true;
        }
      }
      // renderOpsCostMixChart hook (M2.4.3) — uses _opsData.cost already fetched
      if (btn.dataset.sub === 'ops-cost' && typeof renderOpsCostMixChart === 'function') {
        if (!window._costMixLoaded && _opsData && _opsData.cost) {
          renderOpsCostMixChart(_opsData.cost);
          window._costMixLoaded = true;
        }
      }'''

    if OLD_WIRE in js:
        js = js.replace(OLD_WIRE, NEW_WIRE, 1)
        print("  ✓ sub-tab activation wired to renderOpsCostMixChart")
    else:
        print("  ⚠️  Cost KPI hook anchor not found — manual wiring may be needed")

APP_JS.write_text(js, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 3. Cache buster
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/3] Updating cache buster on app.v5.js reference...")
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
print("M2.4.3 — Cost Mix % chart complete.")
print("=" * 60)
print()
print("Cost Structure sub-tab now has:")
print("  - KPI strip (M2.4.2)")
print("  - Absolute TL chart (existing)")
print("  - NEW: Mix % chart (this iteration)")
print("  - Provisional logistics note")
print("  - Top 10 Cost Suppliers table (M2.4.1)")
print()
print("No uvicorn restart needed (frontend-only).")
print("Browser: hard-refresh, Operations Intelligence > Cost Structure.")
