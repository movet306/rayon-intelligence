"""
pi_1_7_nylon_align.py - X-axis common-start alignment in _renderMultiLine.

Problem:
  Nylon panel currently shows series with very different start dates (PA6
  chip and adipic acid have long history, polyamide_fdy started later).
  Plotly auto-fits x-axis, which made the panel feel like it covered a
  much shorter window than the polyester chart above it. The visual
  language was inconsistent across the section.

Decision (recap):
  - Date range strategy = A: common-start window. Use the latest first-date
    across the series being rendered, end at the latest end-date.
  - Adipic annotation = B: not adding any signal annotation in this phase.

Implementation:
  Same approach used in PI-1.5 for the polyester chart: just before
  Plotly.newPlot, compute the common range from the assembled traces and
  override layout.xaxis.range. Doing this inside _renderMultiLine fixes
  ALL three current callers in one place:
      chart-nylon          (4 series)
      chart-cotton-spot    (1 series, no-op since single trace)
      chart-cotton-futures (1 series, no-op since single trace)

Single-trace charts are unaffected: a 'common start' across one series
is just that series' own first date, which Plotly already auto-fits to.

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

MARKER = "// PI-1.7: align x-axis to common-start"
if MARKER in src:
    print("[skip] PI-1.7 alignment already present in _renderMultiLine")
    sys.exit(0)

# Find the Plotly.newPlot call inside _renderMultiLine. We located it
# earlier:  Plotly.newPlot(elId, traces, ... )
needle = "Plotly.newPlot(elId, traces,"
idx = src.find(needle)
if idx == -1:
    print("[X] could not locate Plotly.newPlot inside _renderMultiLine")
    sys.exit(1)

# Walk forward past whitespace to the layout argument; expect '{' (literal).
j = idx + len(needle)
while j < len(src) and src[j] in " \t\n":
    j += 1
if src[j] != "{":
    print(f"[X] expected '{{' for layout literal, got {src[j]!r}")
    sys.exit(1)

# Insert the alignment block AT THE TOP of the layout literal, right after '{'.
# We add an immediately-invoked helper that mutates the layout's xaxis.range
# in-place. Using IIFE here keeps the existing function shape unchanged.
INSERT = """
      // PI-1.7: align x-axis to common-start across visible series.
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

# Place insertion immediately after the layout literal's opening brace.
src = src[:j+1] + INSERT + src[j+1:]
APPJS.write_text(src, encoding="utf-8")
print("[OK] _renderMultiLine layout: x-axis common-start spread injected")
print("     affects: chart-nylon (4 series), cotton-spot (1), cotton-futures (1)")

# Bump JS cache buster
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m:
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    INDEX.write_text(html, encoding="utf-8")
    print(f"[OK] app.v5.js cache buster -> {ts}")

print()
print("Done. Browser: Ctrl+Shift+R.")
print()
print("Expected:")
print("  - Nylon chart: x-axis no longer dominated by long-history series.")
print("    All 4 lines start from the same date (latest first-date among them).")
print("  - Cotton spot / futures: unchanged (single-trace).")
