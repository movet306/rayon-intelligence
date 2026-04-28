"""
M2.2.1 — Top Suppliers table enrichment (Procurement Phase 1).

Backend: extend /api/internal/top-suppliers to return the new columns from
v_top_suppliers_overall (Migration 015).

Frontend: render share %, last invoice date, trend symbol, and verification
badges in the Operations Intelligence > Procurement > Top 10 Suppliers table.

Backups: .bak_m22_1 suffix.
"""
from pathlib import Path
import re

SERVER = Path("dashboard/server.py")
APP_JS = Path("dashboard/static/app.v5.js")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m22_1")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. Backend — extend the SQL in /api/internal/top-suppliers
# ─────────────────────────────────────────────────────────────────────────
print("[1/2] Patching backend endpoint...")
text = SERVER.read_text(encoding="utf-8")
backup(SERVER)

OLD_SQL = '''    rows = _rows("""
        SELECT
            supplier_name,
            row_count,
            bucket_count,
            amount_tl::float    AS amount_tl,
            amount_usd::float   AS amount_usd,
            amount_eur::float   AS amount_eur,
            top_bucket,
            to_char(first_invoice_date, 'YYYY-MM-DD') AS first_invoice_date,
            to_char(last_invoice_date,  'YYYY-MM-DD') AS last_invoice_date
        FROM v_top_suppliers_overall
        ORDER BY amount_tl DESC NULLS LAST
        LIMIT %s
    """, [limit])'''

NEW_SQL = '''    rows = _rows("""
        SELECT
            supplier_name,
            row_count,
            bucket_count,
            amount_tl::float    AS amount_tl,
            amount_usd::float   AS amount_usd,
            amount_eur::float   AS amount_eur,
            top_bucket,
            to_char(first_invoice_date, 'YYYY-MM-DD') AS first_invoice_date,
            to_char(last_invoice_date,  'YYYY-MM-DD') AS last_invoice_date,
            -- M2.2.1 enrichment (Migration 015)
            share_pct::float    AS share_pct,
            trend_direction,
            amount_tl_h1::float AS amount_tl_h1,
            amount_tl_h2::float AS amount_tl_h2,
            vergi_numarasi,
            is_verified,
            name_variants_count
        FROM v_top_suppliers_overall
        ORDER BY amount_tl DESC NULLS LAST
        LIMIT %s
    """, [limit])'''

if NEW_SQL.strip() in text:
    print("  ⏭  endpoint already patched")
elif OLD_SQL.strip() not in text:
    print("  ❌ original SQL block not found — patch aborted")
    raise SystemExit(1)
else:
    text = text.replace(OLD_SQL, NEW_SQL, 1)
    SERVER.write_text(text, encoding="utf-8")
    print("  ✓ endpoint extended with new columns")


# ─────────────────────────────────────────────────────────────────────────
# 2. Frontend — extend the renderer for ops-suppliers-table
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/2] Patching frontend renderer...")
js = APP_JS.read_text(encoding="utf-8")
backup(APP_JS)

# Find the existing renderer block (around line 1970 — uses ops-suppliers-table)
# Strategy: locate the block by anchor text and replace it as a whole.

# The renderer block is something like:
#   const el = document.getElementById('ops-suppliers-table');
#   ... builds an HTML table from the suppliers array ...

# We need to find this block and replace it. Let's locate first.

# Find a reasonable anchor
anchor_start = js.find("const el = document.getElementById('ops-suppliers-table');")
if anchor_start < 0:
    print("  ❌ could not find ops-suppliers-table anchor")
    raise SystemExit(1)

# Find a reasonable end: next function declaration OR another const el = document.getElementById
# Conservative approach: search forward for the next 'function ' or 'async function ' or
# the closing of the function this code belongs to. We'll match braces.

# Easier: find the function this anchor lives in. Walk backward to find 'function'
back_search = js[:anchor_start].rfind('function ')
if back_search < 0:
    print("  ❌ could not find enclosing function")
    raise SystemExit(1)

# Find function open brace
fn_start = js.find('{', back_search)
# Match braces until we find the function close
depth = 1
i = fn_start + 1
while i < len(js) and depth > 0:
    if js[i] == '{':
        depth += 1
    elif js[i] == '}':
        depth -= 1
    i += 1
fn_end = i

# Now replace the *entire body* of this function. But to be safe, we only want to
# replace the suppliers-table rendering block, not the whole function. Look for
# a specific HTML-building pattern.

# Inspect: find 'ops-suppliers-table' occurrence and the next line that uses
# innerHTML or template literals. We'll match a block that:
#   - starts with: const el = document.getElementById('ops-suppliers-table');
#   - ends with: el.innerHTML = `...`; (closing backtick)

block_start = anchor_start
# Find the next `el.innerHTML =` or assignment ending in backtick
ih_idx = js.find("el.innerHTML", block_start)
if ih_idx < 0:
    print("  ❌ could not find el.innerHTML for suppliers table")
    raise SystemExit(1)

# Find the closing backtick of the template literal that follows el.innerHTML = `
bt1 = js.find("`", ih_idx)
# Match to the closing backtick (skip escaped ones — but template literals don't escape)
# Naive: find next unescaped backtick
bt2 = js.find("`", bt1 + 1)
# But there may be ${...} inside. Find the literal end by scanning for a final ` followed by ;
end_search = js.find("`;", ih_idx)
if end_search < 0:
    print("  ❌ could not find end of suppliers innerHTML template")
    raise SystemExit(1)

block_end = end_search + 2  # include `;

original_block = js[block_start:block_end]

# Sanity: print the size
print(f"  found existing block: {len(original_block)} chars")

# Construct new renderer block
NEW_RENDERER = '''const el = document.getElementById('ops-suppliers-table');
  if (!el) return;
  if (!suppliers || suppliers.length === 0) {
    el.innerHTML = '<div class="empty-state">No supplier data.</div>';
    return;
  }

  // M2.2.1 enrichment helpers
  const _stripTaxZero = v => {
    if (v == null) return '';
    let s = String(v).trim();
    if (s.endsWith('.0')) s = s.slice(0, -2);
    return s;
  };
  const _fmtTL = v => {
    if (v == null || isNaN(v)) return '—';
    const abs = Math.abs(v);
    if (abs >= 1e9) return '₺' + (v/1e9).toFixed(1) + 'B';
    if (abs >= 1e6) return '₺' + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return '₺' + (v/1e3).toFixed(0) + 'K';
    return '₺' + v.toFixed(0);
  };
  const _fmtFx = (v, sym) => {
    if (v == null || isNaN(v) || v === 0) return '—';
    const abs = Math.abs(v);
    if (abs >= 1e6) return sym + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return sym + (v/1e3).toFixed(0) + 'K';
    return sym + v.toFixed(0);
  };
  const _badges = s => {
    const out = [];
    if (s.is_verified === false) {
      out.push('<span class="ce-badge ce-badge-warn" title="No verified tax id — name-grouped">no-tax</span>');
    }
    if (s.name_variants_count > 1) {
      out.push(`<span class="ce-badge ce-badge-info" title="${s.name_variants_count} display name variants">${s.name_variants_count} vars</span>`);
    }
    return out.join(' ');
  };
  const _trendCell = t => {
    if (t === '▲') return '<span class="trend-up" title="Spend rising (last 6m vs prior 6m, ≥10%)">▲</span>';
    if (t === '▼') return '<span class="trend-down" title="Spend falling (last 6m vs prior 6m, ≥10%)">▼</span>';
    return '<span class="trend-flat" title="Spend stable (within ±10%)">–</span>';
  };

  el.innerHTML = `
    <table class="ops-table ops-suppliers">
      <thead>
        <tr>
          <th class="num">#</th>
          <th>Supplier</th>
          <th class="num">TL spend</th>
          <th class="num">Share</th>
          <th class="num">USD invoiced</th>
          <th class="num">EUR invoiced</th>
          <th>Top bucket</th>
          <th class="num">Buckets</th>
          <th class="num">Last invoice</th>
          <th class="num">Trend</th>
        </tr>
      </thead>
      <tbody>
        ${suppliers.map((s, i) => `
          <tr>
            <td class="num">${i+1}</td>
            <td>
              <div class="cell-supplier">
                <span class="supplier-name">${(s.supplier_name || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')}</span>
                ${_badges(s) ? `<span class="supplier-badges">${_badges(s)}</span>` : ''}
              </div>
            </td>
            <td class="num">${_fmtTL(s.amount_tl)}</td>
            <td class="num">${s.share_pct != null ? s.share_pct.toFixed(2) + '%' : '—'}</td>
            <td class="num">${_fmtFx(s.amount_usd, '$')}</td>
            <td class="num">${_fmtFx(s.amount_eur, '€')}</td>
            <td>${(s.top_bucket || '—').replace(/_/g, ' ')}</td>
            <td class="num">${s.bucket_count}</td>
            <td class="num">${s.last_invoice_date || '—'}</td>
            <td class="num">${_trendCell(s.trend_direction)}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;'''

# Replace
js = js[:block_start] + NEW_RENDERER + js[block_end:]
APP_JS.write_text(js, encoding="utf-8")
print("  ✓ frontend renderer updated")


# ─────────────────────────────────────────────────────────────────────────
# 3. CSS — trend cell colors (small append)
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/3] Patching style.v5.css for trend symbol colors...")
CSS = Path("dashboard/static/style.v5.css")
css = CSS.read_text(encoding="utf-8")

CSS_MARKER = "/* === Procurement Phase 1 trend symbols (M2.2.1) === */"
CSS_BLOCK = '''

/* === Procurement Phase 1 trend symbols (M2.2.1) === */
.trend-up   { color: #2f9e44; font-weight: 700; }
.trend-down { color: #e03131; font-weight: 700; }
.trend-flat { color: #868e96; font-weight: 500; }

.ops-suppliers .cell-supplier {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.ops-suppliers .supplier-badges {
  display: inline-flex;
  gap: 4px;
}
'''

if CSS_MARKER not in css:
    backup(CSS)
    css = css.rstrip() + "\n" + CSS_BLOCK
    CSS.write_text(css, encoding="utf-8")
    print("  ✓ trend / badge styles added")
else:
    print("  ⏭  trend styles already present")


print()
print("=" * 60)
print("M2.2.1 — Top Suppliers table enrichment complete.")
print("=" * 60)
print()
print("New columns visible:")
print("  - Share %        (supplier's % of cost-relevant procurement)")
print("  - Last invoice   (latest invoice date)")
print("  - Trend          (▲ ▼ – : last 6m vs prior 6m, ±10%)")
print("  - Badges         (no-tax warning, name variants count)")
print()
print("Restart uvicorn to load endpoint changes:")
print("  Ctrl+C, then: python -m uvicorn dashboard.server:app --port 8000")
print()
print("Then in browser: hard-refresh (Ctrl+Shift+R) on Procurement sub-tab.")
