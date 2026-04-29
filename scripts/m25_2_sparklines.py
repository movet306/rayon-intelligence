"""
M2.5.2 — Mini sparklines on Overview KPI wall.

Frontend-only. Reuses _opsData (proc/cost/rev) already loaded by loadInternal().
Each of the 11 KPI cards gets a small inline SVG sparkline showing the last
12 months of the corresponding metric, rendered below the existing stat-fx
line.

Mapping (metric_key -> data source):
  Procurement (proc.data; rows have business_bucket + amount_tl):
    total_procurement -> sum across all 4 raw_material_* buckets per month
    yarn              -> raw_material_yarn
    chemical_dye      -> raw_material_chemical + raw_material_dye per month
    greige            -> raw_material_greige_fabric

  Cost (cost.data; same shape):
    utilities         -> utilities
    maintenance       -> maintenance_factory
    fason             -> outsourced_processing
    factory_overhead  -> factory_overhead

  Revenue (rev.data; one row per month with named columns):
    core_sales        -> core_sales_tl
    fason_revenue     -> fason_revenue_tl
    net_revenue       -> net_revenue_tl

Backups: .bak_m25_2 suffix.
"""
from pathlib import Path

INDEX  = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")
CSS    = Path("dashboard/static/style.v5.css")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m25_2")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. JS — extend buildKpiCard to embed an SVG sparkline
# ─────────────────────────────────────────────────────────────────────────
print("[1/3] Extending buildKpiCard with sparkline support...")
js = APP_JS.read_text(encoding="utf-8")

if "_kpiSparklineSeries" in js:
    print("  ⏭  sparkline helpers already present")
else:
    backup(APP_JS)

    # Helpers + sparkline series resolver. Inserted just before buildKpiCard.
    # Uses _opsData (set in loadInternal).
    HELPERS = '''
/* ── Mini sparklines for Overview KPI wall (M2.5.2) ───────────────────── */
/* Each KPI card resolves its 12-month series from the _opsData payload    */
/* that loadInternal already fetched. No new endpoint.                     */

function _kpiSparklineSeries(metricKey, panel) {
  // Returns array of numbers (length up to 12) or [] if no data available.
  const opsData = (typeof _opsData !== 'undefined') ? _opsData : null;
  if (!opsData) return [];

  // ── Procurement KPIs ───────────────────────────────────────────────────
  if (panel === 'procurement') {
    const rows = opsData?.proc?.data || [];
    if (!rows.length) return [];

    // Group rows by month, summing per requested metric_key
    const byMonth = {};
    rows.forEach(r => {
      const m = r.month;
      if (!byMonth[m]) byMonth[m] = 0;
      const b = r.business_bucket;
      let include = false;
      if (metricKey === 'total_procurement') {
        include = b && b.indexOf('raw_material_') === 0;
      } else if (metricKey === 'yarn') {
        include = (b === 'raw_material_yarn');
      } else if (metricKey === 'chemical_dye') {
        include = (b === 'raw_material_chemical' || b === 'raw_material_dye');
      } else if (metricKey === 'greige') {
        include = (b === 'raw_material_greige_fabric');
      }
      if (include) byMonth[m] += (r.amount_tl || 0);
    });
    const months = Object.keys(byMonth).sort();
    const last12 = months.slice(-12);
    return last12.map(m => byMonth[m]);
  }

  // ── Cost Structure KPIs ────────────────────────────────────────────────
  if (panel === 'cost_structure') {
    const rows = opsData?.cost?.data || [];
    if (!rows.length) return [];
    const targetBucket =
      metricKey === 'utilities'        ? 'utilities' :
      metricKey === 'maintenance'      ? 'maintenance_factory' :
      metricKey === 'fason'            ? 'outsourced_processing' :
      metricKey === 'factory_overhead' ? 'factory_overhead' : null;
    if (!targetBucket) return [];

    const byMonth = {};
    rows.forEach(r => {
      if (r.business_bucket === targetBucket) {
        byMonth[r.month] = (byMonth[r.month] || 0) + (r.amount_tl || 0);
      }
    });
    const months = Object.keys(byMonth).sort();
    return months.slice(-12).map(m => byMonth[m]);
  }

  // ── Revenue KPIs ───────────────────────────────────────────────────────
  if (panel === 'revenue_reality') {
    const rows = opsData?.rev?.data || [];
    if (!rows.length) return [];
    const col =
      metricKey === 'core_sales'    ? 'core_sales_tl' :
      metricKey === 'fason_revenue' ? 'fason_revenue_tl' :
      metricKey === 'net_revenue'   ? 'net_revenue_tl' : null;
    if (!col) return [];

    const sorted = rows.slice().sort((a, b) => (a.month < b.month ? -1 : 1));
    return sorted.slice(-12).map(r => r[col] || 0);
  }

  return [];
}

function _renderSparklineSvg(series, opts = {}) {
  if (!series || series.length < 2) return '';
  const w = opts.width  || 110;
  const h = opts.height || 22;
  const pad = 1;

  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = (max - min) || 1;
  const stepX = (w - 2 * pad) / (series.length - 1);

  const points = series.map((v, i) => {
    const x = pad + i * stepX;
    const y = h - pad - ((v - min) / range) * (h - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  // Trend color: compare last vs first half average
  const half = Math.floor(series.length / 2);
  const firstAvg = series.slice(0, half).reduce((s, v) => s + v, 0) / Math.max(half, 1);
  const lastAvg  = series.slice(-half).reduce((s, v) => s + v, 0) / Math.max(half, 1);
  const trend = lastAvg > firstAvg * 1.05 ? 'up'
              : lastAvg < firstAvg * 0.95 ? 'down'
              : 'flat';

  // Dot at the last point (current value emphasis)
  const lastX = pad + (series.length - 1) * stepX;
  const lastY = h - pad - ((series[series.length - 1] - min) / range) * (h - 2 * pad);

  return `
    <svg class="kpi-sparkline kpi-sparkline-${trend}" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
      <polyline fill="none" stroke="currentColor" stroke-width="1.2" points="${points}" />
      <circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="1.8" fill="currentColor" />
    </svg>
  `;
}
'''

    # Find buildKpiCard and inject helpers right before it
    buildkpi_idx = js.find("function buildKpiCard(")
    if buildkpi_idx < 0:
        print("  ❌ buildKpiCard not found")
        raise SystemExit(1)

    js = js[:buildkpi_idx] + HELPERS + "\n" + js[buildkpi_idx:]
    print("  ✓ sparkline helpers inserted before buildKpiCard")


# Now patch buildKpiCard's return template to include the sparkline
if "kpi-sparkline-wrap" in js:
    print("  ⏭  buildKpiCard return already patched")
else:
    OLD_RETURN = '''  return `
    <div class="stat-card">
      <div class="stat-label">${metric.metric_label}</div>
      <div class="stat-value">${tlMain}</div>
      <div class="stat-sub ${yoyCls}">${yoy ? `YoY ${yoy}` : '—'}</div>
      ${fxText ? `<div class="stat-fx">${fxText}</div>` : ''}
      ${contextHint}
    </div>
  `;'''

    NEW_RETURN = '''  // Sparkline (M2.5.2) — uses _opsData already fetched by loadInternal
  const _sparkSeries = (typeof _kpiSparklineSeries === 'function')
    ? _kpiSparklineSeries(metric.metric_key, metric.panel) : [];
  const _sparkSvg = (typeof _renderSparklineSvg === 'function' && _sparkSeries.length >= 2)
    ? _renderSparklineSvg(_sparkSeries) : '';
  const _sparkBlock = _sparkSvg
    ? `<div class="kpi-sparkline-wrap" title="last 12 months">${_sparkSvg}</div>`
    : '';

  return `
    <div class="stat-card">
      <div class="stat-label">${metric.metric_label}</div>
      <div class="stat-value">${tlMain}</div>
      <div class="stat-sub ${yoyCls}">${yoy ? `YoY ${yoy}` : '—'}</div>
      ${fxText ? `<div class="stat-fx">${fxText}</div>` : ''}
      ${_sparkBlock}
      ${contextHint}
    </div>
  `;'''

    if NEW_RETURN.split("return")[1] in js:
        print("  ⏭  return already patched")
    elif OLD_RETURN not in js:
        print("  ❌ buildKpiCard return template not matching")
        raise SystemExit(1)
    else:
        js = js.replace(OLD_RETURN, NEW_RETURN, 1)
        print("  ✓ buildKpiCard return now embeds sparkline")

APP_JS.write_text(js, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 2. CSS — sparkline styling
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/3] Adding CSS for sparklines...")
css = CSS.read_text(encoding="utf-8")

CSS_MARKER = "/* === Overview KPI sparklines (M2.5.2) === */"
if CSS_MARKER in css:
    print("  ⏭  CSS already present")
else:
    backup(CSS)
    CSS_BLOCK = '''

/* === Overview KPI sparklines (M2.5.2) === */
/* 12-month inline trend, embedded in stat-card. Color reflects trend.   */
.kpi-sparkline-wrap {
  margin-top: 6px;
  line-height: 0;          /* removes inline-svg baseline gap */
  display: flex;
  align-items: center;
}
.kpi-sparkline {
  opacity: 0.85;
}
.kpi-sparkline-up   { color: #51cf66; }   /* rising trend  — green  */
.kpi-sparkline-down { color: #ff6b6b; }   /* falling trend — red    */
.kpi-sparkline-flat { color: #868e96; }   /* stable        — muted  */
'''
    css = css.rstrip() + CSS_BLOCK
    CSS.write_text(css, encoding="utf-8")
    print("  ✓ sparkline CSS appended")


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
print("M2.5.2 — Overview KPI sparklines complete.")
print("=" * 60)
print()
print("Each of the 11 Overview KPI cards now shows a 12-month sparkline:")
print("  - green if the trend is rising (last half avg > first half by 5%)")
print("  - red if falling")
print("  - muted gray if stable")
print()
print("No backend / no uvicorn restart needed (frontend-only).")
print("Browser: hard-refresh, Operations Intelligence > Overview.")
