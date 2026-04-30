"""
pi_1_5b_white_text.py - Make node names and FDY reference label fully white.

Two small CSS overrides:

  1. FDY reference label was set to opacity 0.7 to feel "secondary".
     User feedback: still looks too dim. Drop the opacity, label is white
     like the others. Secondary feel is still preserved by the muted
     border/background and the body opacity on the FDY card itself.

  2. The node name labels (PTA, PSF, POY, DTY, FDY) currently inherit a
     muted color from the chain-node-name rule. User wants them white.

CSS-only. Idempotent.
"""
from pathlib import Path
import re
import sys
import time

REPO  = Path(__file__).resolve().parent.parent
CSS   = REPO / "dashboard" / "static" / "style.v5.css"
INDEX = REPO / "dashboard" / "static" / "index.html"

css_src = CSS.read_text(encoding="utf-8")

HEADER = "/* ── PI-1.5b: full white text on labels and node names"

NEW_BLOCK = """

/* ── PI-1.5b: full white text on labels and node names ────────────────────── */
.chain-group-parallel .chain-group-label {
  /* override the earlier opacity:0.7 — user wants it just white */
  opacity: 1;
}
.chain-node-name {
  color: var(--text, #e6e9ef);
  opacity: 1;
}
"""

if HEADER in css_src:
    print("[skip] white-text override already present")
else:
    CSS.write_text(css_src.rstrip() + NEW_BLOCK, encoding="utf-8")
    print("[OK]  FDY ref label and chain-node-name set to white")

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
