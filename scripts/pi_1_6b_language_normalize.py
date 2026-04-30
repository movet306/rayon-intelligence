"""
pi_1_6b_language_normalize.py - Normalize UI strings to English.

After PI-1.3 (English section labels) and PI-1.5b (English chain header),
the page is mixed-language: navigation/structure in English, but content
labels, buttons, and badges still in Turkish. This unifies the UI.

Scope (B): UI strings only. Signal card content (explanation,
business_implication) is generated server-side by build_price_signals.py
and remains Turkish for now. A separate phase PI-1.6c will translate the
generator. While the generator stays TR, freshly produced cards will be
TR; this is acknowledged and accepted.

Files touched:
  - dashboard/static/index.html
      Section title 'Emtia Fiyat İstihbaratı' -> 'Commodity Price Intelligence'
      'Pamuk — Spot vs Vadeli'   -> 'Cotton — Spot vs Futures'
      'Naylon Ailesi & Adipik Asit' -> 'Nylon Family & Adipic Acid'

  - dashboard/static/app.v5.js
      MATERIAL_LABELS: Turkish names -> English
      TYPE_LABEL (signal types): all 8 entries
      SEV_LABEL (severity): KRİTİK/YÜKSEK/ORTA/DÜŞÜK -> CRITICAL/HIGH/MEDIUM/LOW
      Empty-state messages, lag badges, insufficient-data tooltips
      _renderPolyLagRow header
      Cotton chart series labels (already partially done in PI-1.6;
        finalize legend strings here)

CSS-only renames not needed.

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
    """Helper: replace `old` with `new` if present, else flag missing."""
    if new in text and old not in text:
        print(f"[skip] {label}: already translated")
        return text, "skip"
    if old not in text:
        print(f"[!]    {label}: source string not found")
        return text, "miss"
    text = text.replace(old, new, 1)
    print(f"[OK]   {label}")
    return text, "ok"


# ─────────────────────────────────────────────────────────────────────────────
# (1) HTML strings
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")

html, _ = replace_once(
    html,
    'Emtia Fiyat İstihbaratı',
    'Commodity Price Intelligence',
    "(1.1) HTML section title",
)
html, _ = replace_once(
    html,
    'Pamuk &#8212; Spot vs Vadeli',
    'Cotton &#8212; Spot vs Futures',
    "(1.2) HTML cotton panel title",
)
# Try alternate encoding too if first didn't match
if 'Cotton &#8212; Spot vs Futures' not in html:
    html, _ = replace_once(
        html,
        'Pamuk — Spot vs Vadeli',
        'Cotton — Spot vs Futures',
        "(1.2alt) HTML cotton panel title literal",
    )

html, _ = replace_once(
    html,
    'Naylon Ailesi &amp; Adipik Asit',
    'Nylon Family &amp; Adipic Acid',
    "(1.3) HTML nylon panel title",
)

INDEX.write_text(html, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# (2) JS strings
# ─────────────────────────────────────────────────────────────────────────────
src = APPJS.read_text(encoding="utf-8")

# 2.1 — MATERIAL_LABELS
material_replacements = [
    ("'Polyester İplik'",          "'Polyester Yarn'",            "(2.1a) polyester_yarn label"),
    ("'Pamuk (SunSirs Çin)'",      "'Cotton (SunSirs China)'",    "(2.1b) cotton_lint label"),
    ("'Pamuk (ICE Vadeli)'",       "'Cotton (ICE Futures)'",      "(2.1c) cotton_lint_futures label"),
    ("'Pamuk İpliği'",             "'Cotton Yarn'",               "(2.1d) cotton_yarn label"),
    ("'Naylon FDY (PA6)'",         "'Nylon FDY (PA6)'",           "(2.1e) polyamide_fdy label"),
    ("'Adipik Asit'",              "'Adipic Acid'",               "(2.1f) adipic_acid label"),
]
for old, new, lbl in material_replacements:
    src, _ = replace_once(src, old, new, lbl)

# 2.2 — TYPE_LABEL (signal types)
type_replacements = [
    ("'Maliyet Artışı'",     "'Cost Pressure Up'",     "(2.2a) COST_PRESSURE_UP"),
    ("'Maliyet Düşüşü'",     "'Cost Pressure Down'",   "(2.2b) COST_PRESSURE_DOWN"),
    ("'Zincir Uyumsuzluğu'", "'Chain Divergence'",     "(2.2c) UPSTREAM_DOWNSTREAM_DIVG"),
    ("'Spread Genişleme'",   "'Spread Widening'",      "(2.2d) SPREAD_WIDENING"),
    ("'Spread Daralma'",     "'Spread Tightening'",    "(2.2e) SPREAD_TIGHTENING"),
    ("'Volatilite'",         "'Volatility'",           "(2.2f) VOLATILITY_SPIKE"),
    ("'Gecikmiş Yansıma'",   "'Delayed Pass-Through'", "(2.2g) DELAYED_PASS_THROUGH_RISK"),
    ("'Veri Uyarısı'",       "'Data Quality'",         "(2.2h) DATA_QUALITY_WARNING"),
]
for old, new, lbl in type_replacements:
    src, _ = replace_once(src, old, new, lbl)

# 2.3 — SEV_LABEL (severity)
sev_old = "{ critical: 'KRİTİK', high: 'YÜKSEK', medium: 'ORTA', low: 'DÜŞÜK' }"
sev_new = "{ critical: 'CRITICAL', high: 'HIGH', medium: 'MEDIUM', low: 'LOW' }"
src, _ = replace_once(src, sev_old, sev_new, "(2.3) SEV_LABEL severities")

# 2.4 — Empty-state and lag-row strings (PI-1.3 introduced these)
src, _ = replace_once(
    src,
    "'<div class=\"no-signals-muted\">Aktif fiyat sinyali yok — piyasalar sakin</div>'",
    "'<div class=\"no-signals-muted\">No active price signals — markets calm</div>'",
    "(2.4a) no-signals message",
)
src, _ = replace_once(
    src,
    "emptyMsg: 'Şu an aksiyon gerektiren kritik / yüksek sinyal yok.',",
    "emptyMsg: 'No critical / high-severity signals require action right now.',",
    "(2.4b) action-empty message",
)
src, _ = replace_once(
    src,
    "emptyMsg: 'Orta seviye izleme sinyali yok.',",
    "emptyMsg: 'No medium-severity signals to watch right now.',",
    "(2.4c) watch-empty message",
)

# 2.5 — Turkey lag prefix in signal cards
src, _ = replace_once(
    src,
    '`<div class="ew-lag">&#8594; Türkiye tahmini: ${s.turkey_lag_min}–${s.turkey_lag_max} hafta</div>`',
    '`<div class="ew-lag">&#8594; Turkey lag est.: ${s.turkey_lag_min}–${s.turkey_lag_max} weeks</div>`',
    "(2.5) signal card Turkey lag prefix",
)

# 2.6 — _renderPolyLagRow header label
src, _ = replace_once(
    src,
    'el.innerHTML = `<span class="lag-row-label">&#127481;&#127479; Türkiye yansıma:</span> ${items.join(\'\')}`;',
    'el.innerHTML = `<span class="lag-row-label">&#127481;&#127479; Turkey lag:</span> ${items.join(\'\')}`;',
    "(2.6) _renderPolyLagRow header",
)

# 2.7 — turkey-lag-badge unit "hf" -> "wk" (3 occurrences)
# These are in different places: _renderPolyLagRow, polyMetricCards, and yarn-related
lag_badge_old = '<span class="turkey-lag-badge">${lagMin}–${lagMax} hf</span>'
lag_badge_new = '<span class="turkey-lag-badge">${lagMin}–${lagMax} wk</span>'
count = src.count(lag_badge_old)
if count > 0:
    src = src.replace(lag_badge_old, lag_badge_new)
    print(f"[OK]   (2.7a) turkey-lag-badge unit 'hf' -> 'wk' ({count} occurrence{'s' if count != 1 else ''})")
elif lag_badge_new in src:
    print("[skip] (2.7a) turkey-lag-badge already 'wk'")
else:
    print("[!]    (2.7a) turkey-lag-badge with 'hf' not found")

# Variant with `${a}\u2013${b} hf` (used in line 1221)
lag_badge_old_var = '<span class="turkey-lag-badge">${a}\\u2013${b} hf</span>'
lag_badge_new_var = '<span class="turkey-lag-badge">${a}\\u2013${b} wk</span>'
if lag_badge_old_var in src:
    src = src.replace(lag_badge_old_var, lag_badge_new_var)
    print("[OK]   (2.7b) turkey-lag-badge variant (yarn) -> 'wk'")
elif lag_badge_new_var in src:
    print("[skip] (2.7b) turkey-lag-badge yarn variant already 'wk'")

# 2.8 — "yetersiz veri" -> "insufficient data" (3 occurrences)
yv_replacements = [
    ("`${m.label} (yetersiz veri)`",
     "`${m.label} (insufficient data)`",
     "(2.8a) chart name 'yetersiz veri'"),
    ('`${m.label}: %{y:${hoverFmt}} (yetersiz veri)<extra></extra>`',
     '`${m.label}: %{y:${hoverFmt}} (insufficient data)<extra></extra>`',
     "(2.8b) hover template 'yetersiz veri'"),
    ('title="Yetersiz veri — 7\'den az veri noktası"',
     'title="Insufficient data — fewer than 7 data points"',
     "(2.8c) tooltip 'yetersiz veri'"),
]
for old, new, lbl in yv_replacements:
    src, _ = replace_once(src, old, new, lbl)

# 2.9 — Nylon chart series labels
src, _ = replace_once(
    src,
    "{ key: 'polyamide_fdy', color: C.purple, label: 'Naylon FDY' },",
    "{ key: 'polyamide_fdy', color: C.purple, label: 'Nylon FDY' },",
    "(2.9a) nylon chart series 'Naylon FDY'",
)
src, _ = replace_once(
    src,
    "{ key: 'adipic_acid',   color: '#56d364',label: 'Adipik Asit (öncü)' },",
    "{ key: 'adipic_acid',   color: '#56d364',label: 'Adipic Acid (leading)' },",
    "(2.9b) nylon chart series 'Adipik Asit (öncü)'",
)

# 2.10 — Sub-spec tooltip (yarn intelligence)
src, _ = replace_once(
    src,
    'title="Alt-spec varyantlar mevcut \\u2014 fiyat farki olabilir"',
    'title="Sub-spec variants present \\u2014 price may vary"',
    "(2.10) sub-spec tooltip",
)

# 2.11 — Cotton disclaimer text (was set as discEl.textContent)
# The current text is: 'Bu iki seri farklı piyasalardır — doğrudan karşılaştırılmamalıdır.'
disclaimer_replacements = [
    ("'Bu iki seri farklı piyasalardır — doğrudan karşılaştırılmamalıdır.'",
     "'Different markets — not directly comparable.'",
     "(2.11a) cotton disclaimer single-quote form"),
    ('"Bu iki seri farklı piyasalardır — doğrudan karşılaştırılmamalıdır."',
     '"Different markets — not directly comparable."',
     "(2.11b) cotton disclaimer double-quote form"),
    ("`Bu iki seri farklı piyasalardır — doğrudan karşılaştırılmamalıdır.`",
     "`Different markets — not directly comparable.`",
     "(2.11c) cotton disclaimer template form"),
]
disclaimer_done = False
for old, new, lbl in disclaimer_replacements:
    if old in src:
        src = src.replace(old, new)
        print(f"[OK]   {lbl}")
        disclaimer_done = True
        break
if not disclaimer_done:
    if "Different markets — not directly comparable" in src:
        print("[skip] (2.11) cotton disclaimer already translated")
    else:
        print("[!]    (2.11) cotton disclaimer not found in known forms")

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
print("Done. Browser: Ctrl+Shift+R on Price Intelligence.")
print()
print("Note: signal card BODY text (explanation, business_implication) still")
print("appears in Turkish because it comes from the DB. Translating the")
print("signal generator (build_price_signals.py) is PI-1.6c, deferred.")
