"""
M2.2.3 — Procurement mix % over time chart.

Approach: frontend-only — reuses existing /api/internal/procurement-trend
payload, normalizes per-month bucket totals to % share. No new endpoint.

Layout: stacked underneath the existing absolute TL chart (Layout B).

Backups: .bak_m22_3 suffix
"""
from pathlib import Path
import re

INDEX  = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m22_3")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. HTML — add second chart-panel after the absolute TL one
# ─────────────────────────────────────────────────────────────────────────
print("[1/2] Inserting Mix % chart container into index.html...")
html = INDEX.read_text(encoding="utf-8")

if 'id="chart-ops-procurement-mix"' in html:
    print("  ⏭  Mix % container already present")
else:
    # The existing absolute chart panel:
    #   <div class="chart-panel" style="margin-bottom:16px">
    #     <div class="chart-panel-title">Monthly Procurement by Bucket (TL)</div>
    #     <div class="chart-wrap" id="chart-ops-procurement"></div>
    #   </div>
    # Insert new chart panel right after this one.

    OLD = '''<div class="chart-panel" style="margin-bottom:16px">
          <div class="chart-panel-title">Monthly Procurement by Bucket (TL)</div>
          <div class="chart-wrap" id="chart-ops-procurement"></div>
        </div>'''

    NEW = '''<div class="chart-panel" style="margin-bottom:16px">
          <div class="chart-panel-title">Monthly Procurement by Bucket (TL)</div>
          <div class="chart-wrap" id="chart-ops-procurement"></div>
        </div>
        <div class="chart-panel" style="margin-bottom:16px">
          <div class="chart-panel-title">Procurement Mix % over time</div>
          <div class="chart-wrap" id="chart-ops-procurement-mix"></div>
        </div>'''

    if OLD not in html:
        print("  ❌ absolute chart panel anchor not found")
        # Print what's actually around the area for debugging
        idx = html.find('chart-ops-procurement')
        if idx > 0:
            print("  Context near chart-ops-procurement:")
            print("  " + repr(html[idx-100:idx+250]))
        raise SystemExit(1)

    backup(INDEX)
    html = html.replace(OLD, NEW, 1)
    INDEX.write_text(html, encoding="utf-8")
    print("  ✓ Mix % chart container inserted after absolute TL chart")


# ─────────────────────────────────────────────────────────────────────────
# 2. JS — add renderOpsProcurementMixChart() and call it from the loader
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/2] Adding Mix % renderer to app.v5.js...")
js = APP_JS.read_text(encoding="utf-8")

JS_MARKER = "function renderOpsProcurementMixChart"

if JS_MARKER in js:
    print("  ⏭  Mix chart renderer already present")
else:
    # New renderer — same data shape as renderOpsProcurementChart, but normalize per month
    NEW_FN = '''

/* ── Procurement mix % chart (M2.2.3) ─────────────────────────────────── */
function renderOpsProcurementMixChart(payload) {
  const data = payload?.data || [];
  if (!data.length) return;

  const months = [...new Set(data.map(d => d.month))].sort();
  const buckets = payload.buckets || [
    'raw_material_yarn', 'raw_material_chemical',
    'raw_material_dye', 'raw_material_greige_fabric',
  ];
  const colorMap = {
    raw_material_yarn:           C.blue,
    raw_material_chemical:       C.purple,
    raw_material_dye:            C.orange,
    raw_material_greige_fabric:  C.green,
  };
  const labelMap = {
    raw_material_yarn:           'Yarn',
    raw_material_chemical:       'Chemical',
    raw_material_dye:            'Dye',
    raw_material_greige_fabric:  'Greige fabric',
  };

  // Per-month totals across all buckets
  const monthTotals = {};
  months.forEach(m => { monthTotals[m] = 0; });
  data.forEach(d => {
    if (buckets.includes(d.business_bucket)) {
      monthTotals[d.month] = (monthTotals[d.month] || 0) + (d.amount_tl || 0);
    }
  });

  const traces = buckets.map(bucket => {
    const byMonth = Object.fromEntries(
      data.filter(d => d.business_bucket === bucket)
          .map(d => [d.month, d.amount_tl || 0])
    );
    return {
      x: months,
      y: months.map(m => {
        const total = monthTotals[m] || 0;
        if (total === 0) return 0;
        return ((byMonth[m] || 0) / total) * 100;
      }),
      name: labelMap[bucket] || bucket,
      type: 'bar',
      marker: { color: colorMap[bucket] || C.muted, opacity: 0.85 },
      hovertemplate: `${labelMap[bucket] || bucket}: %{y:.1f}%<extra></extra>`,
    };
  });

  Plotly.newPlot('chart-ops-procurement-mix', traces, {
    ...PLOTLY_BASE,
    height: 360,
    barmode: 'stack',
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

    # Insert immediately after the existing renderOpsProcurementChart function
    # Find that function and the closing brace (matching braces).
    fn_start = js.find("function renderOpsProcurementChart(payload) {")
    if fn_start < 0:
        print("  ❌ existing renderOpsProcurementChart function not found")
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
    fn_end = i  # position right after closing }

    backup(APP_JS)
    js = js[:fn_end] + NEW_FN + js[fn_end:]
    print("  ✓ renderOpsProcurementMixChart inserted after existing chart fn")


# Wire the call into the loader. Find where renderOpsProcurementChart(proc) is called.
WIRE_MARKER = "renderOpsProcurementMixChart(proc);"
if WIRE_MARKER in js:
    print("  ⏭  call already wired")
else:
    OLD_CALL = "renderOpsProcurementChart(proc);"
    NEW_CALL = "renderOpsProcurementChart(proc);\n    renderOpsProcurementMixChart(proc);"

    if OLD_CALL in js:
        js = js.replace(OLD_CALL, NEW_CALL, 1)
        print("  ✓ Mix chart call wired into loader")
    else:
        print("  ⚠️  could not find renderOpsProcurementChart(proc) call — manual wiring needed")

APP_JS.write_text(js, encoding="utf-8")


print()
print("=" * 60)
print("M2.2.3 — Procurement Mix % chart complete.")
print("=" * 60)
print()
print("Layout: absolute TL chart (top) + mix % chart (bottom), same data.")
print()
print("uvicorn does NOT need restart (frontend-only change).")
print("Browser: hard-refresh (Ctrl+Shift+R) → Operations Intelligence > Procurement.")
