"""
M2.2.2 — Procurement KPI strip
  - Backend: new endpoint /api/internal/procurement-kpis (reads v_procurement_kpis)
  - Frontend: HTML block + JS render + CSS
  - Layout B: anchor row (3 large) + context row (3 smaller)

Backups: .bak_m22_2 suffix
"""
from pathlib import Path
import re

SERVER = Path("dashboard/server.py")
INDEX  = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")
CSS    = Path("dashboard/static/style.v5.css")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m22_2")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. Backend — new endpoint just before /api/internal/top-suppliers
# ─────────────────────────────────────────────────────────────────────────
print("[1/4] Adding /api/internal/procurement-kpis endpoint...")
text = SERVER.read_text(encoding="utf-8")
backup(SERVER)

ENDPOINT_MARKER = "@app.get(\"/api/internal/procurement-kpis\")"
if ENDPOINT_MARKER in text:
    print("  ⏭  endpoint already present")
else:
    # Insert just before the top-suppliers endpoint comment block
    ANCHOR = "# ── /api/internal/top-suppliers ───────"
    if ANCHOR not in text:
        print("  ❌ anchor not found")
        raise SystemExit(1)

    NEW_ENDPOINT = '''# ── /api/internal/procurement-kpis ─────────────────────────────────────────
# M2.2.2 — Procurement Phase 1 KPI strip.
# Returns 6 metrics (3 anchor + 3 context) over the 12m rolling window,
# plus window metadata (latest complete month, total 12m TL).
@app.get("/api/internal/procurement-kpis")
def internal_procurement_kpis():
    rows = _rows("""
        SELECT
            top_3_supplier_share_pct::float AS top_3_supplier_share_pct,
            fx_invoiced_share_pct::float    AS fx_invoiced_share_pct,
            active_supplier_count,
            yarn_share_pct::float           AS yarn_share_pct,
            greige_share_pct::float         AS greige_share_pct,
            biggest_mover_bucket,
            biggest_mover_pct::float        AS biggest_mover_pct,
            biggest_mover_tl::float         AS biggest_mover_tl,
            latest_month,
            prior_month,
            total_12m_tl::float             AS total_12m_tl
        FROM v_procurement_kpis
    """)
    if not rows:
        return {"error": "no procurement data"}
    return rows[0]


'''

    text = text.replace(ANCHOR, NEW_ENDPOINT + ANCHOR, 1)
    SERVER.write_text(text, encoding="utf-8")
    print("  ✓ endpoint added before top-suppliers block")


# ─────────────────────────────────────────────────────────────────────────
# 2. Frontend HTML — insert KPI strip into Procurement sub-section
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/4] Inserting KPI strip into Procurement sub-section HTML...")
html = INDEX.read_text(encoding="utf-8")
backup(INDEX)

KPI_STRIP_HTML = '''<div id="ops-procurement-kpis" class="proc-kpi-strip" style="margin-bottom:16px"></div>
        '''

if 'id="ops-procurement-kpis"' in html:
    print("  ⏭  KPI strip already present")
else:
    # Find the procurement sub-section and insert KPI strip before the chart-panel
    OLD = '''<div id="sub-ops-procurement" class="sub-section">
        <div class="chart-panel" style="margin-bottom:16px">'''
    NEW = '''<div id="sub-ops-procurement" class="sub-section">
        ''' + KPI_STRIP_HTML + '''<div class="chart-panel" style="margin-bottom:16px">'''

    if OLD not in html:
        print("  ❌ procurement sub-section anchor not found")
        raise SystemExit(1)

    html = html.replace(OLD, NEW, 1)
    INDEX.write_text(html, encoding="utf-8")
    print("  ✓ KPI strip container inserted")


# ─────────────────────────────────────────────────────────────────────────
# 3. Frontend JS — fetch + render
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/4] Adding fetch + render functions to app.v5.js...")
js = APP_JS.read_text(encoding="utf-8")
backup(APP_JS)

JS_MARKER = "// === PROCUREMENT KPI STRIP (M2.2.2) ==="

if JS_MARKER in js:
    print("  ⏭  JS already patched")
else:
    JS_BLOCK = '''

// === PROCUREMENT KPI STRIP (M2.2.2) ===
async function loadProcurementKpis() {
  const el = document.getElementById('ops-procurement-kpis');
  if (!el) return;
  try {
    const data = await api('/api/internal/procurement-kpis');
    if (!data || data.error) {
      el.innerHTML = '<div class="empty-state">No procurement KPI data.</div>';
      return;
    }
    renderProcurementKpis(data);
  } catch (e) {
    console.error('procurement-kpis fetch failed', e);
    el.innerHTML = '<div class="empty-state">Failed to load KPIs.</div>';
  }
}

function renderProcurementKpis(d) {
  const el = document.getElementById('ops-procurement-kpis');

  const _fmtPct = v => (v == null || isNaN(v)) ? '—' : v.toFixed(2) + '%';
  const _fmtInt = v => (v == null || isNaN(v)) ? '—' : Number(v).toLocaleString();
  const _fmtTL = v => {
    if (v == null || isNaN(v)) return '—';
    const sign = v >= 0 ? '+' : '';
    const abs = Math.abs(v);
    if (abs >= 1e9) return sign + '₺' + (v/1e9).toFixed(1) + 'B';
    if (abs >= 1e6) return sign + '₺' + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return sign + '₺' + (v/1e3).toFixed(0) + 'K';
    return sign + '₺' + v.toFixed(0);
  };
  const _fmtPctSigned = v => {
    if (v == null || isNaN(v)) return '—';
    const sign = v >= 0 ? '+' : '';
    return sign + v.toFixed(1) + '%';
  };
  const _bucketLabel = s => (s || '—').replace(/_/g, ' ');
  const _moverClass = v => v == null ? '' : (v >= 0 ? 'mover-up' : 'mover-down');

  const moverDirection = (d.biggest_mover_tl != null && d.biggest_mover_tl >= 0) ? '▲' : '▼';

  el.innerHTML = `
    <div class="proc-kpi-row proc-kpi-anchor">
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Top 3 supplier share</div>
        <div class="proc-kpi-value">${_fmtPct(d.top_3_supplier_share_pct)}</div>
        <div class="proc-kpi-sub">of cost-relevant 12m procurement</div>
      </div>
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">FX-invoiced share</div>
        <div class="proc-kpi-value">${_fmtPct(d.fx_invoiced_share_pct)}</div>
        <div class="proc-kpi-sub">USD + EUR invoicing</div>
      </div>
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Active suppliers (12m)</div>
        <div class="proc-kpi-value">${_fmtInt(d.active_supplier_count)}</div>
        <div class="proc-kpi-sub">distinct cost-relevant</div>
      </div>
    </div>
    <div class="proc-kpi-row proc-kpi-context">
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Yarn share</div>
        <div class="proc-kpi-value-sm">${_fmtPct(d.yarn_share_pct)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Greige share</div>
        <div class="proc-kpi-value-sm">${_fmtPct(d.greige_share_pct)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Largest MoM mover (${d.latest_month || '—'} vs ${d.prior_month || '—'})</div>
        <div class="proc-kpi-value-sm ${_moverClass(d.biggest_mover_tl)}">
          ${moverDirection} ${_bucketLabel(d.biggest_mover_bucket)}
          <span class="proc-kpi-mover-detail">${_fmtPctSigned(d.biggest_mover_pct)} (${_fmtTL(d.biggest_mover_tl)})</span>
        </div>
      </div>
    </div>
  `;
}
// === END PROCUREMENT KPI STRIP ===
'''

    js = js.rstrip() + JS_BLOCK
    print("  ✓ JS functions appended")

# Wire loadProcurementKpis() into the Procurement sub-tab activation
WIRE_MARKER = "// loadProcurementKpis hook (M2.2.2)"
if WIRE_MARKER not in js:
    # Find sub-nav-btn click handler (around line 119) and add a hook for ops-procurement
    OLD_SUB_BLOCK = """      const sub = document.getElementById('sub-' + btn.dataset.sub);
      if (sub) sub.classList.add('active');
      // Counterparty Explorer hook (M2.1)"""

    NEW_SUB_BLOCK = """      const sub = document.getElementById('sub-' + btn.dataset.sub);
      if (sub) sub.classList.add('active');
      // loadProcurementKpis hook (M2.2.2)
      if (btn.dataset.sub === 'ops-procurement' && typeof loadProcurementKpis === 'function') {
        if (!window._procKpisLoaded) {
          loadProcurementKpis();
          window._procKpisLoaded = true;
        }
      }
      // Counterparty Explorer hook (M2.1)"""

    if OLD_SUB_BLOCK in js:
        js = js.replace(OLD_SUB_BLOCK, NEW_SUB_BLOCK, 1)
        print("  ✓ sub-tab activation wired to loadProcurementKpis()")
    else:
        print("  ⚠️  sub-nav handler anchor not found — wiring skipped (manual hook may be needed)")

# Also load on initial page load if Procurement sub-tab is active by default
# (it's not active by default — Overview is — so no initial-load call needed)

APP_JS.write_text(js, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 4. CSS — KPI strip styling
# ─────────────────────────────────────────────────────────────────────────
print("\n[4/4] Adding KPI strip CSS...")
css = CSS.read_text(encoding="utf-8")
backup(CSS)

CSS_MARKER = "/* === Procurement KPI strip (M2.2.2) === */"

if CSS_MARKER in css:
    print("  ⏭  CSS already patched")
else:
    CSS_BLOCK = '''

/* === Procurement KPI strip (M2.2.2) === */
.proc-kpi-strip {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.proc-kpi-row {
  display: grid;
  gap: 12px;
}
.proc-kpi-anchor {
  grid-template-columns: repeat(3, 1fr);
}
.proc-kpi-context {
  grid-template-columns: 1fr 1fr 2fr;
}
.proc-kpi-card {
  background: var(--card-bg, #1a1d2e);
  border: 1px solid var(--card-border, #2a2f45);
  border-radius: 8px;
  padding: 14px 16px;
}
.proc-kpi-large {
  padding: 18px 20px;
}
.proc-kpi-small {
  padding: 12px 14px;
}
.proc-kpi-label {
  font-size: 11px;
  color: var(--text-muted, #8a8f9e);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 6px;
}
.proc-kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary, #ffffff);
  line-height: 1.1;
}
.proc-kpi-value-sm {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #ffffff);
}
.proc-kpi-sub {
  font-size: 11px;
  color: var(--text-muted, #8a8f9e);
  margin-top: 4px;
}
.proc-kpi-mover-detail {
  display: inline-block;
  margin-left: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted, #8a8f9e);
}
.mover-up   { color: #2f9e44; }
.mover-down { color: #e03131; }
'''

    css = css.rstrip() + "\n" + CSS_BLOCK
    CSS.write_text(css, encoding="utf-8")
    print("  ✓ KPI strip styles added")


print()
print("=" * 60)
print("M2.2.2 — Procurement KPI strip complete.")
print("=" * 60)
print()
print("Layout B (anchor + context):")
print("  Anchor row:  Top 3 share | FX-invoiced share | Active suppliers")
print("  Context row: Yarn share  | Greige share      | Largest MoM mover")
print()
print("Restart uvicorn (endpoint changed):")
print("  Ctrl+C, then: python -m uvicorn dashboard.server:app --port 8000")
print()
print("Browser: hard-refresh (Ctrl+Shift+R), Operations Intelligence > Procurement.")
