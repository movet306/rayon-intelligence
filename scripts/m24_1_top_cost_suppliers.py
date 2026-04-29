"""
M2.4.1 — Top Cost Suppliers table (Cost Structure Phase 1).

Backend: new endpoint /api/internal/top-cost-suppliers (reads
v_top_cost_suppliers_overall — Migration 022).

Frontend: insert table into Cost Structure sub-section under the existing
chart, with bucket display in compact single-cell format:
  - "utilities · 100%"
  - "outsourced_processing · 67% | factory_overhead · 22%"

Backups: .bak_m24_1 suffix.
"""
from pathlib import Path

SERVER = Path("dashboard/server.py")
INDEX  = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m24_1")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. Backend — new endpoint
# ─────────────────────────────────────────────────────────────────────────
print("[1/4] Adding /api/internal/top-cost-suppliers endpoint...")
text = SERVER.read_text(encoding="utf-8")

ENDPOINT_MARKER = '@app.get("/api/internal/top-cost-suppliers")'
if ENDPOINT_MARKER in text:
    print("  ⏭  endpoint already present")
else:
    backup(SERVER)

    ANCHOR = "# ── /api/internal/top-customers ───────"
    if ANCHOR not in text:
        print("  ❌ anchor not found")
        raise SystemExit(1)

    NEW_ENDPOINT = '''# ── /api/internal/top-cost-suppliers ───────────────────────────────────────
# M2.4.1 — Cost Structure Phase 1: top suppliers in cost-bucket scope
# (utilities/maintenance/packaging/factory_overhead/outsourced_processing/
# logistics_distribution). 12m rolling. Includes bucket spread (top + secondary).
@app.get("/api/internal/top-cost-suppliers")
def internal_top_cost_suppliers(
    limit: int = Query(10, ge=1, le=100),
):
    rows = _rows("""
        SELECT
            supplier_name,
            row_count,
            bucket_count,
            amount_tl::float                        AS amount_tl,
            amount_usd::float                       AS amount_usd,
            amount_eur::float                       AS amount_eur,
            top_bucket,
            top_bucket_share_pct::float             AS top_bucket_share_pct,
            secondary_bucket,
            secondary_bucket_share_pct::float       AS secondary_bucket_share_pct,
            to_char(first_invoice_date, 'YYYY-MM-DD') AS first_invoice_date,
            to_char(last_invoice_date,  'YYYY-MM-DD') AS last_invoice_date,
            share_pct::float                        AS share_pct,
            trend_direction,
            amount_tl_h1::float                     AS amount_tl_h1,
            amount_tl_h2::float                     AS amount_tl_h2,
            vergi_numarasi,
            is_verified,
            name_variants_count
        FROM v_top_cost_suppliers_overall
        ORDER BY amount_tl DESC NULLS LAST
        LIMIT %s
    """, [limit])

    return {
        "suppliers":     rows,
        "count":         len(rows),
        "window":        "last 12 months",
        "scope":         "cost buckets only (utilities, maintenance, packaging, "
                         "factory_overhead, outsourced_processing, logistics_distribution)",
    }


'''

    text = text.replace(ANCHOR, NEW_ENDPOINT + ANCHOR, 1)
    SERVER.write_text(text, encoding="utf-8")
    print("  ✓ endpoint added")


# ─────────────────────────────────────────────────────────────────────────
# 2. HTML — insert table inside Cost Structure sub-section, after chart
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/4] Inserting Top Cost Suppliers table into Cost sub-section...")
html = INDEX.read_text(encoding="utf-8")

if 'id="ops-cost-suppliers-table"' in html:
    print("  ⏭  table already present")
else:
    OLD_8 = '''<div class="ops-note" id="ops-cost-note">
          Note: <em>logistics_distribution</em> is provisional in the MVP and may include both inbound (procurement-related) and outbound (commercial) flows. To be split in M2.1.
        </div>
      </div>'''
    NEW_8 = '''<div class="ops-note" id="ops-cost-note">
          Note: <em>logistics_distribution</em> is provisional in the MVP and may include both inbound (procurement-related) and outbound (commercial) flows. To be split in M2.1.
        </div>
        <div class="table-wrap" style="margin-top:16px">
          <div class="table-title">Top 10 Cost Suppliers (last 12 months, cost buckets only)</div>
          <div id="ops-cost-suppliers-table"></div>
        </div>
      </div>'''

    OLD_6 = '''<div class="ops-note" id="ops-cost-note">
        Note: <em>logistics_distribution</em> is provisional in the MVP and may include both inbound (procurement-related) and outbound (commercial) flows. To be split in M2.1.
      </div>
    </div>'''
    NEW_6 = '''<div class="ops-note" id="ops-cost-note">
        Note: <em>logistics_distribution</em> is provisional in the MVP and may include both inbound (procurement-related) and outbound (commercial) flows. To be split in M2.1.
      </div>
      <div class="table-wrap" style="margin-top:16px">
        <div class="table-title">Top 10 Cost Suppliers (last 12 months, cost buckets only)</div>
        <div id="ops-cost-suppliers-table"></div>
      </div>
    </div>'''

    if OLD_8 in html:
        backup(INDEX)
        html = html.replace(OLD_8, NEW_8, 1)
        INDEX.write_text(html, encoding="utf-8")
        print("  ✓ table container inserted (8-space indent)")
    elif OLD_6 in html:
        backup(INDEX)
        html = html.replace(OLD_6, NEW_6, 1)
        INDEX.write_text(html, encoding="utf-8")
        print("  ✓ table container inserted (6-space indent)")
    else:
        print("  ❌ Cost note anchor not found — checking layout...")
        idx = html.find('ops-cost-note')
        if idx > 0:
            print("  Context: " + repr(html[idx-30:idx+250]))
        raise SystemExit(1)


# ─────────────────────────────────────────────────────────────────────────
# 3. JS — fetch + render
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/4] Adding fetch + render for cost suppliers table...")
js = APP_JS.read_text(encoding="utf-8")

if "renderOpsCostSuppliersTable" in js:
    print("  ⏭  renderer already present")
else:
    backup(APP_JS)

    NEW_FN = '''


/* ── Top Cost Suppliers table (M2.4.1) ────────────────────────────────── */
async function loadCostSuppliersTable() {
  try {
    const data = await api('/api/internal/top-cost-suppliers?limit=10');
    if (!data) return;
    renderOpsCostSuppliersTable(data);
  } catch (e) {
    console.error('top-cost-suppliers fetch failed', e);
  }
}

function renderOpsCostSuppliersTable(payload) {
  const suppliers = Array.isArray(payload) ? payload : (payload?.suppliers || []);
  const el = document.getElementById('ops-cost-suppliers-table');
  if (!el) return;
  if (!suppliers || suppliers.length === 0) {
    el.innerHTML = '<div class="empty-state">No cost supplier data.</div>';
    return;
  }

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
    return '<span class="trend-flat" title="Stable (within ±10%)">–</span>';
  };
  // Compact bucket spread cell:
  //   "utilities · 100%"   (when 2nd missing)
  //   "outsourced · 67% | factory_overhead · 22%"   (when 2nd present)
  const _bucketCell = s => {
    if (!s.top_bucket) return '—';
    const tb = s.top_bucket;
    const tbpct = (s.top_bucket_share_pct != null) ? s.top_bucket_share_pct.toFixed(0) + '%' : '—';
    let out = `${tb} · ${tbpct}`;
    if (s.secondary_bucket) {
      const sb = s.secondary_bucket;
      const sbpct = (s.secondary_bucket_share_pct != null) ? s.secondary_bucket_share_pct.toFixed(0) + '%' : '—';
      out += ` <span class="bucket-secondary">| ${sb} · ${sbpct}</span>`;
    }
    return out;
  };

  el.innerHTML = `
    <table class="ops-table ops-suppliers ops-cost-suppliers">
      <thead>
        <tr>
          <th class="num">#</th>
          <th>Supplier</th>
          <th class="num">TL spend</th>
          <th class="num">Share</th>
          <th>Bucket spread</th>
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
            <td class="bucket-cell">${_bucketCell(s)}</td>
            <td class="num">${s.bucket_count}</td>
            <td class="num">${s.last_invoice_date || '—'}</td>
            <td class="num">${_trendCell(s.trend_direction)}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}
'''
    js = js.rstrip() + NEW_FN
    print("  ✓ renderer + fetch fn appended")


# Wire sub-tab activation hook
WIRE_MARKER = "loadCostSuppliersTable hook"
if WIRE_MARKER in js:
    print("  ⏭  sub-tab hook already wired")
else:
    OLD_WIRE = '''      // loadCustomerConcentrationChart hook (M2.3.3)
      if (btn.dataset.sub === 'ops-revenue' && typeof loadCustomerConcentrationChart === 'function') {
        if (!window._custConcentrationLoaded) {
          loadCustomerConcentrationChart();
          window._custConcentrationLoaded = true;
        }
      }'''

    NEW_WIRE = '''      // loadCustomerConcentrationChart hook (M2.3.3)
      if (btn.dataset.sub === 'ops-revenue' && typeof loadCustomerConcentrationChart === 'function') {
        if (!window._custConcentrationLoaded) {
          loadCustomerConcentrationChart();
          window._custConcentrationLoaded = true;
        }
      }
      // loadCostSuppliersTable hook (M2.4.1)
      if (btn.dataset.sub === 'ops-cost' && typeof loadCostSuppliersTable === 'function') {
        if (!window._costSuppliersLoaded) {
          loadCostSuppliersTable();
          window._costSuppliersLoaded = true;
        }
      }'''

    if OLD_WIRE in js:
        js = js.replace(OLD_WIRE, NEW_WIRE, 1)
        print("  ✓ sub-tab activation wired to loadCostSuppliersTable")
    else:
        print("  ⚠️  Revenue concentration hook anchor not found — manual wiring may be needed")

APP_JS.write_text(js, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 4. CSS — minor styling for bucket-secondary span
# ─────────────────────────────────────────────────────────────────────────
print("\n[4/4] Adding CSS for bucket spread cell...")
CSS = Path("dashboard/static/style.v5.css")
css = CSS.read_text(encoding="utf-8")

CSS_MARKER = "/* === Cost suppliers — bucket spread (M2.4.1) === */"
if CSS_MARKER in css:
    print("  ⏭  CSS already present")
else:
    backup(CSS)
    CSS_BLOCK = '''

/* === Cost suppliers — bucket spread (M2.4.1) === */
/* Compact format inside a single table cell:                                  */
/*   "utilities · 100%"           — primary only                               */
/*   "outsourced · 67% | factory_overhead · 22%"  — primary + secondary        */
.ops-cost-suppliers .bucket-cell {
  font-size: 12.5px;
  white-space: nowrap;
  font-family: var(--font-mono, 'Inter', sans-serif);
}
.ops-cost-suppliers .bucket-secondary {
  color: var(--text-muted, #888);
  font-size: 11.5px;
  margin-left: 4px;
}
'''
    css = css.rstrip() + CSS_BLOCK
    CSS.write_text(css, encoding="utf-8")
    print("  ✓ bucket-cell CSS appended")


# ─────────────────────────────────────────────────────────────────────────
# 5. Cache buster
# ─────────────────────────────────────────────────────────────────────────
print("\n[5] Updating cache buster on app.v5.js reference...")
import re
import time as _time
html = INDEX.read_text(encoding="utf-8")
ts = _time.strftime("%Y%m%d%H%M%S")
new_html = re.sub(r'app\.v5\.js(\?[^"]*)?"', f'app.v5.js?v={ts}"', html)
if new_html != html:
    INDEX.write_text(new_html, encoding="utf-8")
    print(f"  ✓ cache buster updated to v={ts}")
else:
    print("  ⏭  no app.v5.js reference found")


print()
print("=" * 60)
print("M2.4.1 — Top Cost Suppliers table complete.")
print("=" * 60)
print()
print("Cost Structure sub-tab now has:")
print("  - Existing: Monthly cost structure chart + provisional note")
print("  - NEW:      Top 10 Cost Suppliers table with bucket spread column")
print()
print("Restart uvicorn (new endpoint added):")
print("  Ctrl+C, then: python -m uvicorn dashboard.server:app --port 8000")
print()
print("Browser: hard-refresh, Operations Intelligence > Cost Structure.")
