"""
pi_1_9_rename_and_viscose.py - Three small text changes.

(1) Section / sidebar label:
    'Price Intelligence' -> 'Raw Material Price Intelligence'
    Conveys what the section actually is: tracked raw materials,
    not internal pricing.

(2) Material label cleanup (PI-1.6b leftover):
    'Rayon İpliği' -> 'Viscose Yarn'
    Reason: Mert uses viscose and modal in production. The DB field
    `rayon_yarn` is a generic-rayon scrape from SunSirs but for the
    user's reality the relevant material is viscose. UI label changes
    to 'Viscose Yarn'; the underlying DB key (rayon_yarn) stays so
    no migration is needed yet.

(3) Family mapping for grouping (used by PI-1.8a):
    fam: 'rayon' -> fam: 'viscose'
    Family label in PRICE_MATS so the upcoming family-grouped
    summary table groups Viscose Yarn under VISCOSE, not RAYON.

Frontend-only. No DB changes. No API changes.

Idempotent.
"""
from pathlib import Path
import re
import io
import time

REPO  = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"

# ─────────────────────────────────────────────────────────────────────────────
# (1) Section rename — find current "Price Intelligence" label location.
#
# Likely spots:
#   - sidebar nav button (HTML)
#   - inline page header text inside main content (HTML)
# We try the most common patterns; if none matches, we report and skip.
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")

# Probe: the literal "Price Intelligence" string in HTML.
old_section = "Price Intelligence"
new_section = "Raw Material Price Intelligence"

if "Raw Material Price Intelligence" in html:
    print("[skip] (1) section already renamed")
elif old_section in html:
    # Replace ALL occurrences in HTML (sidebar + page header).
    n = html.count(old_section)
    html = html.replace(old_section, new_section)
    print(f"[OK]   (1) HTML: 'Price Intelligence' -> 'Raw Material Price Intelligence' ({n} occurrence{'s' if n != 1 else ''})")
else:
    print("[!]    (1) 'Price Intelligence' not found in HTML")
    print("           (sidebar label may be in JS; will check next)")

# Maybe the label is in JS-rendered nav. Check app.v5.js too.
src = APPJS.read_text(encoding="utf-8")
if "'Price Intelligence'" in src:
    src = src.replace("'Price Intelligence'", "'Raw Material Price Intelligence'")
    print("[OK]   (1b) JS string 'Price Intelligence' updated")
elif '"Price Intelligence"' in src:
    src = src.replace('"Price Intelligence"', '"Raw Material Price Intelligence"')
    print("[OK]   (1b) JS string \"Price Intelligence\" updated")

# ─────────────────────────────────────────────────────────────────────────────
# (2) Material label: Rayon İpliği -> Viscose Yarn
# ─────────────────────────────────────────────────────────────────────────────
OLD_LABEL = "rayon_yarn:             'Rayon İpliği',"
NEW_LABEL = "rayon_yarn:             'Viscose Yarn',"

if "rayon_yarn:             'Viscose Yarn'," in src:
    print("[skip] (2) Viscose Yarn label already set")
elif OLD_LABEL in src:
    src = src.replace(OLD_LABEL, NEW_LABEL)
    print("[OK]   (2) Material label: 'Rayon İpliği' -> 'Viscose Yarn'")
else:
    # Fallback: looser match (in case whitespace differs)
    m = re.search(r"rayon_yarn:\s*'Rayon\s*İpliği'\s*,", src)
    if m:
        src = src[:m.start()] + "rayon_yarn:             'Viscose Yarn'," + src[m.end():]
        print("[OK]   (2) Material label updated via regex fallback")
    else:
        print("[!]    (2) Rayon label not found in expected form")

# ─────────────────────────────────────────────────────────────────────────────
# (3) Family mapping: 'rayon' -> 'viscose' for rayon_yarn entry in PRICE_MATS
# ─────────────────────────────────────────────────────────────────────────────
OLD_FAM = "{ key: 'rayon_yarn',             fam: 'rayon'     },"
NEW_FAM = "{ key: 'rayon_yarn',             fam: 'viscose'   },"

if "{ key: 'rayon_yarn',             fam: 'viscose'   }," in src:
    print("[skip] (3) family already 'viscose'")
elif OLD_FAM in src:
    src = src.replace(OLD_FAM, NEW_FAM)
    print("[OK]   (3) Family mapping: rayon_yarn fam -> 'viscose'")
else:
    # Fallback
    m = re.search(r"\{\s*key:\s*'rayon_yarn'[^}]*fam:\s*'rayon'[^}]*\},", src)
    if m:
        repl = m.group(0).replace("'rayon'", "'viscose'", 1)
        src = src[:m.start()] + repl + src[m.end():]
        print("[OK]   (3) Family mapping updated via regex fallback")
    else:
        print("[!]    (3) Family mapping not found in expected form")

APPJS.write_text(src, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# Cache buster — UTF-8 no BOM, explicit
# ─────────────────────────────────────────────────────────────────────────────
ts = int(time.time())
html = re.sub(r'app\.v5\.js\?v=\d+', f'app.v5.js?v={ts}', html)
html = re.sub(r'style\.v5\.css\?v=\d+', f'style.v5.css?v={ts}', html)

with io.open(INDEX, "w", encoding="utf-8", newline="") as f:
    f.write(html)
print(f"[OK]   cache buster -> {ts}")

print()
print("Done. Browser: Ctrl+Shift+R.")
print()
print("Expected:")
print("  - Section/sidebar reads 'Raw Material Price Intelligence'")
print("  - Materials Summary table shows 'Viscose Yarn' (not 'Rayon İpliği')")
print("  - Future PI-1.8a family grouping will place it under VISCOSE")
