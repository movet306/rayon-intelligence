"""
pi_2b_filter_chips.py - Type filter chips above the Materials Summary table.

Adds a row of clickable chips:
  [All]  [Direct]  [Benchmark]  [Proxy]  [Estimate]

Each chip shows the count of materials in that type. Clicking a chip
filters the table to materials of that type only. The active chip is
visually highlighted.

Behavior:
  - 'All' is the default (no filter, current behavior).
  - Filter respects sort state and family-collapse state.
  - When filtering by a non-All type, family grouping still applies but
    only families containing at least one matching material show.
  - Sort still works inside the filtered set.
  - Clicking the active chip again does nothing (must click another).

State:
  - _renderPriceSummaryTable._typeFilter = null | 'Direct' | 'Benchmark' | 'Proxy' | 'Estimate'

UI:
  - Chip row sits between section header (with the down-arrow toggle)
    and the table itself, so the existing collapse-section behavior
    is unaffected.

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

if "// PI-2b: filter chips" in src:
    print("[skip] PI-2b filter chips already applied")
    raise SystemExit(0)

# ─────────────────────────────────────────────────────────────────────────────
# (1) Initialize _typeFilter state at the top of _renderPriceSummaryTable.
# ─────────────────────────────────────────────────────────────────────────────
OLD_INIT = """  if (!fn._sortState)  fn._sortState  = null;
  if (!fn._collapsed)  fn._collapsed  = new Set();"""

NEW_INIT = """  if (!fn._sortState)  fn._sortState  = null;
  if (!fn._collapsed)  fn._collapsed  = new Set();
  // PI-2b: filter chips — null means All. Otherwise one of the type names.
  if (fn._typeFilter === undefined) fn._typeFilter = null;"""

if OLD_INIT in src:
    src = src.replace(OLD_INIT, NEW_INIT, 1)
    print("[OK]   (1) _typeFilter state initialized")
else:
    print("[X]    (1) state init block not found")
    raise SystemExit(1)

# ─────────────────────────────────────────────────────────────────────────────
# (2) Apply filter to records before rendering. We filter AFTER building
# the records (to keep counts intact for the chips themselves) but BEFORE
# rendering body html.
#
# Insert right before "let bodyHtml;"
# ─────────────────────────────────────────────────────────────────────────────
OLD_BEFORE_BODY = """  let bodyHtml;"""

NEW_BEFORE_BODY = """  // PI-2b: build the chip row counts BEFORE filtering, so chip counts
  // always reflect the full universe, not the filtered subset.
  const typeCounts = { Direct: 0, Benchmark: 0, Proxy: 0, Estimate: 0 };
  records.forEach(r => { if (r.type && typeCounts[r.type] !== undefined) typeCounts[r.type]++; });
  const totalCount = records.length;

  // Apply filter to the records used for body rendering.
  const visibleRecords = fn._typeFilter
    ? records.filter(r => r.type === fn._typeFilter)
    : records;

  let bodyHtml;"""

if OLD_BEFORE_BODY in src:
    src = src.replace(OLD_BEFORE_BODY, NEW_BEFORE_BODY, 1)
    print("[OK]   (2) filter applied before body render")
else:
    print("[X]    (2) 'let bodyHtml' anchor not found")
    raise SystemExit(1)

# ─────────────────────────────────────────────────────────────────────────────
# (3) Replace `records` with `visibleRecords` in the two places it's used
# for rendering: the sort branch and the grouped branch.
# ─────────────────────────────────────────────────────────────────────────────
# Sort branch
OLD_SORT = "    const sorted = records.slice().sort((a, b) => {"
NEW_SORT = "    const sorted = visibleRecords.slice().sort((a, b) => {"

if OLD_SORT in src:
    src = src.replace(OLD_SORT, NEW_SORT, 1)
    print("[OK]   (3a) sort branch uses visibleRecords")
else:
    print("[!]    (3a) sort branch anchor not found")

# Grouped branch — main loop
OLD_GROUPED = """    records.forEach(r => {
      if (!groups[r.fam]) groups[r.fam] = [];
      groups[r.fam].push(r);
    });"""

NEW_GROUPED = """    visibleRecords.forEach(r => {
      if (!groups[r.fam]) groups[r.fam] = [];
      groups[r.fam].push(r);
    });"""

if OLD_GROUPED in src:
    src = src.replace(OLD_GROUPED, NEW_GROUPED, 1)
    print("[OK]   (3b) grouped branch uses visibleRecords")
else:
    print("[!]    (3b) grouped branch anchor not found")

# Grouped branch — leftover loop (defensive)
OLD_LEFTOVER = "    const leftover = records.filter(r => !FAMILY_ORDER.includes(r.fam));"
NEW_LEFTOVER = "    const leftover = visibleRecords.filter(r => !FAMILY_ORDER.includes(r.fam));"
if OLD_LEFTOVER in src:
    src = src.replace(OLD_LEFTOVER, NEW_LEFTOVER, 1)
    print("[OK]   (3c) leftover loop uses visibleRecords")

# ─────────────────────────────────────────────────────────────────────────────
# (4) Inject the chip row into the rendered HTML.
# Currently the render line is:
#   document.getElementById('price-summary-table').innerHTML = `
#     <table class="data-table summary-table">${headerHtml}${bodyHtml}</table>`;
#
# We prepend a chip bar before the table.
# ─────────────────────────────────────────────────────────────────────────────
OLD_RENDER = """  document.getElementById('price-summary-table').innerHTML = `
    <table class="data-table summary-table">${headerHtml}${bodyHtml}</table>`;"""

NEW_RENDER = """  // PI-2b: build chip bar
  const mkChip = (label, count, value) => {
    const isActive = (fn._typeFilter === value) || (value === null && fn._typeFilter === null);
    const cls = `type-chip ${isActive ? 'type-chip-active' : ''} ${value ? `type-chip-${value.toLowerCase()}` : 'type-chip-all'}`.trim();
    return `<button class="${cls}" data-type-filter="${value === null ? 'all' : value}">${label} <span class="type-chip-count">${count}</span></button>`;
  };
  const chipBar = `
    <div class="type-chip-bar">
      ${mkChip('All', totalCount, null)}
      ${mkChip('Direct', typeCounts.Direct, 'Direct')}
      ${mkChip('Benchmark', typeCounts.Benchmark, 'Benchmark')}
      ${mkChip('Proxy', typeCounts.Proxy, 'Proxy')}
      ${mkChip('Estimate', typeCounts.Estimate, 'Estimate')}
    </div>
  `;

  document.getElementById('price-summary-table').innerHTML = `
    ${chipBar}
    <table class="data-table summary-table">${headerHtml}${bodyHtml}</table>`;

  // Wire chip clicks
  document.querySelectorAll('#price-summary-table .type-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const v = btn.dataset.typeFilter;
      fn._typeFilter = (v === 'all') ? null : v;
      _renderPriceSummaryTable(data);
    });
  });"""

if OLD_RENDER in src:
    src = src.replace(OLD_RENDER, NEW_RENDER, 1)
    print("[OK]   (4) chip bar injected into render")
else:
    print("[X]    (4) render anchor not found")
    raise SystemExit(1)

# Add a sentinel comment for the idempotent guard
SENTINEL_OLD = "function _renderPriceSummaryTable(data) {\n  // PI-1.8a:"
SENTINEL_NEW = "function _renderPriceSummaryTable(data) {\n  // PI-2b: filter chips applied\n  // PI-1.8a:"
if SENTINEL_NEW not in src and SENTINEL_OLD in src:
    src = src.replace(SENTINEL_OLD, SENTINEL_NEW, 1)

APPJS.write_text(src, encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# (5) CSS for the chip bar
# ─────────────────────────────────────────────────────────────────────────────
css_src = CSS.read_text(encoding="utf-8")

CSS_HEADER = "/* ── PI-2b: type filter chips"

CSS_BLOCK = """

/* ── PI-2b: type filter chips ─────────────────────────────────────────────── */
.type-chip-bar {
  display: flex;
  gap: 6px;
  padding: 8px 0 12px;
  flex-wrap: wrap;
  align-items: center;
}
.type-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 4px;
  color: var(--muted, #8a92a3);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.4px;
  cursor: pointer;
  transition: background 120ms, color 120ms, border-color 120ms;
}
.type-chip:hover {
  background: rgba(255, 255, 255, 0.07);
  color: var(--text, #e6e9ef);
}
.type-chip-count {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 700;
  background: rgba(255, 255, 255, 0.06);
  color: var(--muted, #8a92a3);
}
.type-chip-active {
  background: rgba(108, 182, 255, 0.12);
  border-color: rgba(108, 182, 255, 0.40);
  color: #cfe5ff;
}
.type-chip-active .type-chip-count {
  background: rgba(108, 182, 255, 0.20);
  color: #cfe5ff;
}
/* tinted active styles, matching the type-badge palette */
.type-chip-direct.type-chip-active {
  background: rgba(86, 211, 100, 0.12);
  border-color: rgba(86, 211, 100, 0.40);
  color: #b6f0bf;
}
.type-chip-direct.type-chip-active .type-chip-count {
  background: rgba(86, 211, 100, 0.20);
  color: #b6f0bf;
}
.type-chip-benchmark.type-chip-active {
  background: rgba(76, 154, 255, 0.12);
  border-color: rgba(76, 154, 255, 0.40);
  color: #cfe5ff;
}
.type-chip-benchmark.type-chip-active .type-chip-count {
  background: rgba(76, 154, 255, 0.20);
  color: #cfe5ff;
}
.type-chip-proxy.type-chip-active {
  background: rgba(241, 161, 105, 0.12);
  border-color: rgba(241, 161, 105, 0.40);
  color: #ffd9b3;
}
.type-chip-proxy.type-chip-active .type-chip-count {
  background: rgba(241, 161, 105, 0.20);
  color: #ffd9b3;
}
.type-chip-estimate.type-chip-active {
  background: rgba(255, 255, 255, 0.10);
  border-color: rgba(255, 255, 255, 0.30);
  color: #e6e9ef;
}
.type-chip-estimate.type-chip-active .type-chip-count {
  background: rgba(255, 255, 255, 0.18);
  color: #e6e9ef;
}
"""

if CSS_HEADER in css_src:
    print("[skip] (5) PI-2b CSS already present")
else:
    CSS.write_text(css_src.rstrip() + CSS_BLOCK, encoding="utf-8")
    print("[OK]   (5) PI-2b CSS appended")

# Cache buster
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
print("  - Chip bar above the table: All (14) | Direct (5) | Benchmark (3) | Proxy (5) | Estimate (1)")
print("  - 'All' is highlighted by default.")
print("  - Click 'Direct' -> only the 5 Direct rows show.")
print("  - Click 'All' -> back to full list.")
print("  - Filter respects sort state and family grouping.")
