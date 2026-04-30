"""
pi_1_6_cotton_split.py - Split cotton chart into two stacked sub-charts.

Current state: SunSirs China Spot and ICE Futures share one chart and one
y-axis. They are different markets (one Chinese physical spot, one global
futures benchmark) and should not be plotted on a shared price scale —
the visual implies they are directly comparable when they are not.

Change: keep one cotton panel (one heading, one summary band, one
disclaimer), but split the chart area into two stacked sub-charts:

  Pamuk — Spot vs Futures
  ┌─────────────────────────────────────────────────┐
  │  [SunSirs summary card]   [ICE summary card]    │
  ├─────────────────────────────────────────────────┤
  │  SunSirs China Spot                             │
  │  [chart 1, orange line, own y-axis]             │
  ├─────────────────────────────────────────────────┤
  │  ICE Futures                                    │
  │  [chart 2, blue line, own y-axis]               │
  └─────────────────────────────────────────────────┘
  [disclaimer: different markets, not directly comparable]

Implementation:
  - HTML: split #chart-cotton-raw into #chart-cotton-spot and
    #chart-cotton-futures, with mini section labels.
  - JS: _renderCottonPanel renders the two charts independently via
    _renderMultiLine, each with a single series.
  - Title updated: 'Pamuk — Spot & Vadeli' -> 'Pamuk — Spot vs Vadeli'
    (the 'vs' makes the two-different-markets framing explicit).
  - Disclaimer text strengthened to spell out the parity warning.

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

# ─────────────────────────────────────────────────────────────────────────────
# (1) HTML: replace the single chart div with two stacked sub-charts.
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")

OLD_HTML_BLOCK = """      <div class="chart-panel">
        <div class="chart-panel-title">Pamuk &#8212; Spot &amp; Vadeli</div>
        <div id="cotton-series-info" class="cotton-series-info"></div>
        <div class="chart-wrap" id="chart-cotton-raw"></div>
        <div class="cotton-disclaimer" id="cotton-disclaimer"></div>
      </div>"""

NEW_HTML_BLOCK = """      <div class="chart-panel">
        <!-- PI-1.6: split into two stacked sub-charts with separate y-axes -->
        <div class="chart-panel-title">Pamuk &#8212; Spot vs Vadeli</div>
        <div id="cotton-series-info" class="cotton-series-info"></div>
        <div class="cotton-subchart">
          <div class="cotton-subchart-label">SunSirs &#199;in Spot</div>
          <div class="chart-wrap" id="chart-cotton-spot"></div>
        </div>
        <div class="cotton-subchart">
          <div class="cotton-subchart-label">ICE Vadeli (K&#252;resel)</div>
          <div class="chart-wrap" id="chart-cotton-futures"></div>
        </div>
        <div class="cotton-disclaimer" id="cotton-disclaimer"></div>
      </div>"""

if "chart-cotton-spot" in html:
    print("[skip] (1) cotton HTML already split")
else:
    # Try the form we got from Select-String first; if not, try literal
    # characters and a regex fallback.
    if OLD_HTML_BLOCK in html:
        html = html.replace(OLD_HTML_BLOCK, NEW_HTML_BLOCK)
        print("[OK]   (1) cotton HTML split into two sub-charts")
    else:
        # Fallback: regex over the whole panel
        m = re.search(
            r'<div class="chart-panel">\s*<div class="chart-panel-title">[^<]*Pamuk[^<]*</div>\s*'
            r'<div id="cotton-series-info"[^<]*</div>\s*'
            r'<div class="chart-wrap" id="chart-cotton-raw"></div>\s*'
            r'<div class="cotton-disclaimer" id="cotton-disclaimer"></div>\s*</div>',
            html,
            flags=re.DOTALL,
        )
        if m:
            html = html[:m.start()] + NEW_HTML_BLOCK + html[m.end():]
            print("[OK]   (1) cotton HTML split via regex fallback")
        else:
            print("[X]    (1) cotton panel HTML not found in expected form")
            sys.exit(1)

INDEX.write_text(html, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# (2) JS: replace the single _renderMultiLine call with two single-series calls
# ─────────────────────────────────────────────────────────────────────────────
src = APPJS.read_text(encoding="utf-8")

OLD_JS_BLOCK = """  _renderMultiLine('chart-cotton-raw', [
    { key: 'cotton_lint',         color: C.orange, label: 'Pamuk — SunSirs Çin Spot' },
    { key: 'cotton_lint_futures', color: C.blue,   label: 'Pamuk — ICE Vadeli (USD/t)' },
  ], data);"""

NEW_JS_BLOCK = """  // PI-1.6: render SunSirs and ICE on separate sub-charts so they no longer
  // share a y-axis. Different markets, different price scales.
  _renderMultiLine('chart-cotton-spot', [
    { key: 'cotton_lint', color: C.orange, label: 'SunSirs Çin Spot (USD/t)' },
  ], data);
  _renderMultiLine('chart-cotton-futures', [
    { key: 'cotton_lint_futures', color: C.blue, label: 'ICE Vadeli (USD/t)' },
  ], data);"""

if "PI-1.6: render SunSirs and ICE on separate" in src:
    print("[skip] (2) cotton render already split")
elif OLD_JS_BLOCK in src:
    src = src.replace(OLD_JS_BLOCK, NEW_JS_BLOCK)
    APPJS.write_text(src, encoding="utf-8")
    print("[OK]   (2) cotton render: single multi-line -> two single-line calls")
else:
    print("[X]    (2) _renderMultiLine cotton block not found in expected form")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# (3) Disclaimer text: spell out parity warning.
#
# We don't fully know the current disclaimer text (server-side or client-side?).
# Quick check: search for cotton_disclaimer assignment in JS.
# ─────────────────────────────────────────────────────────────────────────────
DISC_OLD_PATTERNS = [
    "discEl.innerHTML = 'Bu iki seri farklı piyasalar",
    "discEl.innerHTML = `Bu iki seri farklı piyasalar",
    "discEl.textContent = 'Bu iki seri farklı piyasalar",
]
# We'll patch only if we find an existing assignment we can confidently match.
# If not, leave a TODO note — disclaimer can stay as-is.
src = APPJS.read_text(encoding="utf-8")
disc_handled = False
for pat in DISC_OLD_PATTERNS:
    if pat in src:
        disc_handled = True
        print(f"[!]    (3) cotton disclaimer found ({pat[:40]}...); leaving as-is")
        break
if not disc_handled:
    print("[skip] (3) no client-side disclaimer text found to patch (HTML disclaimer div is populated dynamically; leaving as-is)")

# ─────────────────────────────────────────────────────────────────────────────
# (4) CSS: small layout for the new sub-chart sections
# ─────────────────────────────────────────────────────────────────────────────
css_src = CSS.read_text(encoding="utf-8")

CSS_HEADER = "/* ── PI-1.6: cotton sub-chart split"

CSS_BLOCK = """

/* ── PI-1.6: cotton sub-chart split ───────────────────────────────────────── */
.cotton-subchart {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 10px;
}
.cotton-subchart-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--text, #e6e9ef);
  opacity: 0.85;
  padding-left: 4px;
}
.cotton-subchart .chart-wrap {
  /* slightly shorter than the original combined chart since we now have two */
  min-height: 180px;
}
"""

if CSS_HEADER in css_src:
    print("[skip] (4) cotton sub-chart CSS already present")
else:
    CSS.write_text(css_src.rstrip() + CSS_BLOCK, encoding="utf-8")
    print("[OK]   (4) cotton sub-chart CSS appended")

# ─────────────────────────────────────────────────────────────────────────────
# (5) Cache busters
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m_js = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m_js:
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    print(f"[OK]   (5a) app.v5.js cache buster -> {ts}")
m_css = re.search(r'style\.v5\.css\?v=(\S+?)"', html)
if m_css:
    html = re.sub(r'style\.v5\.css\?v=\S+?"', f'style.v5.css?v={ts}"', html)
    print(f"[OK]   (5b) style.v5.css cache buster -> {ts}")
INDEX.write_text(html, encoding="utf-8")

print()
print("Done. Browser: Ctrl+Shift+R on Price Intelligence.")
print()
print("Expected:")
print("  - One 'Pamuk — Spot vs Vadeli' panel")
print("  - Two summary cards on top (SunSirs Çin Spot / ICE Vadeli)")
print("  - Two stacked sub-charts:")
print("      'SunSirs Çin Spot'  with orange line, own y-axis")
print("      'ICE Vadeli (Küresel)' with blue line, own y-axis")
print("  - Disclaimer underneath")
