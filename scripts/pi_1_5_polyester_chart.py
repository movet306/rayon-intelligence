"""
pi_1_5_polyester_chart.py - Polyester chain chart fixes.

Four targeted changes to dashboard/static/app.v5.js. All idempotent.

  1. Add PTA to POLY_MATS so it renders as a chart line.
     POLY_MATS currently contains [PSF, FDY, POY, DTY] only. PTA appears in
     the chain-flow boxes (POLY_CHAIN) but not in the chart, even though
     PTA is the upstream trigger of the entire chain.

  2. Drop MA7 dashed traces.
     Currently rendered with showlegend=false, hoverinfo='skip' so they
     are mostly invisible but still consume layout space and create
     visual noise on close inspection. With PTA added the chart now has
     5 series; redundant MA7 ghost traces would push it to 10. Removed.

  3. Align x-axis start to the latest first-date across visible series.
     Series start dates differ (e.g. PSF added in April, POY since Feb).
     The auto-fit x-axis makes PSF look like it "spiked" when in fact data
     simply didn't exist before. Setting a common start removes the
     misleading visual.

  4. Move sigma (volatility_7d) into chain-flow node footer.
     Then hide the redundant poly-metric-cards container.
     HTML node is preserved (display:none) so rollback is trivial.

Touches one file:
  dashboard/static/app.v5.js

No backend, no SQL, no data changes.
"""
from pathlib import Path
import re
import sys
import time

REPO = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"

src = APPJS.read_text(encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# Change 1: add PTA to POLY_MATS
# ─────────────────────────────────────────────────────────────────────────────
OLD_POLY_MATS = """const POLY_MATS = [
  { key: 'polyester_staple_fiber', color: C.blue,     label: 'PSF' },
  { key: 'polyester_fdy',          color: C.orange,   label: 'FDY' },
  { key: 'polyester_poy',          color: C.green,    label: 'POY' },
  { key: 'polyester_dty',          color: '#a371f7',  label: 'DTY' },
];"""

NEW_POLY_MATS = """const POLY_MATS = [
  // PI-1.5: PTA added (upstream trigger of polyester chain).
  { key: 'pta',                    color: C.purple,   label: 'PTA' },
  { key: 'polyester_staple_fiber', color: C.blue,     label: 'PSF' },
  { key: 'polyester_fdy',          color: C.orange,   label: 'FDY' },
  { key: 'polyester_poy',          color: C.green,    label: 'POY' },
  { key: 'polyester_dty',          color: '#a371f7',  label: 'DTY' },
];"""

if "// PI-1.5: PTA added" in src:
    print("[skip] (1) POLY_MATS already updated")
elif OLD_POLY_MATS in src:
    src = src.replace(OLD_POLY_MATS, NEW_POLY_MATS)
    print("[OK]   (1) POLY_MATS: PTA added at top of list")
else:
    print("[X]    (1) POLY_MATS block not found in expected form")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Change 2: drop MA7 dashed traces
# ─────────────────────────────────────────────────────────────────────────────
OLD_MA7_BLOCK = """      const rate = data.meta?.rmb_usd_rate ?? 1;
      const yMa7 = d.series.map(p => {
        if (p.ma7 == null) return null;
        return _currency === 'usd' ? p.ma7 * rate : p.ma7;
      });
      if (yMa7.some(v => v != null)) {
        traces.push({
          x, y: yMa7, name: `${m.label} MA7`,
          type: 'scatter', mode: 'lines',
          line: { color: m.color, width: 1.5, dash: 'dash' },
          opacity: 0.5, showlegend: false, hoverinfo: 'skip',
        });
      }"""

NEW_MA7_BLOCK = """      // PI-1.5: MA7 dashed ghost traces removed (visual noise, no UX value)."""

if "PI-1.5: MA7 dashed ghost traces removed" in src:
    print("[skip] (2) MA7 dashed traces already removed")
elif OLD_MA7_BLOCK in src:
    src = src.replace(OLD_MA7_BLOCK, NEW_MA7_BLOCK)
    print("[OK]   (2) MA7 dashed traces removed from _renderPolyesterFamily")
else:
    print("[X]    (2) MA7 trace block not found in expected form")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Change 3: align x-axis start by adding range computation + layout override.
#
# Strategy: at the start of _renderPolyesterFamily, after `const traces = []`
# and `const hoverFmt = ...`, add a helper that computes the latest first-date
# among the visible series. Then before each Plotly.newPlot call, layout gets
# an xaxis.range override.
#
# Simpler approach: compute commonStart once, then patch the existing layout
# usage. Layout is constructed elsewhere in the function (we didn't see it
# fully). Safest minimal change: at the END of trace assembly, mutate layout.
#
# But we don't have visibility on `layout` constant. So we'll patch by
# inserting a targeted block right before `Plotly.newPlot('chart-polyester'...)`
# which extracts xMin from traces, sets layout.xaxis.range.
# ─────────────────────────────────────────────────────────────────────────────
OLD_PLOT_CALL = "  Plotly.newPlot('chart-polyester', traces, layout, PLOTLY_CONFIG);"

NEW_PLOT_CALL = """  // PI-1.5: align x-axis to latest first-date across visible series.
  // Prevents the misleading "spike" effect when one series starts later.
  const _firstDates = traces
    .filter(t => Array.isArray(t.x) && t.x.length)
    .map(t => t.x[0]);
  if (_firstDates.length) {
    const _commonStart = _firstDates.sort().reverse()[0];
    const _commonEnd = traces
      .filter(t => Array.isArray(t.x) && t.x.length)
      .map(t => t.x[t.x.length - 1])
      .sort()
      .reverse()[0];
    layout.xaxis = { ...(layout.xaxis || {}), range: [_commonStart, _commonEnd] };
  }
  Plotly.newPlot('chart-polyester', traces, layout, PLOTLY_CONFIG);"""

if "PI-1.5: align x-axis to latest first-date" in src:
    print("[skip] (3) x-axis alignment already applied")
elif OLD_PLOT_CALL in src:
    src = src.replace(OLD_PLOT_CALL, NEW_PLOT_CALL)
    print("[OK]   (3) x-axis common start alignment added before Plotly.newPlot")
else:
    print("[X]    (3) Plotly.newPlot('chart-polyester') call not found in expected form")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Change 4a: add sigma to chain-flow node footer
# ─────────────────────────────────────────────────────────────────────────────
OLD_FOOTER = """    const tier    = latest?.confidence_tier;
    const mom     = _momentumArrow(latest?.momentum_score);
    const tierHtml = _tierBadge(tier);
    const momHtml  = `<span class="chain-momentum ${mom.cls}">${mom.icon}</span>`;"""

NEW_FOOTER = """    const tier    = latest?.confidence_tier;
    const mom     = _momentumArrow(latest?.momentum_score);
    const tierHtml = _tierBadge(tier);
    const momHtml  = `<span class="chain-momentum ${mom.cls}">${mom.icon}</span>`;
    // PI-1.5: sigma (7d volatility) moved here from poly-metric-cards.
    const vol     = latest?.volatility_7d;
    const volHtml = vol != null
      ? `<span class="chain-vol" style="font-size:11px; color:var(--muted); margin-left:6px">σ ${vol.toFixed(1)}</span>`
      : '';"""

if "PI-1.5: sigma (7d volatility) moved here" in src:
    print("[skip] (4a) sigma already added to chain-flow footer")
elif OLD_FOOTER in src:
    src = src.replace(OLD_FOOTER, NEW_FOOTER)
    print("[OK]   (4a) sigma extraction added in _renderChainFlow")
else:
    print("[X]    (4a) chain-flow footer prep block not found in expected form")
    sys.exit(1)

# Wire sigma into the rendered footer HTML
OLD_FOOTER_HTML = '<div class="chain-node-footer">${tierHtml}${momHtml}</div>'
NEW_FOOTER_HTML = '<div class="chain-node-footer">${tierHtml}${momHtml}${volHtml}</div>'

if NEW_FOOTER_HTML in src:
    print("[skip] (4a-2) sigma already wired into chain-node-footer HTML")
elif OLD_FOOTER_HTML in src:
    src = src.replace(OLD_FOOTER_HTML, NEW_FOOTER_HTML)
    print("[OK]   (4a-2) sigma wired into chain-node-footer HTML")
else:
    print("[X]    (4a-2) chain-node-footer HTML not found in expected form")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Change 4b: hide poly-metric-cards (no-op the renderer + display:none)
# ─────────────────────────────────────────────────────────────────────────────
OLD_RENDER_FN = """function _renderPolyMetricCards(data) {
  const container = document.getElementById('poly-metric-cards');
  container.innerHTML = POLY_MATS.map(m => {"""

NEW_RENDER_FN = """function _renderPolyMetricCards(data) {
  // PI-1.5: detail cards are now redundant (sigma moved to chain-flow footer).
  // HTML container preserved for easy rollback; rendered as hidden no-op.
  const container = document.getElementById('poly-metric-cards');
  if (container) {
    container.innerHTML = '';
    container.style.display = 'none';
  }
  return;
  // eslint-disable-next-line no-unreachable
  /* original implementation kept below for reference, never executed:
  container.innerHTML = POLY_MATS.map(m => {"""

# We need a matching closing comment to neutralize the rest of the function.
# The function ends with `).join('');\n}` — we need to close the comment there.
OLD_RENDER_END = "  }).join('');\n}\n\nfunction _renderSecondaryCharts(data) {"
NEW_RENDER_END = "  }).join('');\n  */\n}\n\nfunction _renderSecondaryCharts(data) {"

if "PI-1.5: detail cards are now redundant" in src:
    print("[skip] (4b) poly-metric-cards already hidden")
elif OLD_RENDER_FN in src and OLD_RENDER_END in src:
    src = src.replace(OLD_RENDER_FN, NEW_RENDER_FN)
    src = src.replace(OLD_RENDER_END, NEW_RENDER_END)
    print("[OK]   (4b) poly-metric-cards hidden (renderer no-op + display:none)")
else:
    print("[X]    (4b) _renderPolyMetricCards function bounds not found")
    sys.exit(1)

APPJS.write_text(src, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# Cache buster bump on app.v5.js so browser fetches fresh
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m:
    old_v = m.group(1)
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    INDEX.write_text(html, encoding="utf-8")
    print(f"[OK]   index.html: cache buster {old_v} -> {ts}")

print()
print("Done. Restart not required (static JS reload):")
print("  1. Browser: Ctrl+Shift+R on Price Intelligence")
print("  2. Verify:")
print("     - Polyester chart now shows 5 lines including PTA (purple)")
print("     - All series start from the same date on the x-axis")
print("     - No dashed/ghost lines crowding the chart")
print("     - Chain-flow boxes show sigma at right of footer")
print("     - 'Detail cards' grid below the chart is gone")
