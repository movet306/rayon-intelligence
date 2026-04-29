"""
M2.3.1 — Top Customers table enrichment (Revenue Phase 1).

Mirror of M2.2.1 (Top Suppliers enrichment).

Backend: extend /api/internal/top-customers to return the new columns from
v_top_customers_overall (Migration 019).

Frontend: render share %, last invoice date, trend symbol, and verification
badges in the Operations Intelligence > Revenue > Top 10 Customers table.

Backups: .bak_m23_1 suffix.
"""
from pathlib import Path

SERVER = Path("dashboard/server.py")
APP_JS = Path("dashboard/static/app.v5.js")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m23_1")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. Backend — extend the SQL in /api/internal/top-customers
# ─────────────────────────────────────────────────────────────────────────
print("[1/2] Patching backend endpoint...")
text = SERVER.read_text(encoding="utf-8")

OLD_SQL = '''    rows = _rows("""
        SELECT
            customer_name,
            row_count,
            bucket_count,
            amount_tl::float    AS amount_tl,
            amount_usd::float   AS amount_usd,
            amount_eur::float   AS amount_eur,
            rows_usd,
            rows_try,
            rows_eur,
            to_char(first_invoice_date, 'YYYY-MM-DD') AS first_invoice_date,
            to_char(last_invoice_date,  'YYYY-MM-DD') AS last_invoice_date
        FROM v_top_customers_overall
        ORDER BY amount_tl DESC NULLS LAST
        LIMIT %s
    """, [limit])'''

NEW_SQL = '''    rows = _rows("""
        SELECT
            customer_name,
            row_count,
            bucket_count,
            amount_tl::float    AS amount_tl,
            amount_usd::float   AS amount_usd,
            amount_eur::float   AS amount_eur,
            rows_usd,
            rows_try,
            rows_eur,
            to_char(first_invoice_date, 'YYYY-MM-DD') AS first_invoice_date,
            to_char(last_invoice_date,  'YYYY-MM-DD') AS last_invoice_date,
            -- M2.3.1 enrichment (Migration 019)
            share_pct::float    AS share_pct,
            trend_direction,
            amount_tl_h1::float AS amount_tl_h1,
            amount_tl_h2::float AS amount_tl_h2,
            vergi_numarasi,
            is_verified,
            name_variants_count
        FROM v_top_customers_overall
        ORDER BY amount_tl DESC NULLS LAST
        LIMIT %s
    """, [limit])'''

if NEW_SQL.strip() in text:
    print("  ⏭  endpoint already patched")
elif OLD_SQL.strip() not in text:
    print("  ❌ original SQL block not found — patch aborted")
    raise SystemExit(1)
else:
    backup(SERVER)
    text = text.replace(OLD_SQL, NEW_SQL, 1)
    SERVER.write_text(text, encoding="utf-8")
    print("  ✓ endpoint extended with new columns")


# ─────────────────────────────────────────────────────────────────────────
# 2. Frontend — extend the renderer for ops-customers-table
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/2] Patching frontend renderer...")
js = APP_JS.read_text(encoding="utf-8")

# Find the renderOpsCustomersTable function (paralleling renderOpsSuppliersTable)
fn_start = js.find("function renderOpsCustomersTable(")
if fn_start < 0:
    print("  ❌ renderOpsCustomersTable not found")
    raise SystemExit(1)

# Find the function body
brace_open = js.find("{", fn_start)
depth = 1
i = brace_open + 1
while i < len(js) and depth > 0:
    if js[i] == "{":
        depth += 1
    elif js[i] == "}":
        depth -= 1
    i += 1
fn_end = i

backup(APP_JS)

# Build the replacement: full function body
NEW_FN = '''function renderOpsCustomersTable(payload) {
  const customers = payload?.customers || [];
  const el = document.getElementById('ops-customers-table');
  if (!el) return;
  if (!customers || customers.length === 0) {
    el.innerHTML = '<div class="empty-state">No customer data.</div>';
    return;
  }

  // M2.3.1 enrichment helpers (same as M2.2.1)
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
  const _badges = c => {
    const out = [];
    if (c.is_verified === false) {
      out.push('<span class="ce-badge ce-badge-warn" title="No verified tax id — name-grouped">no-tax</span>');
    }
    if (c.name_variants_count > 1) {
      out.push(`<span class="ce-badge ce-badge-info" title="${c.name_variants_count} display name variants">${c.name_variants_count} vars</span>`);
    }
    return out.join(' ');
  };
  const _trendCell = t => {
    if (t === '▲') return '<span class="trend-up" title="Revenue rising (last 6m vs prior 6m, ≥10%)">▲</span>';
    if (t === '▼') return '<span class="trend-down" title="Revenue falling (last 6m vs prior 6m, ≥10%)">▼</span>';
    return '<span class="trend-flat" title="Revenue stable (within ±10%)">–</span>';
  };

  el.innerHTML = `
    <table class="ops-table ops-suppliers">
      <thead>
        <tr>
          <th class="num">#</th>
          <th>Customer</th>
          <th class="num">TL revenue</th>
          <th class="num">Share</th>
          <th class="num">USD invoiced</th>
          <th class="num">EUR invoiced</th>
          <th class="num">Buckets</th>
          <th class="num">Last invoice</th>
          <th class="num">Trend</th>
        </tr>
      </thead>
      <tbody>
        ${customers.map((c, i) => `
          <tr>
            <td class="num">${i+1}</td>
            <td>
              <div class="cell-supplier">
                <span class="supplier-name">${(c.customer_name || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')}</span>
                ${_badges(c) ? `<span class="supplier-badges">${_badges(c)}</span>` : ''}
              </div>
            </td>
            <td class="num">${_fmtTL(c.amount_tl)}</td>
            <td class="num">${c.share_pct != null ? c.share_pct.toFixed(2) + '%' : '—'}</td>
            <td class="num">${_fmtFx(c.amount_usd, '$')}</td>
            <td class="num">${_fmtFx(c.amount_eur, '€')}</td>
            <td class="num">${c.bucket_count}</td>
            <td class="num">${c.last_invoice_date || '—'}</td>
            <td class="num">${_trendCell(c.trend_direction)}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}'''

js = js[:fn_start] + NEW_FN + js[fn_end:]
APP_JS.write_text(js, encoding="utf-8")
print("  ✓ frontend renderer updated")

# Note: trend-up/down/flat CSS classes already added in M2.2.1.
# Same .ops-suppliers class used (visual consistency between supplier and customer tables).

print()
print("=" * 60)
print("M2.3.1 — Top Customers table enrichment complete.")
print("=" * 60)
print()
print("New columns visible:")
print("  - Share %        (customer's % of core 12m revenue)")
print("  - Last invoice   (latest invoice date)")
print("  - Trend          (▲ ▼ – : last 6m vs prior 6m, ±10%)")
print("  - Badges         (no-tax warning, name variants count)")
print()
print("Restart uvicorn to load endpoint changes:")
print("  Ctrl+C, then: python -m uvicorn dashboard.server:app --port 8000")
print()
print("Then in browser: hard-refresh (Ctrl+Shift+R) on Revenue sub-tab.")
