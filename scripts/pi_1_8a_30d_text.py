"""
pi_1_8a_30d_text.py - Replace empty 30D% dash with explicit text.

User feedback: showing '—' in empty 30D% cells (with hover tooltip) wasn't
self-explanatory at a glance. Better to surface the reason directly.

Change: in fmt30 helper inside _renderPriceSummaryTable, when value is null,
render '<30 days history' (with the angle bracket properly escaped) instead
of '—'. The tooltip stays attached for redundancy.

Idempotent.
"""
from pathlib import Path
import re
import io
import time

REPO  = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"

src = APPJS.read_text(encoding="utf-8")

OLD = '''  const fmt30 = v => {
    if (v == null) {
      return '<span class="muted" title="Insufficient history \\u2014 30D requires at least 30 days of data">\\u2014</span>';
    }
    const cls = v > 0 ? 'stat-up' : v < 0 ? 'stat-down' : 'stat-neutral';
    return `<span class="${cls}">${v > 0 ? '+' : ''}${v.toFixed(1)}%</span>`;
  };'''

NEW = '''  const fmt30 = v => {
    if (v == null) {
      // PI-1.8a tweak: explicit "<30 days history" instead of dash so the
      // missing-data reason is visible without hovering.
      return '<span class="muted muted-tag" title="30D requires at least 30 days of data">&lt;30 days history</span>';
    }
    const cls = v > 0 ? 'stat-up' : v < 0 ? 'stat-down' : 'stat-neutral';
    return `<span class="${cls}">${v > 0 ? '+' : ''}${v.toFixed(1)}%</span>`;
  };'''

if "&lt;30 days history" in src:
    print("[skip] 30D% explicit text already applied")
elif OLD in src:
    src = src.replace(OLD, NEW, 1)
    APPJS.write_text(src, encoding="utf-8")
    print("[OK] 30D% empty cells now read '<30 days history'")
else:
    print("[X] could not find fmt30 block to patch")
    print("    (likely the file was edited differently — check the function)")
    raise SystemExit(1)

# Cache buster
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
html = re.sub(r'app\.v5\.js\?v=\d+', f'app.v5.js?v={ts}', html)
html = re.sub(r'style\.v5\.css\?v=\d+', f'style.v5.css?v={ts}', html)
with io.open(INDEX, "w", encoding="utf-8", newline="") as f:
    f.write(html)
print(f"[OK] cache buster -> {ts}")

print()
print("Done. Browser: Ctrl+Shift+R.")
