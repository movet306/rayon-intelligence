"""
pi_1_7_panel_balance.py - Sync cotton sub-charts + nylon panel height.

Three concerns from the visual review:

  (1) Cotton sub-charts use inconsistent time windows.
      Top sub-chart (SunSirs) shows ~Apr 9-30 because that series is
      short. Bottom sub-chart (ICE) shows ~Feb-Apr because that series
      is long. They should share one window.
      Fix: in _renderCottonPanel, compute the union end / latest start
      across both series, then call _renderMultiLine with an explicit
      x-range override for both sub-charts so they line up.

  (2) Nylon panel has too much empty vertical space.
      The chart-wrap inside .chart-panel doesn't fill available height,
      leaving a big void below. Fix in CSS: let .chart-panel be a flex
      column where the chart-wrap grows to fill remaining space, and
      give the chart a sane min-height.

  (3) Left/right balance.
      Largely a consequence of (1) and (2). With cotton aligned to the
      same window and nylon filling its panel, the section will look
      symmetric without further intervention.

Implementation note for (1):
  _renderMultiLine already has the PI-1.7 common-start IIFE that uses
  layout.xaxis.range. Since each cotton sub-chart has only one trace,
  that IIFE just re-applies the trace's own range, which is exactly
  what we DON'T want for the panel-wide alignment. Solution: add an
  optional 4th argument `xRangeOverride` to _renderMultiLine. If
  provided, it wins; otherwise the IIFE keeps doing what it does for
  nylon (multi-trace common-start).

Idempotent.
"""
from pathlib import Path
import re
import sys
import time

REPO  = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"
CSS   = REPO / "dashboard" / "static" / "style.v5.css"

src = APPJS.read_text(encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# (1a) Add optional xRangeOverride parameter to _renderMultiLine
# ─────────────────────────────────────────────────────────────────────────────
OLD_SIG  = "function _renderMultiLine(elId, mats, data) {"
NEW_SIG  = "function _renderMultiLine(elId, mats, data, xRangeOverride) {"

# The PI-1.7 IIFE in the layout literal is what we need to make conditional.
OLD_IIFE = """      // PI-1.7: align x-axis to common-start across visible series.
      // For multi-trace charts (nylon), this prevents long-history series
      // from making short-history series look like they "spiked".
      // Single-trace charts are unaffected.
      ...(function _multiLineRange() {
        const fd = traces.filter(t => Array.isArray(t.x) && t.x.length).map(t => t.x[0]);
        const ld = traces.filter(t => Array.isArray(t.x) && t.x.length).map(t => t.x[t.x.length - 1]);
        if (!fd.length) return {};
        const start = fd.sort().reverse()[0];
        const end   = ld.sort().reverse()[0];
        return { xaxis: { range: [start, end] } };
      })(),"""

NEW_IIFE = """      // PI-1.7: align x-axis. Caller can pass xRangeOverride [start, end]
      // (used by _renderCottonPanel to keep both sub-charts on the same
      // window). Otherwise, fall back to common-start across visible series
      // (good for multi-trace charts like the nylon family).
      ...(function _multiLineRange() {
        if (Array.isArray(xRangeOverride) && xRangeOverride.length === 2) {
          return { xaxis: { range: xRangeOverride } };
        }
        const fd = traces.filter(t => Array.isArray(t.x) && t.x.length).map(t => t.x[0]);
        const ld = traces.filter(t => Array.isArray(t.x) && t.x.length).map(t => t.x[t.x.length - 1]);
        if (!fd.length) return {};
        const start = fd.sort().reverse()[0];
        const end   = ld.sort().reverse()[0];
        return { xaxis: { range: [start, end] } };
      })(),"""

if "xRangeOverride" in src:
    print("[skip] (1a) xRangeOverride already added to _renderMultiLine")
else:
    if OLD_SIG not in src:
        print("[X]    (1a) _renderMultiLine signature not found")
        sys.exit(1)
    if OLD_IIFE not in src:
        print("[X]    (1a) PI-1.7 IIFE block not found in expected form")
        sys.exit(1)
    src = src.replace(OLD_SIG, NEW_SIG, 1)
    src = src.replace(OLD_IIFE, NEW_IIFE, 1)
    print("[OK]   (1a) _renderMultiLine: optional xRangeOverride added")

# ─────────────────────────────────────────────────────────────────────────────
# (1b) Update _renderCottonPanel to compute panel-wide range and pass it.
# ─────────────────────────────────────────────────────────────────────────────
OLD_COTTON_RENDER = """  // PI-1.6: render SunSirs and ICE on separate sub-charts so they no longer
  // share a y-axis. Different markets, different price scales.
  _renderMultiLine('chart-cotton-spot', [
    { key: 'cotton_lint', color: C.orange, label: 'SunSirs China Spot (USD/t)' },
  ], data);
  _renderMultiLine('chart-cotton-futures', [
    { key: 'cotton_lint_futures', color: C.blue, label: 'ICE Futures (USD/t)' },
  ], data);"""

NEW_COTTON_RENDER = """  // PI-1.6: render SunSirs and ICE on separate sub-charts so they no longer
  // share a y-axis. Different markets, different price scales.
  // PI-1.7 followup: ensure both sub-charts use the same x-axis window so
  // the user reads them as one comparison, not two unrelated time series.
  // We pick the latest first-date and the latest last-date across the two
  // series so neither sub-chart shows extrapolated empty space and short
  // series aren't squeezed into a tiny corner.
  const _spotSer  = data['cotton_lint']?.series          || [];
  const _futSer   = data['cotton_lint_futures']?.series  || [];
  let _xRange = null;
  if (_spotSer.length && _futSer.length) {
    const _firsts = [_spotSer[0].date, _futSer[0].date].sort().reverse();
    const _lasts  = [
      _spotSer[_spotSer.length - 1].date,
      _futSer[_futSer.length - 1].date,
    ].sort().reverse();
    _xRange = [_firsts[0], _lasts[0]];
  }
  _renderMultiLine('chart-cotton-spot', [
    { key: 'cotton_lint', color: C.orange, label: 'SunSirs China Spot (USD/t)' },
  ], data, _xRange);
  _renderMultiLine('chart-cotton-futures', [
    { key: 'cotton_lint_futures', color: C.blue, label: 'ICE Futures (USD/t)' },
  ], data, _xRange);"""

if "PI-1.7 followup: ensure both sub-charts use the same x-axis window" in src:
    print("[skip] (1b) cotton panel already passes xRangeOverride")
elif OLD_COTTON_RENDER in src:
    src = src.replace(OLD_COTTON_RENDER, NEW_COTTON_RENDER)
    print("[OK]   (1b) cotton panel computes panel-wide range and passes to both sub-charts")
else:
    print("[X]    (1b) cotton render block not found in expected form")
    sys.exit(1)

APPJS.write_text(src, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# (2) CSS: nylon panel chart fills available height. Apply to all chart-panel
# children with a chart-wrap so the rule benefits any future panels too.
# ─────────────────────────────────────────────────────────────────────────────
css_src = CSS.read_text(encoding="utf-8")

CSS_HEADER = "/* ── PI-1.7 followup: chart-panel chart fills available height"

CSS_BLOCK = """

/* ── PI-1.7 followup: chart-panel chart fills available height ────────────── */
/* When two chart-panels sit side by side and one has dense content (e.g. the
   cotton panel with two stacked sub-charts) and the other has just one chart
   (e.g. the nylon panel), the lighter panel ends up looking half-empty. Make
   the chart-wrap stretch so the chart fills the available vertical space. */
.chart-panel {
  display: flex;
  flex-direction: column;
}
.chart-panel > .chart-wrap {
  flex: 1 1 auto;
  min-height: 280px;
}
"""

if CSS_HEADER in css_src:
    print("[skip] (2) chart-panel flex CSS already present")
else:
    CSS.write_text(css_src.rstrip() + CSS_BLOCK, encoding="utf-8")
    print("[OK]   (2) chart-panel flex CSS appended (nylon chart will fill its panel)")

# ─────────────────────────────────────────────────────────────────────────────
# (3) Cache busters
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m_js = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m_js:
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    print(f"[OK]   (3a) app.v5.js cache buster -> {ts}")
m_css = re.search(r'style\.v5\.css\?v=(\S+?)"', html)
if m_css:
    html = re.sub(r'style\.v5\.css\?v=\S+?"', f'style.v5.css?v={ts}"', html)
    print(f"[OK]   (3b) style.v5.css cache buster -> {ts}")
INDEX.write_text(html, encoding="utf-8")

print()
print("Done. Browser: Ctrl+Shift+R.")
print()
print("Expected:")
print("  - Cotton sub-charts: both span the same date range (panel-wide window).")
print("  - Nylon panel: chart fills the panel, no big empty area below.")
print("  - Left and right cotton/nylon panels look balanced.")
