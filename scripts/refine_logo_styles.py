"""
refine_logo_styles.py - Refine sidebar logo alignment + tagline typography.

Follow-up to swap_logo.py. Fixes:
  - Logo image was centered (margin: 0 auto), tagline left-aligned -> mismatch.
    Both now left-aligned, consistent with nav items below.
  - Tagline 'Intelligence Platform' was visually competing with logo.
    Now: smaller, uppercase, muted, letter-spaced -> proper hierarchy.
  - Logo max-width 180 -> 150 (less heavy in narrow sidebar).

Idempotent via marker comment.
"""
from pathlib import Path
import re
import sys
import time

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "dashboard" / "static" / "index.html"
CSS = REPO / "dashboard" / "static" / "style.v5.css"

MARKER = "/* === Sidebar logo refinements (alignment + tagline) === */"
REFINEMENT = MARKER + """
.sidebar-logo .logo-mark-img {
  max-width: 150px;
  margin: 0 0 8px 0;
}
.sidebar-logo .logo-sub {
  font-size: 10px;
  font-weight: 500;
  color: var(--muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin: 0;
}
"""

# --- Step 1: append refinement block to CSS ---------------------------------
css = CSS.read_text(encoding="utf-8")

if MARKER in css:
    print("[skip] refinements already present in style.v5.css")
else:
    css = css.rstrip() + "\n\n" + REFINEMENT
    CSS.write_text(css, encoding="utf-8")
    print("[OK] style.v5.css: appended logo refinements")

# --- Step 2: bump cache buster ----------------------------------------------
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m = re.search(r'style\.v5\.css\?v=(\S+?)"', html)
if m:
    old_v = m.group(1)
    html = re.sub(r'style\.v5\.css\?v=\S+?"', f'style.v5.css?v={ts}"', html)
    INDEX.write_text(html, encoding="utf-8")
    print(f"[OK] Cache buster: style.v5.css?v={old_v} -> ?v={ts}")
else:
    print("[!]  No style.v5.css?v=... pattern found, skipping cache buster bump.")

print("\nDone. Next: Ctrl+Shift+R in browser, verify logo + tagline alignment.")
