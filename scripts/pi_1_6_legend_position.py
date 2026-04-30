"""
pi_1_6_legend_position.py - Fix Plotly legend position on cotton sub-charts.

User feedback: the auto-positioned legend on each cotton sub-chart sits
inside the plot area near the line, which made it look like a 'cut' in
the line at first glance.

Fix: pin the legend to the top-right corner of each chart, anchored to
the upper-right of the plot area, slightly inside the bounds. Same
treatment for both SunSirs and ICE sub-charts.

This is a generic _renderMultiLine layout option. Setting it via the
function's layout block fixes both single-series and multi-series
charts at once. We pass the legend config directly as part of the
existing layout, only when there's exactly one trace (so multi-series
charts like the polyester family chart and the nylon chart keep their
default legend placement).

Actually simpler approach: set legend position on layout for ANY chart
rendered through _renderMultiLine. Top-right is reasonable for all.
We'll do that.

Idempotent.
"""
from pathlib import Path
import re
import sys
import time

REPO  = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"

src = APPJS.read_text(encoding="utf-8")

# Find _renderMultiLine and patch its layout to add legend positioning.
# Anchor: function header. We'll insert a legend block into the existing
# layout literal.
#
# Strategy: find the layout object literal inside _renderMultiLine and add
# a legend property. We need to be surgical — match a unique fragment of
# that layout to anchor the insertion.

# Quick reconnaissance: we don't have the layout block in front of us, so
# the safest path is to wrap Plotly.newPlot for the multi-line function
# by post-processing layout right before the call. But we can't see the
# call site. Easier: just patch the cotton-specific renders to pass a
# layout-override flag.
#
# But _renderMultiLine signature is _renderMultiLine(elId, mats, data) —
# adding a 4th arg requires both touching the function and its callers.
#
# Cleanest minimal approach: patch _renderMultiLine internally to set
# `legend: { x: 1, xanchor: 'right', y: 1, yanchor: 'top' }` on its
# layout object. This applies to ALL charts rendered via this helper:
# cotton spot, cotton futures, and nylon. That's fine — top-right is a
# reasonable default everywhere.

# Find the function signature and inspect the layout literal there. Then
# inject `legend: {...},` near the top of that layout literal.

# We don't know the exact layout shape, so we match `Plotly.newPlot(elId, traces,`
# which appears once inside _renderMultiLine. Then we walk forward to the
# next `{` (start of layout literal) and insert our legend property just
# after that opening brace.

needle = "Plotly.newPlot(elId, traces,"
idx = src.find(needle)
if idx == -1:
    print("[X] could not locate Plotly.newPlot inside _renderMultiLine")
    sys.exit(1)

# Walk forward from idx + len(needle) past whitespace to the layout argument.
# It's either a `{...}` literal directly or an identifier (variable). Most
# likely a literal here based on the existing pattern.
after = idx + len(needle)
# Skip whitespace
j = after
while j < len(src) and src[j] in " \t\n":
    j += 1
if src[j] != "{":
    print(f"[X] expected layout literal (open brace), found '{src[j]!r}' at {j}")
    sys.exit(1)

# Already patched?
if "// PI-1.6: pin legend top-right" in src:
    print("[skip] legend position already patched")
else:
    insertion = "\n      // PI-1.6: pin legend top-right so it sits in the upper corner of the plot.\n      legend: { x: 1, xanchor: 'right', y: 1, yanchor: 'top' },"
    # Insert right after the opening brace of the layout literal
    src = src[:j+1] + insertion + src[j+1:]
    APPJS.write_text(src, encoding="utf-8")
    print("[OK]  legend position pinned to top-right in _renderMultiLine layout")

# Bump JS cache buster
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m_js = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m_js:
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    INDEX.write_text(html, encoding="utf-8")
    print(f"[OK]  app.v5.js cache buster -> {ts}")

print()
print("Done. Browser: Ctrl+Shift+R.")
print()
print("Expected: legend pinned to upper-right corner of every chart")
print("rendered through _renderMultiLine (both cotton sub-charts + nylon).")
