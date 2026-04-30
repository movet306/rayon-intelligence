"""
pi_1_5b_label_color.py - Make all chain group labels white for readability.

The previous polish pass left labels (STAPLE / FILAMENT / FDY REFERENCE)
in muted gray which doesn't read well against the dark panel background.
Switch to white. FDY reference still reads as secondary because of the
muted border, lighter background, and reduced body opacity — we don't
need the label color too.

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

HEADER = "/* ── PI-1.5b: chain group labels white for readability"

NEW_BLOCK = """

/* ── PI-1.5b: chain group labels white for readability ───────────────────── */
.chain-group-label {
  color: var(--text, #e6e9ef);
}
.chain-group-parallel .chain-group-label {
  color: var(--text, #e6e9ef);
  opacity: 0.7;  /* still slightly de-emphasized vs. main branches */
}
"""

if HEADER in css_src:
    print("[skip] label color override already present")
else:
    CSS.write_text(css_src.rstrip() + NEW_BLOCK, encoding="utf-8")
    print("[OK]  chain-group labels set to white (FDY ref slightly muted via opacity)")

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
