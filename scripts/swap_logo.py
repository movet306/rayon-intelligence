"""
swap_logo.py - Replace hexagon emoji mark with branded Rayon logo image.

Pre-req: dashboard/static/rayon-logo.png must exist (copy rayon-logo-light.png there).

Changes:
  - index.html: <div class="logo-mark">u+2B21 Rayon</div>  ->  <img class="logo-mark-img" src="rayon-logo.png">
  - style.v5.css: append .logo-mark-img rules
  - index.html: bump style.v5.css cache buster to current unix timestamp

Idempotent: re-running after success prints '[skip] already patched' for each step.
"""
from pathlib import Path
import re
import sys
import time

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "dashboard" / "static" / "index.html"
CSS = REPO / "dashboard" / "static" / "style.v5.css"
LOGO = REPO / "dashboard" / "static" / "rayon-logo.png"

OLD_LINE = '    <div class="logo-mark">\u2B21 Rayon</div>'
NEW_LINE = '    <img class="logo-mark-img" src="rayon-logo.png" alt="Rayon">'

CSS_BLOCK = """
/* === Sidebar branded logo (replaces hexagon mark) === */
.sidebar-logo .logo-mark-img {
  display: block;
  width: 100%;
  max-width: 180px;
  height: auto;
  margin: 0 auto 6px auto;
}
"""

# --- Step 1: verify logo file exists ----------------------------------------
if not LOGO.exists():
    print(f"[X] Logo file missing: {LOGO}")
    print(f"    -> Copy rayon-logo-light.png there as rayon-logo.png and re-run.")
    sys.exit(1)
print(f"[OK] Logo file present: {LOGO.name} ({LOGO.stat().st_size:,} bytes)")

# --- Step 2: patch index.html (logo-mark -> img) ----------------------------
html = INDEX.read_text(encoding="utf-8")

if 'class="logo-mark-img"' in html:
    print("[skip] index.html already has logo-mark-img")
elif OLD_LINE in html:
    html = html.replace(OLD_LINE, NEW_LINE)
    print("[OK] index.html: replaced .logo-mark with <img>")
else:
    print("[X] Could not find expected line in index.html:")
    print(f"    Expected: {OLD_LINE!r}")
    print("    Inspect index.html line 16 manually.")
    sys.exit(1)

# --- Step 3: bump cache buster ----------------------------------------------
ts = int(time.time())
m = re.search(r'style\.v5\.css\?v=(\S+?)"', html)
if m:
    old_v = m.group(1)
    html = re.sub(r'style\.v5\.css\?v=\S+?"', f'style.v5.css?v={ts}"', html)
    print(f"[OK] Cache buster: style.v5.css?v={old_v} -> ?v={ts}")
else:
    print("[!]  No style.v5.css?v=... pattern found, skipping cache buster bump.")

INDEX.write_text(html, encoding="utf-8")

# --- Step 4: append CSS rules -----------------------------------------------
css = CSS.read_text(encoding="utf-8")

if '.logo-mark-img' in css:
    print("[skip] style.v5.css already has .logo-mark-img rules")
else:
    css = css.rstrip() + "\n" + CSS_BLOCK
    CSS.write_text(css, encoding="utf-8")
    print("[OK] style.v5.css: appended .logo-mark-img rules")

print("\nDone. Next: Ctrl+Shift+R in browser, verify sidebar logo.")
