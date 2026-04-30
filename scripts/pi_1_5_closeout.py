"""
pi_1_5_closeout.py - Final visual polish to close PI-1.5.

Two small UX fixes:

  1. PTA color: was C.purple, conflicted visually with DTY ('#a371f7' lila).
     Move PTA to teal/cyan family — clearly distinct from DTY's purple,
     stays distinct from PSF (blue) and POY (green).
     Chosen: '#22c1c3' (teal), well separated on the color wheel.

  2. Rangeslider strip at the bottom of the polyester chart looked cluttered
     with no clear value at this density. Hide it via Plotly layout.

Idempotent.
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
# Change 1: PTA color teal
# ─────────────────────────────────────────────────────────────────────────────
OLD_PTA_LINE = "  { key: 'pta',                    color: C.purple,   label: 'PTA' },"
NEW_PTA_LINE = "  { key: 'pta',                    color: '#22c1c3',  label: 'PTA' },  // PI-1.5 closeout: teal, distinct from DTY purple"

if "PI-1.5 closeout: teal" in src:
    print("[skip] (1) PTA color already updated to teal")
elif OLD_PTA_LINE in src:
    src = src.replace(OLD_PTA_LINE, NEW_PTA_LINE)
    print("[OK]   (1) PTA color: C.purple -> #22c1c3 (teal)")
else:
    print("[X]    (1) Expected PTA line not found")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Change 2: hide rangeslider on polyester chart
#
# We patch the same spot we patched in pi_1_5_polyester_chart.py (just before
# the Plotly.newPlot call) by also disabling rangeslider in layout.xaxis.
# ─────────────────────────────────────────────────────────────────────────────
OLD_RANGE_BLOCK = """    layout.xaxis = { ...(layout.xaxis || {}), range: [_commonStart, _commonEnd] };
  }
  Plotly.newPlot('chart-polyester', traces, layout, PLOTLY_CONFIG);"""

NEW_RANGE_BLOCK = """    layout.xaxis = {
      ...(layout.xaxis || {}),
      range: [_commonStart, _commonEnd],
      // PI-1.5 closeout: hide rangeslider strip (low value at this density).
      rangeslider: { visible: false },
    };
  }
  Plotly.newPlot('chart-polyester', traces, layout, PLOTLY_CONFIG);"""

if "PI-1.5 closeout: hide rangeslider" in src:
    print("[skip] (2) rangeslider already hidden")
elif OLD_RANGE_BLOCK in src:
    src = src.replace(OLD_RANGE_BLOCK, NEW_RANGE_BLOCK)
    print("[OK]   (2) rangeslider hidden in chart layout")
else:
    print("[X]    (2) x-axis range block (from pi_1_5_polyester_chart.py) not found")
    print("       This patch must run AFTER pi_1_5_polyester_chart.py.")
    sys.exit(1)

APPJS.write_text(src, encoding="utf-8")

# Bump cache buster
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m:
    old_v = m.group(1)
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    INDEX.write_text(html, encoding="utf-8")
    print(f"[OK]   index.html: cache buster {old_v} -> {ts}")

print()
print("Done. Browser: Ctrl+Shift+R on Price Intelligence.")
print("Verify:")
print("  - PTA line is teal (clearly distinct from DTY purple)")
print("  - No rangeslider strip at the bottom of the polyester chart")
