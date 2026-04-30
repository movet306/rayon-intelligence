"""
pi_1_6b_cleanup.py - Mop up remaining Turkish strings missed by the
first language-normalize pass.

Targets (from the leftover scan):

  index.html:
    'Fiyat' button label                      -> 'Price'
    'ICE Vadeli (Küresel)' subchart label    -> 'ICE Futures (Global)'
    'Tüm Materyaller — Özet'                  -> 'All Materials — Summary'
    table header '7G%'                        -> '7D%'

  app.v5.js:
    loading message 'Fiyat verisi yükleniyor…' -> 'Loading price data…'
    cotton series card 'SunSirs Çin Spot'      -> 'SunSirs China Spot'
    cotton series card 'ICE Vadeli (Küresel)'  -> 'ICE Futures (Global)'
    cotton chart legend 'SunSirs Çin Spot (USD/t)' -> 'SunSirs China Spot (USD/t)'
    cotton chart legend 'ICE Vadeli (USD/t)'   -> 'ICE Futures (USD/t)'
    summary table headers:
        'Materyal'              -> 'Material'
        'Fiyat (USD/t / RMB/t)' -> 'Price (USD/t / RMB/t)'
        '1G%' / '7G%' / '30G%'  -> '1D%' / '7D%' / '30D%'

  'TR Lag' kept as-is (already English-style).
  Internal Data section (Operations / Procurement / Customer concentration)
  was already English in the leftover scan; not touched.

Idempotent.
"""
from pathlib import Path
import re
import sys
import time

REPO  = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"


def replace_once(text, old, new, label):
    if new in text and old not in text:
        print(f"[skip] {label}: already translated")
        return text
    if old not in text:
        print(f"[!]    {label}: source string not found")
        return text
    text = text.replace(old, new, 1)
    print(f"[OK]   {label}")
    return text


# ─────────────────────────────────────────────────────────────────────────────
# (1) HTML
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")

html = replace_once(
    html,
    '<button class="toggle-btn active" data-mode="price">Fiyat</button>',
    '<button class="toggle-btn active" data-mode="price">Price</button>',
    "(1.1) HTML 'Fiyat' button",
)

html = replace_once(
    html,
    '<div class="cotton-subchart-label">ICE Vadeli (K&#252;resel)</div>',
    '<div class="cotton-subchart-label">ICE Futures (Global)</div>',
    "(1.2) HTML cotton subchart label 'ICE Vadeli (Küresel)'",
)
# also try literal-character form just in case
html = replace_once(
    html,
    '<div class="cotton-subchart-label">ICE Vadeli (Küresel)</div>',
    '<div class="cotton-subchart-label">ICE Futures (Global)</div>',
    "(1.2alt) HTML cotton subchart label literal",
)

html = replace_once(
    html,
    'Tüm Materyaller — Özet',
    'All Materials — Summary',
    "(1.3) HTML 'Tüm Materyaller — Özet'",
)

html = replace_once(
    html,
    '<th class="num">7G%</th>',
    '<th class="num">7D%</th>',
    "(1.4) HTML table header '7G%'",
)

INDEX.write_text(html, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# (2) JS
# ─────────────────────────────────────────────────────────────────────────────
src = APPJS.read_text(encoding="utf-8")

src = replace_once(
    src,
    "'<div class=\"loading\">Fiyat verisi yükleniyor…</div>'",
    "'<div class=\"loading\">Loading price data…</div>'",
    "(2.1) loading message",
)

src = replace_once(
    src,
    '<div class="cotton-series-label">SunSirs Çin Spot</div>',
    '<div class="cotton-series-label">SunSirs China Spot</div>',
    "(2.2) cotton series card 'SunSirs Çin Spot'",
)
src = replace_once(
    src,
    '<div class="cotton-series-label">ICE Vadeli (Küresel)</div>',
    '<div class="cotton-series-label">ICE Futures (Global)</div>',
    "(2.3) cotton series card 'ICE Vadeli (Küresel)'",
)

src = replace_once(
    src,
    "{ key: 'cotton_lint', color: C.orange, label: 'SunSirs Çin Spot (USD/t)' },",
    "{ key: 'cotton_lint', color: C.orange, label: 'SunSirs China Spot (USD/t)' },",
    "(2.4) cotton chart legend 'SunSirs Çin Spot'",
)
src = replace_once(
    src,
    "{ key: 'cotton_lint_futures', color: C.blue, label: 'ICE Vadeli (USD/t)' },",
    "{ key: 'cotton_lint_futures', color: C.blue, label: 'ICE Futures (USD/t)' },",
    "(2.5) cotton chart legend 'ICE Vadeli'",
)

# Summary table headers
src = replace_once(
    src,
    "<th>Materyal</th>",
    "<th>Material</th>",
    "(2.6) summary table 'Materyal'",
)
src = replace_once(
    src,
    "<th class=\"num\">Fiyat (${_currency === 'usd' ? 'USD/t' : 'RMB/t'})</th>",
    "<th class=\"num\">Price (${_currency === 'usd' ? 'USD/t' : 'RMB/t'})</th>",
    "(2.7) summary table 'Fiyat'",
)
src = replace_once(
    src,
    '<th class="num">1G%</th>',
    '<th class="num">1D%</th>',
    "(2.8) summary table '1G%'",
)
src = replace_once(
    src,
    '<th class="num">7G%</th>',
    '<th class="num">7D%</th>',
    "(2.9) summary table '7G%'",
)
src = replace_once(
    src,
    '<th class="num">30G%</th>',
    '<th class="num">30D%</th>',
    "(2.10) summary table '30G%'",
)

APPJS.write_text(src, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# (3) Cache busters
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m_js = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m_js:
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    print(f"[OK]   (3a) app.v5.js cache buster -> {ts}")
m_css = re.search(r'style\.v5\.css\?v=(\S+?)"', html)
if m_css:
    html = re.sub(r'style\.v5\.css\?v=\S+?"', f'style.v5.css?v={ts}"', html)
    print(f"[OK]   (3b) style.v5.css cache buster -> {ts}")
INDEX.write_text(html, encoding="utf-8")

print()
print("Done. Browser: Ctrl+Shift+R.")
