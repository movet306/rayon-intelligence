"""
M2.1 v1.1 — Narrow bug-confidence pass for Counterparty Explorer.

Four fixes only:
  1. Fix lingering "Loading..." title (JS render order)
  2. Strip .0 suffix from tax ids everywhere they're displayed
  3. Make currency labels explicit:
       - "USD invoiced (original currency)"
       - "EUR invoiced (original currency)"
       - main TL stays as "24m TL"
  4. Surface ALIŞ/SATIŞ mode in the detail panel + rename bucket split
       - "Mode: Supplier (ALIŞ)" / "Mode: Customer (SATIŞ)" badge
       - "Purchase-side bucket split" / "Sales-side bucket split"

Backups: .bak_m21_v1_1 suffix.
"""
from pathlib import Path

APP_JS = Path("dashboard/static/app.v5.js")
INDEX = Path("dashboard/static/index.html")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m21_v1_1")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# Fix 1+2+3+4 (JS) — replace ceRenderDetail, fmtTL, list rendering
# ─────────────────────────────────────────────────────────────────────────
print("[1/2] Patching app.v5.js...")
js = APP_JS.read_text(encoding="utf-8")
backup(APP_JS)


# ── Helper: stripTaxZero ──────────────────────────────────────────────────
HELPER_MARKER = "// stripTaxZero (M2.1 v1.1)"
HELPER_FN = '''
// stripTaxZero (M2.1 v1.1)
function stripTaxZero(v) {
  if (v == null) return '';
  let s = String(v).trim();
  if (s.endsWith('.0')) s = s.slice(0, -2);
  return s;
}
'''

if HELPER_MARKER not in js:
    # Insert near the other ce* helpers (before escapeHtml)
    js = js.replace("function escapeHtml(s) {", HELPER_FN + "\nfunction escapeHtml(s) {", 1)
    print("  ✓ added stripTaxZero helper")
else:
    print("  ⏭  stripTaxZero already present")


# ── Fix list rendering: strip .0 from vergi_numarasi display ──────────────
OLD_VN_DISPLAY = '${item.vergi_numarasi ? `<div class="ce-li-tax">vn: ${item.vergi_numarasi}</div>` : \'\'}'
NEW_VN_DISPLAY = '${item.vergi_numarasi ? `<div class="ce-li-tax">vn: ${stripTaxZero(item.vergi_numarasi)}</div>` : \'\'}'
if OLD_VN_DISPLAY in js:
    js = js.replace(OLD_VN_DISPLAY, NEW_VN_DISPLAY, 1)
    print("  ✓ list .0 strip")
else:
    print("  ⏭  list vn template already patched or missing")


# ── Replace ceRenderDetail with a hardened version ────────────────────────
# Strategy: locate the function and replace the whole body until the next
# top-level function. We use sentinel markers if available, else regex.

import re
new_render = '''function ceRenderDetail(d) {
  // Fix 1: clear any lingering "Loading…" title with the actual name
  document.getElementById('ce-detail-name').textContent = d.display_name || '<unknown>';

  // Fix 4: explicit mode badge (Supplier/Customer)
  const modeLabel = (d.side === 'purchase')
    ? 'Mode: Supplier (ALIŞ)'
    : 'Mode: Customer (SATIŞ)';

  // Badges (mode + verification + name drift + counterparty type)
  const badgesEl = document.getElementById('ce-detail-badges');
  const bd = [];
  bd.push(`<span class="ce-badge ce-badge-mode">${modeLabel}</span>`);
  if (!d.is_verified) bd.push('<span class="ce-badge ce-badge-warn">tax id missing · name-grouped</span>');
  if (d.name_variants_count > 1) bd.push(`<span class="ce-badge ce-badge-info">${d.name_variants_count} name variants</span>`);
  if (d.counterparty_type) bd.push(`<span class="ce-badge ce-badge-neutral">${d.counterparty_type}</span>`);
  badgesEl.innerHTML = bd.join(' ');

  // Fix 2: meta line — strip .0 from tax id
  const metaEl = document.getElementById('ce-detail-meta');
  metaEl.innerHTML = `
    <div class="ce-meta-row"><span>Tax id:</span> <strong>${stripTaxZero(d.vergi_numarasi) || '—'}</strong></div>
    <div class="ce-meta-row"><span>Window:</span> <strong>${d.months}m</strong> ending ${d.data_horizon || '—'}</div>
    <div class="ce-meta-row"><span>First invoice:</span> <strong>${d.summary.first_invoice || '—'}</strong></div>
  `;

  // Summary KPIs
  document.getElementById('ce-stat-tl').textContent = ceFmtTL(d.summary.total_tl);
  document.getElementById('ce-stat-usd').textContent = d.summary.total_usd ? '$' + ceFmtNum(d.summary.total_usd) : '—';
  document.getElementById('ce-stat-eur').textContent = d.summary.total_eur ? '€' + ceFmtNum(d.summary.total_eur) : '—';
  document.getElementById('ce-stat-rows').textContent = d.summary.row_count.toLocaleString();
  document.getElementById('ce-stat-share').textContent = d.summary.share_of_total_pct.toFixed(2) + '%';
  document.getElementById('ce-stat-last').textContent = d.summary.last_invoice || '—';

  // Fix 3: relabel KPI tiles to be unambiguous
  const tlLabel = document.querySelector('#ce-stat-tl')?.parentElement?.querySelector('.ce-stat-label');
  const usdLabel = document.querySelector('#ce-stat-usd')?.parentElement?.querySelector('.ce-stat-label');
  const eurLabel = document.querySelector('#ce-stat-eur')?.parentElement?.querySelector('.ce-stat-label');
  if (tlLabel)  tlLabel.textContent  = `${d.months}m TL (all rows)`;
  if (usdLabel) usdLabel.textContent = `${d.months}m USD invoiced (orig. ccy)`;
  if (eurLabel) eurLabel.textContent = `${d.months}m EUR invoiced (orig. ccy)`;

  // Fix 4: bucket split heading reflects mode
  const bucketHeading = document.querySelector('#ce-bucket-table')?.closest('.ce-block')?.querySelector('h4');
  if (bucketHeading) {
    bucketHeading.textContent = (d.side === 'purchase')
      ? 'Purchase-side bucket split'
      : 'Sales-side bucket split';
  }

  // Monthly trend
  ceRenderMonthlyChart(d.monthly_trend);

  // Bucket table
  const bbody = document.querySelector('#ce-bucket-table tbody');
  bbody.innerHTML = '';
  d.bucket_split.forEach(b => {
    bbody.innerHTML += `<tr><td>${escapeHtml(b.bucket || '<null>')}</td><td class="num">${ceFmtTL(b.amount_tl)}</td><td class="num">${b.share_pct}%</td><td class="num">${b.rows}</td></tr>`;
  });

  // Currency split — note the "TL equivalent" semantics in the column header
  const ccyHeading = document.querySelector('#ce-ccy-table thead tr');
  if (ccyHeading) {
    ccyHeading.innerHTML = '<th>Original ccy</th><th class="num">TL equivalent</th><th class="num">Rows</th>';
  }
  const cbody = document.querySelector('#ce-ccy-table tbody');
  cbody.innerHTML = '';
  d.currency_split.forEach(c => {
    cbody.innerHTML += `<tr><td>${escapeHtml(c.ccy)}</td><td class="num">${ceFmtTL(c.amount_tl)}</td><td class="num">${c.rows}</td></tr>`;
  });

  // Top accounts
  const abody = document.querySelector('#ce-accounts-table tbody');
  abody.innerHTML = '';
  d.top_accounts.forEach(a => {
    abody.innerHTML += `<tr><td><code>${escapeHtml(a.hesap_kodu || '')}</code></td><td>${escapeHtml((a.hesap_aciklamasi || '').slice(0, 40))}</td><td class="num">${ceFmtTL(a.amount_tl)}</td><td class="num">${a.rows}</td></tr>`;
  });

  // Subtype
  const sbody = document.querySelector('#ce-subtype-table tbody');
  sbody.innerHTML = '';
  if (d.subtype_split.length === 0) {
    sbody.innerHTML = '<tr><td colspan="3" class="ce-empty-cell">No subtype data</td></tr>';
  } else {
    d.subtype_split.forEach(s => {
      sbody.innerHTML += `<tr><td>${escapeHtml(s.subtype || '')}</td><td class="num">${ceFmtTL(s.amount_tl)}</td><td class="num">${s.rows}</td></tr>`;
    });
  }

  // Quality strip
  const q = d.classification_quality;
  document.getElementById('ce-quality').innerHTML = `
    <div class="ce-quality-cell"><span class="ce-q-label">High confidence:</span> <strong>${q.confidence_high_pct}%</strong></div>
    <div class="ce-quality-cell"><span class="ce-q-label">Review-flagged:</span> <strong>${q.review_flagged_pct}%</strong></div>
  `;

  // Recent rows
  const rbody = document.querySelector('#ce-recent-table tbody');
  rbody.innerHTML = '';
  d.recent_rows.forEach(r => {
    rbody.innerHTML += `<tr><td>${r.fatura_tarihi || '—'}</td><td><code>${escapeHtml(r.hesap_kodu || '')}</code></td><td>${escapeHtml(r.bucket || '')}</td><td class="num">${ceFmtTL(r.amount_tl)}</td><td>${escapeHtml(r.ccy || '')}</td></tr>`;
  });
}'''

# Replace by finding "function ceRenderDetail(d) {" and matching to the closing brace
pattern = re.compile(
    r'function ceRenderDetail\(d\) \{.*?\n\}\n',
    re.DOTALL
)
m = pattern.search(js)
if not m:
    print("  ❌ ceRenderDetail not found")
    raise SystemExit(1)

# Sanity check: don't replace if our marker is already inside
if "Mode: Supplier (ALIŞ)" in m.group(0):
    print("  ⏭  ceRenderDetail already patched")
else:
    js = js[:m.start()] + new_render + "\n" + js[m.end():]
    print("  ✓ ceRenderDetail rewritten with all four fixes")

APP_JS.write_text(js, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# Fix 5 (CSS for new mode badge) — add to inline style block in JS or via index.html style
# Quick path: append a tiny CSS block at the end of style.v5.css
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/2] Patching style.v5.css...")
CSS = Path("dashboard/static/style.v5.css")
css = CSS.read_text(encoding="utf-8")

CSS_MARKER = "/* === CE mode badge (M2.1 v1.1) === */"
CSS_BLOCK = '''

/* === CE mode badge (M2.1 v1.1) === */
.ce-badge-mode {
  background: #e7f5ff;
  color: #0c5b8a;
  border: 1px solid #74c0fc;
  font-weight: 600;
}
'''

if CSS_MARKER not in css:
    backup(CSS)
    css = css.rstrip() + "\n" + CSS_BLOCK
    CSS.write_text(css, encoding="utf-8")
    print("  ✓ added .ce-badge-mode style")
else:
    print("  ⏭  CE mode badge style already present")


print()
print("=" * 60)
print("Bug-confidence pass complete (M2.1 v1.1).")
print("=" * 60)
print()
print("Fixes applied:")
print("  1. ✓ Loading title now updates with actual display_name")
print("  2. ✓ Tax id .0 suffix stripped in list + detail meta")
print("  3. ✓ Currency labels: '24m USD invoiced (orig. ccy)' etc.")
print("  4. ✓ Mode badge: 'Mode: Supplier (ALIŞ)' / 'Customer (SATIŞ)'")
print("  4b ✓ Bucket split heading: Purchase-side / Sales-side")
print("  4c ✓ Currency table header: 'Original ccy' / 'TL equivalent'")
print()
print("Next:")
print("  1. uvicorn auto-serves static — just hard-refresh (Ctrl+Shift+R)")
print("  2. Click Operations Intelligence → Counterparty")
print("  3. Click EKİN DOKUMA (purchase mode) — check mode badge & labels")
print("  4. Switch to SATIŞ — click LESCON — confirm everything reads cleanly")
print()
print("Stopping here. Tomorrow: drill-down + narrative layers.")
