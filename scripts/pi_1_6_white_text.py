"""
pi_1_6_white_text.py - Cotton panel: white labels and summary text.

Three label sets need to be white:
  - .cotton-series-label   (top summary row: 'SunSirs Çin Spot' / 'ICE Vadeli (Küresel)')
  - .cotton-subchart-label (sub-chart headers: 'SUNSIRS ÇİN SPOT' / 'ICE VADELİ (KÜRESEL)')
  - .cotton-disclaimer     (bottom warning line)

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

HEADER = "/* ── PI-1.6: cotton labels white"

NEW_BLOCK = """

/* ── PI-1.6: cotton labels white ──────────────────────────────────────────── */
.cotton-series-label {
  color: var(--text, #e6e9ef);
  opacity: 1;
}
.cotton-subchart-label {
  color: var(--text, #e6e9ef);
  opacity: 1;
}
.cotton-disclaimer {
  color: var(--text, #e6e9ef);
  opacity: 0.85;
}
"""

if HEADER in css_src:
    print("[skip] cotton white-text override already present")
else:
    CSS.write_text(css_src.rstrip() + NEW_BLOCK, encoding="utf-8")
    print("[OK]  cotton labels and disclaimer set to white")

html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m_css = re.search(r'style\.v5\.css\?v=(\S+?)"', html)
if m_css:
    html = re.sub(r'style\.v5\.css\?v=\S+?"', f'style.v5.css?v={ts}"', html)
    INDEX.write_text(html, encoding="utf-8")
    print(f"[OK]  style.v5.css cache buster -> {ts}")

print()
print("Done. Browser: Ctrl+Shift+R.")
