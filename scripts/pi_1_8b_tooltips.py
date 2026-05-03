"""
pi_1_8b_tooltips.py - Tooltip layer for the materials summary table.

Adds explanatory hover tooltips to:
  - Trend column header
  - Momentum column header
  - Quality column header (already had one; refined)
  - TR Lag column header
  - Tier badge cells (A/B/C/D/E with per-tier explanation)
  - TR Lag badge cells (with the actual range spelled out)

No new data required, no new column. Pure UI affordance: when the user
hovers a column header or a cell, they see what it means.

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

if "// PI-1.8b: tooltips" in src:
    print("[skip] PI-1.8b tooltips already applied")
    raise SystemExit(0)

# ─────────────────────────────────────────────────────────────────────────────
# (1) Header tooltips — replace the static <th> for Trend, Momentum, Quality,
# and adjust the sortable-th call for TR Lag header to include a tooltip.
#
# We patch by string match. The existing header lines:
#   <th class="num">Trend</th>
#   <th class="num">Momentum</th>
#   ${sortableTh('tier', 'Quality', 'num')}
#   ${sortableTh('lagMid', 'TR Lag', 'num')}
# ─────────────────────────────────────────────────────────────────────────────
OLD_TREND = '<th class="num">Trend</th>'
NEW_TREND = '<th class="num" title="Direction over the last window (up / flat / down)">Trend</th>'

OLD_MOM   = '<th class="num">Momentum</th>'
NEW_MOM   = '<th class="num" title="Speed and acceleration of recent price movement">Momentum</th>'

if OLD_TREND in src:
    src = src.replace(OLD_TREND, NEW_TREND, 1)
    print("[OK]   (1a) Trend header tooltip")
else:
    print("[!]    (1a) Trend header line not found")

if OLD_MOM in src:
    src = src.replace(OLD_MOM, NEW_MOM, 1)
    print("[OK]   (1b) Momentum header tooltip")
else:
    print("[!]    (1b) Momentum header line not found")

# ─────────────────────────────────────────────────────────────────────────────
# (2) Add a "title" optional parameter to sortableTh so Quality and TR Lag
# headers can carry their own tooltip without sacrificing sort affordance.
#
# Existing sortableTh definition:
#   const sortableTh = (col, label, extraCls = '') => {
#     const cls = `sortable ${extraCls}`.trim();
#     return `<th class="${cls}" data-sort-col="${col}">${label}${sortIndicator(col)}</th>`;
#   };
#
# New definition adds an optional `tooltip` parameter.
# ─────────────────────────────────────────────────────────────────────────────
OLD_STH = """  const sortableTh = (col, label, extraCls = '') => {
    const cls = `sortable ${extraCls}`.trim();
    return `<th class="${cls}" data-sort-col="${col}">${label}${sortIndicator(col)}</th>`;
  };"""

NEW_STH = """  const sortableTh = (col, label, extraCls = '', tooltip = '') => {
    const cls = `sortable ${extraCls}`.trim();
    const t   = tooltip ? ` title="${tooltip}"` : '';
    return `<th class="${cls}"${t} data-sort-col="${col}">${label}${sortIndicator(col)}</th>`;
  };"""

if OLD_STH in src:
    src = src.replace(OLD_STH, NEW_STH, 1)
    print("[OK]   (2) sortableTh helper accepts optional tooltip arg")
else:
    print("[!]    (2) sortableTh helper not in expected form")

# Update the two sortableTh calls that need tooltips (Quality, TR Lag).
OLD_QUAL = "${sortableTh('tier', 'Quality', 'num')}"
NEW_QUAL = "${sortableTh('tier', 'Quality', 'num', 'Data quality: A=60+ days, B=30+, C=14+, D=7+, E=<7 days of usable history')}"

OLD_LAG  = "${sortableTh('lagMid', 'TR Lag', 'num')}"
NEW_LAG  = "${sortableTh('lagMid', 'TR Lag', 'num', 'Estimated Turkey supplier pass-through lag (weeks)')}"

if OLD_QUAL in src:
    src = src.replace(OLD_QUAL, NEW_QUAL, 1)
    print("[OK]   (3a) Quality header tooltip")
else:
    print("[!]    (3a) Quality header sortableTh call not found")

if OLD_LAG in src:
    src = src.replace(OLD_LAG, NEW_LAG, 1)
    print("[OK]   (3b) TR Lag header tooltip")
else:
    print("[!]    (3b) TR Lag header sortableTh call not found")

# ─────────────────────────────────────────────────────────────────────────────
# (4) Tier badge cells — add per-tier tooltip
#
# Current line:
#   const tierHtml = r.tier ? `<span class="tier-badge tier-${r.tier}">${r.tier}</span>` : INS;
# ─────────────────────────────────────────────────────────────────────────────
OLD_TIER = "const tierHtml = r.tier ? `<span class=\"tier-badge tier-${r.tier}\">${r.tier}</span>` : INS;"

NEW_TIER = """const TIER_DESC = {
      A: '60+ days of history — high confidence',
      B: '30+ days of history — usable directional',
      C: '14+ days of history — directional, weaker',
      D: '7+ days of history — short series',
      E: '<7 days of history — collecting data',
    };
    const tierHtml = r.tier
      ? `<span class="tier-badge tier-${r.tier}" title="${TIER_DESC[r.tier] || ''}">${r.tier}</span>`
      : INS;"""

if OLD_TIER in src:
    src = src.replace(OLD_TIER, NEW_TIER, 1)
    print("[OK]   (4) Tier badge cells get per-tier tooltip")
else:
    print("[!]    (4) tierHtml line not in expected form")

# ─────────────────────────────────────────────────────────────────────────────
# (5) TR Lag badge cells — add tooltip showing actual range
#
# Current line (note the unicode escape \\u2013 for en-dash):
#   const lagHtml  = (r.lagMin && r.lagMax)
#     ? `<span class="turkey-lag-badge">${r.lagMin}\\u2013${r.lagMax} wk</span>`
#     : INS;
# ─────────────────────────────────────────────────────────────────────────────
OLD_LAG_CELL = """const lagHtml  = (r.lagMin && r.lagMax)
      ? `<span class="turkey-lag-badge">${r.lagMin}\\u2013${r.lagMax} wk</span>`
      : INS;"""

NEW_LAG_CELL = """const lagHtml  = (r.lagMin && r.lagMax)
      ? `<span class="turkey-lag-badge" title="Turkey supplier pass-through estimate: ${r.lagMin} to ${r.lagMax} weeks">${r.lagMin}\\u2013${r.lagMax} wk</span>`
      : INS;"""

if OLD_LAG_CELL in src:
    src = src.replace(OLD_LAG_CELL, NEW_LAG_CELL, 1)
    print("[OK]   (5) TR Lag badge cells get range tooltip")
else:
    print("[!]    (5) lagHtml line not in expected form")

# ─────────────────────────────────────────────────────────────────────────────
# Add a sentinel comment so the idempotent guard works.
# ─────────────────────────────────────────────────────────────────────────────
SENTINEL_OLD = "function _renderPriceSummaryTable(data) {\n  // PI-1.8a:"
SENTINEL_NEW = "function _renderPriceSummaryTable(data) {\n  // PI-1.8b: tooltips applied\n  // PI-1.8a:"
if SENTINEL_NEW not in src and SENTINEL_OLD in src:
    src = src.replace(SENTINEL_OLD, SENTINEL_NEW, 1)

APPJS.write_text(src, encoding="utf-8")

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
print("Test by hovering on:")
print("  - Trend / Momentum / Quality / TR Lag header cells")
print("  - Any A/B/C tier badge in the Quality column")
print("  - Any '3-6 wk' badge in the TR Lag column")
