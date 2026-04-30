"""
pi_1_3_rename_all_signals.py - Rename 'Tüm Sinyaller' to 'All Signals'.

User feedback: 'Tüm Sinyaller' (Turkish) sat oddly between 'Action Now'
and 'Watch' (English). Switch to 'All Signals' for consistency.
"""
from pathlib import Path
import re
import sys
import time

REPO = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"

src = APPJS.read_text(encoding="utf-8")

OLD = "renderSection('Tüm Sinyaller', all, {"
NEW = "renderSection('All Signals', all, {"

if "renderSection('All Signals', all" in src:
    print("[skip] already renamed")
elif OLD in src:
    src = src.replace(OLD, NEW)
    APPJS.write_text(src, encoding="utf-8")
    print("[OK]  'Tüm Sinyaller' -> 'All Signals'")
else:
    print("[X]   expected line not found")
    sys.exit(1)

# Bump cache buster
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m:
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    INDEX.write_text(html, encoding="utf-8")
    print(f"[OK]  cache buster -> {ts}")

print("\nBrowser: Ctrl+Shift+R")
