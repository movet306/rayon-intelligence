"""
pi_2a_material_type.py - Add Type column to Materials Summary table.

Each tracked material is classified into one of four roles relative to
Rayon's procurement reality:

  Direct    — bought and used directly in production
  Benchmark — tracked for market awareness, not actually purchased
  Proxy     — upstream / leading driver of an input we use
  Estimate  — driver-based estimated price, not a real quote

Initial mapping (defensible starting point, can flip Direct/Benchmark
later when item-level Nebim data is available):

  POLYESTER:
    polyester_staple_fiber : Benchmark   (no staple spinning at Rayon)
    polyester_fdy          : Direct      (main filament input)
    polyester_poy          : Proxy       (upstream of DTY/FDY)
    polyester_dty          : Direct      (used in knit + woven)
    polyester_yarn         : Estimate    (driver-based)
    pta                    : Proxy       (chain upstream)

  COTTON:
    cotton_lint            : Benchmark   (SunSirs China spot)
    cotton_lint_futures    : Benchmark   (ICE futures)
    cotton_yarn            : Direct      (cotton fabric inputs)

  NYLON:
    polyamide_fdy          : Direct      (override to Benchmark if not used)
    pa6_chip               : Proxy       (FDY upstream)
    pa66_chip              : Proxy       (FDY upstream)
    adipic_acid            : Proxy       (PA66 leading driver)

  VISCOSE:
    rayon_yarn             : Direct      (viscose yarn — directly used)

UI changes:
  - Type column inserted between Material and Price (5th visible column).
  - Each cell shows a colored pill badge.
  - Header is sortable + carries an explanatory tooltip.
  - Sort key: typeOrder (Direct=0, Benchmark=1, Proxy=2, Estimate=3).
  - In flat (sorted) mode, the family badge already shown on each row
    sits next to the Material name; the Type badge is its own column.

Idempotent.
"""
from pathlib import Path
import re
import io
import time

REPO  = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"
CSS   = REPO / "dashboard" / "static" / "style.v5.css"

src = APPJS.read_text(encoding="utf-8")

if "// PI-2a: MATERIAL_TYPE" in src:
    print("[skip] PI-2a already applied")
    raise SystemExit(0)

# ─────────────────────────────────────────────────────────────────────────────
# (1) Add MATERIAL_TYPE constant near other top-level mappings.
# Anchor on ALL_PRICE_MATS definition, insert after it.
# ─────────────────────────────────────────────────────────────────────────────
ANCHOR = "const ALL_PRICE_MATS = ["

INSERT = '''// PI-2a: MATERIAL_TYPE — role of each tracked material in Rayon's procurement.
//   Direct    = bought and used directly
//   Benchmark = tracked for market awareness only
//   Proxy     = upstream / leading driver of an input we use
//   Estimate  = driver-based estimated price
// Override rule: if item-level Nebim data later shows direct purchase,
// flip Benchmark/Proxy to Direct.
const MATERIAL_TYPE = {
  // Polyester
  polyester_staple_fiber: 'Benchmark',
  polyester_fdy:          'Direct',
  polyester_poy:          'Proxy',
  polyester_dty:          'Direct',
  polyester_yarn:         'Estimate',
  pta:                    'Proxy',
  // Cotton
  cotton_lint:            'Benchmark',
  cotton_lint_futures:    'Benchmark',
  cotton_yarn:            'Direct',
  // Nylon
  polyamide_fdy:          'Direct',
  pa6_chip:                'Proxy',
  pa66_chip:               'Proxy',
  adipic_acid:             'Proxy',
  // Viscose
  rayon_yarn:              'Direct',
};
const MATERIAL_TYPE_ORDER = { Direct: 0, Benchmark: 1, Proxy: 2, Estimate: 3 };
const MATERIAL_TYPE_TOOLTIP = {
  Direct:    'Direct: bought and used in production',
  Benchmark: 'Benchmark: tracked for market awareness, not purchased',
  Proxy:     'Proxy: upstream / leading driver of an input we use',
  Estimate:  'Estimate: driver-based price, not a real quote',
};

'''

idx = src.find(ANCHOR)
if idx == -1:
    print("[X] could not locate ALL_PRICE_MATS anchor")
    raise SystemExit(1)

src = src[:idx] + INSERT + src[idx:]
print("[OK]   (1) MATERIAL_TYPE / ORDER / TOOLTIP constants added")

# ─────────────────────────────────────────────────────────────────────────────
# (2) Add `type` field to each record in records.map, and `typeOrder` for sort.
# ─────────────────────────────────────────────────────────────────────────────
OLD_RECORD = """    return {
      key: m.key, fam: m.fam,
      label: MATERIAL_LABELS[m.key] || m.key,
      price: _latestPrice(l),
      change_1d: l?.change_1d, change_7d: l?.change_7d, change_30d: l?.change_30d,
      trend: l?.trend_direction, momentum: l?.momentum_score,
      tier, lagMin, lagMax, lagMid,
      isTierE, isMinimal,
    };"""

NEW_RECORD = """    return {
      key: m.key, fam: m.fam,
      label: MATERIAL_LABELS[m.key] || m.key,
      type: MATERIAL_TYPE[m.key] || null,
      typeOrder: MATERIAL_TYPE_ORDER[MATERIAL_TYPE[m.key]] ?? 99,
      price: _latestPrice(l),
      change_1d: l?.change_1d, change_7d: l?.change_7d, change_30d: l?.change_30d,
      trend: l?.trend_direction, momentum: l?.momentum_score,
      tier, lagMin, lagMax, lagMid,
      isTierE, isMinimal,
    };"""

if OLD_RECORD in src:
    src = src.replace(OLD_RECORD, NEW_RECORD, 1)
    print("[OK]   (2) records carry type + typeOrder")
else:
    print("[X]    (2) record literal not found in expected form")
    raise SystemExit(1)

# ─────────────────────────────────────────────────────────────────────────────
# (3) Insert Type column header — between Material and Price.
# ─────────────────────────────────────────────────────────────────────────────
OLD_HEADER = """  const headerHtml = `
    <thead><tr>
      ${sortableTh('label', 'Material')}
      ${sortableTh('price', `Price (${_currency === 'usd' ? 'USD/t' : 'RMB/t'})`, 'num')}"""

NEW_HEADER = """  const headerHtml = `
    <thead><tr>
      ${sortableTh('label', 'Material')}
      ${sortableTh('typeOrder', 'Type', '', 'Material role: Direct (bought) / Benchmark (tracked only) / Proxy (upstream driver) / Estimate (driver-based)')}
      ${sortableTh('price', `Price (${_currency === 'usd' ? 'USD/t' : 'RMB/t'})`, 'num')}"""

if OLD_HEADER in src:
    src = src.replace(OLD_HEADER, NEW_HEADER, 1)
    print("[OK]   (3) Type column header inserted")
else:
    print("[X]    (3) header block not found in expected form")
    raise SystemExit(1)

# ─────────────────────────────────────────────────────────────────────────────
# (4) Insert Type cell in row HTML — between Material and Price.
# ─────────────────────────────────────────────────────────────────────────────
OLD_ROW = """    return `<tr class="${famCls} ${tierECls} ${minCls}"${tooltip}>
      <td>${matBadge}${esc(r.label)}</td>
      <td class="num">${_priceFmt(r.price)}</td>"""

NEW_ROW = """    const typeBadge = r.type
      ? `<span class="type-badge type-${r.type.toLowerCase()}" title="${MATERIAL_TYPE_TOOLTIP[r.type] || ''}">${r.type}</span>`
      : INS;

    return `<tr class="${famCls} ${tierECls} ${minCls}"${tooltip}>
      <td>${matBadge}${esc(r.label)}</td>
      <td>${typeBadge}</td>
      <td class="num">${_priceFmt(r.price)}</td>"""

if OLD_ROW in src:
    src = src.replace(OLD_ROW, NEW_ROW, 1)
    print("[OK]   (4) Type cell added to row HTML")
else:
    print("[X]    (4) row literal not found in expected form")
    raise SystemExit(1)

# ─────────────────────────────────────────────────────────────────────────────
# (5) Update colspan on family-header rows from 9 to 10 (we added one column).
# Two occurrences: main loop and leftover loop.
# ─────────────────────────────────────────────────────────────────────────────
old_colspan = 'colspan="9"'
new_colspan = 'colspan="10"'
count = src.count(old_colspan)
if count > 0:
    src = src.replace(old_colspan, new_colspan)
    print(f"[OK]   (5) family-header colspan: 9 -> 10 ({count} occurrence{'s' if count != 1 else ''})")
else:
    print("[!]    (5) colspan=9 not found (already updated?)")

APPJS.write_text(src, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# (6) CSS for type badges
# ─────────────────────────────────────────────────────────────────────────────
css_src = CSS.read_text(encoding="utf-8")

CSS_HEADER = "/* ── PI-2a: type badges"

CSS_BLOCK = """

/* ── PI-2a: type badges (Direct / Benchmark / Proxy / Estimate) ───────────── */
.type-badge {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.4px;
  padding: 2px 7px;
  border-radius: 3px;
  vertical-align: middle;
  border: 1px solid transparent;
}
.type-direct {
  color: #7ee787;
  background: rgba(86, 211, 100, 0.10);
  border-color: rgba(86, 211, 100, 0.25);
}
.type-benchmark {
  color: #8ad7ff;
  background: rgba(76, 154, 255, 0.10);
  border-color: rgba(76, 154, 255, 0.25);
}
.type-proxy {
  color: #ffb86c;
  background: rgba(241, 161, 105, 0.10);
  border-color: rgba(241, 161, 105, 0.25);
}
.type-estimate {
  color: #c2c8d3;
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.12);
}
"""

if CSS_HEADER in css_src:
    print("[skip] (6) PI-2a CSS already present")
else:
    CSS.write_text(css_src.rstrip() + CSS_BLOCK, encoding="utf-8")
    print("[OK]   (6) PI-2a CSS appended")

# ─────────────────────────────────────────────────────────────────────────────
# Cache buster
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")
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
print("  - New 'Type' column between Material and Price.")
print("  - Direct/Benchmark/Proxy/Estimate badges with distinct colors.")
print("  - Sort by Type works (Direct first, then Benchmark, Proxy, Estimate).")
print("  - Header tooltip explains the four types.")
