"""
pi_1_5b_polish.py - Three small visual refinements after PI-1.5b v2 landed.

Polish only — topology and layout are unchanged.

  1. PTA card: was full-width, dominating the row. Narrow to ~60% and
     center it. Still reads as "single upstream source" but no longer
     visually outweighs everything else.

  2. FDY reference group: visually de-emphasize so it doesn't read as a
     third main branch equal to Staple/Filament. Lower-contrast label,
     slightly muted card border, body opacity ~0.85.

  3. Filament group's POY -> DTY arrow: bumped from the muted gray
     it inherited to a clearer color, slightly larger, more weight.

CSS-only patch. Idempotent.
"""
from pathlib import Path
import re
import sys
import time

REPO  = Path(__file__).resolve().parent.parent
CSS   = REPO / "dashboard" / "static" / "style.v5.css"
INDEX = REPO / "dashboard" / "static" / "index.html"

css_src = CSS.read_text(encoding="utf-8")

POLISH_HEADER = "/* ── PI-1.5b polish: PTA narrow, FDY muted, arrow stronger"

POLISH_CSS = """

/* ── PI-1.5b polish: PTA narrow, FDY muted, arrow stronger ────────────────── */

/* (1) PTA card narrowed and centered. Still a single full-width container
       so the layout grid stays the same, but the inner card is constrained. */
.chain-grouped-root {
  justify-content: center;
}
.chain-grouped-root .chain-node {
  flex: 0 1 60%;
  max-width: 60%;
}

/* (2) FDY reference group de-emphasized. Lower-contrast label, slightly
       muted border, slightly reduced body opacity so it reads as secondary. */
.chain-group-parallel {
  border-color: rgba(255, 255, 255, 0.025);
  background: rgba(255, 255, 255, 0.012);
}
.chain-group-parallel .chain-group-label {
  opacity: 0.65;
  font-size: 9px;
}
.chain-group-parallel .chain-node {
  opacity: 0.88;
}

/* (3) POY -> DTY arrow inside the Filament group: more visible. */
.chain-group-filament .chain-group-arrow {
  font-size: 18px;
  font-weight: 600;
  color: var(--text, #e6e9ef);
  opacity: 0.7;
  padding: 0 2px;
}
"""

if POLISH_HEADER in css_src:
    print("[skip] polish CSS already present")
else:
    CSS.write_text(css_src.rstrip() + POLISH_CSS, encoding="utf-8")
    print("[OK]  polish CSS appended (PTA narrow + FDY muted + arrow stronger)")

# Bump CSS cache buster
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m_css = re.search(r'style\.v5\.css\?v=(\S+?)"', html)
if m_css:
    html = re.sub(r'style\.v5\.css\?v=\S+?"', f'style.v5.css?v={ts}"', html)
    INDEX.write_text(html, encoding="utf-8")
    print(f"[OK]  style.v5.css cache buster -> {ts}")

print()
print("Done. Browser: Ctrl+Shift+R.")
print()
print("Expected:")
print("  - PTA card narrower (~60%), centered.")
print("  - FDY reference group looks subtler than Staple/Filament.")
print("  - POY -> DTY arrow more prominent in the Filament group.")
