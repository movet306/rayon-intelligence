"""
M2.3.2 — Revenue Phase 1 KPI strip (v2 with avg monthly revenue).

Backend: new endpoint /api/internal/revenue-kpis (reads v_revenue_kpis)
Frontend: Layout B with EXTENDED context row — 4 cards instead of 3:
          Anchor row (3): Top 3 share | FX share | Active customers
          Context row (4): Core share | Avg monthly | Contra % | Top 3 Δ

Avg monthly revenue is computed frontend-side as core_total_12m_tl / 12
(no backend change needed beyond the existing field).

Backups: .bak_m23_2 suffix.
"""
from pathlib import Path

SERVER = Path("dashboard/server.py")
INDEX  = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")
CSS    = Path("dashboard/static/style.v5.css")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m23_2")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. Backend — new endpoint
# ─────────────────────────────────────────────────────────────────────────
print("[1/5] Adding /api/internal/revenue-kpis endpoint...")
text = SERVER.read_text(encoding="utf-8")

ENDPOINT_MARKER = '@app.get("/api/internal/revenue-kpis")'
if ENDPOINT_MARKER in text:
    print("  ⏭  endpoint already present")
else:
    backup(SERVER)

    ANCHOR = "# ── /api/internal/top-customers ───────"
    if ANCHOR not in text:
        print("  ❌ anchor not found")
        raise SystemExit(1)

    NEW_ENDPOINT = '''# ── /api/internal/revenue-kpis ─────────────────────────────────────────────
# M2.3.2 — Revenue Phase 1 KPI strip.
# Returns 6+ metrics over the 12m rolling window.
# core_total_12m_tl is provided for frontend-side avg-monthly calc (÷ 12).
# KPI 6 = Top 3 customer share Δ (pp). Positive = concentration rising.
@app.get("/api/internal/revenue-kpis")
def internal_revenue_kpis():
    rows = _rows("""
        SELECT
            top_3_customer_share_pct::float AS top_3_customer_share_pct,
            fx_invoiced_share_pct::float    AS fx_invoiced_share_pct,
            active_customer_count,
            core_revenue_share_pct::float   AS core_revenue_share_pct,
            contra_share_pct::float         AS contra_share_pct,
            top_3_share_delta_pp::float     AS top_3_share_delta_pp,
            top_3_share_latest_pct::float   AS top_3_share_latest_pct,
            top_3_share_prior_pct::float    AS top_3_share_prior_pct,
            latest_month,
            prior_month,
            core_total_12m_tl::float        AS core_total_12m_tl
        FROM v_revenue_kpis
    """)
    if not rows:
        return {"error": "no revenue data"}
    return rows[0]


'''

    text = text.replace(ANCHOR, NEW_ENDPOINT + ANCHOR, 1)
    SERVER.write_text(text, encoding="utf-8")
    print("  ✓ endpoint added before top-customers")


# ─────────────────────────────────────────────────────────────────────────
# 2. HTML — insert KPI strip into Revenue sub-section
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/5] Inserting KPI strip into Revenue sub-section HTML...")
html = INDEX.read_text(encoding="utf-8")

if 'id="ops-revenue-kpis"' in html:
    print("  ⏭  KPI strip already present")
else:
    OLD_8 = '''<div id="sub-ops-revenue" class="sub-section">
        <div class="chart-panel" style="margin-bottom:16px">'''
    NEW_8 = '''<div id="sub-ops-revenue" class="sub-section">
        <div id="ops-revenue-kpis" class="proc-kpi-strip" style="margin-bottom:16px"></div>
        <div class="chart-panel" style="margin-bottom:16px">'''

    OLD_6 = '''<div id="sub-ops-revenue" class="sub-section">
      <div class="chart-panel" style="margin-bottom:16px">'''
    NEW_6 = '''<div id="sub-ops-revenue" class="sub-section">
      <div id="ops-revenue-kpis" class="proc-kpi-strip" style="margin-bottom:16px"></div>
      <div class="chart-panel" style="margin-bottom:16px">'''

    if OLD_8 in html:
        backup(INDEX)
        html = html.replace(OLD_8, NEW_8, 1)
        INDEX.write_text(html, encoding="utf-8")
        print("  ✓ KPI strip container inserted (8-space indent)")
    elif OLD_6 in html:
        backup(INDEX)
        html = html.replace(OLD_6, NEW_6, 1)
        INDEX.write_text(html, encoding="utf-8")
        print("  ✓ KPI strip container inserted (6-space indent)")
    else:
        print("  ❌ Revenue sub-section anchor not found")
        idx = html.find('sub-ops-revenue')
        if idx > 0:
            print("  Context: " + repr(html[idx-30:idx+200]))
        raise SystemExit(1)


# ─────────────────────────────────────────────────────────────────────────
# 3. JS — fetch + render functions, wire sub-tab activation
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/5] Adding fetch + render functions to app.v5.js...")
js = APP_JS.read_text(encoding="utf-8")

JS_MARKER = "// === REVENUE KPI STRIP (M2.3.2) ==="

if JS_MARKER in js:
    print("  ⏭  JS already patched")
else:
    backup(APP_JS)

    JS_BLOCK = '''


// === REVENUE KPI STRIP (M2.3.2) ===
async function loadRevenueKpis() {
  const el = document.getElementById('ops-revenue-kpis');
  if (!el) return;
  try {
    const data = await api('/api/internal/revenue-kpis');
    if (!data || data.error) {
      el.innerHTML = '<div class="empty-state">No revenue KPI data.</div>';
      return;
    }
    renderRevenueKpis(data);
  } catch (e) {
    console.error('revenue-kpis fetch failed', e);
    el.innerHTML = '<div class="empty-state">Failed to load KPIs.</div>';
  }
}

function renderRevenueKpis(d) {
  const el = document.getElementById('ops-revenue-kpis');

  const _fmtPct = v => (v == null || isNaN(v)) ? '—' : v.toFixed(2) + '%';
  const _fmtInt = v => (v == null || isNaN(v)) ? '—' : Number(v).toLocaleString();
  const _fmtPP = v => {
    if (v == null || isNaN(v)) return '—';
    const sign = v >= 0 ? '+' : '';
    return sign + v.toFixed(1) + 'pp';
  };
  const _fmtTL = v => {
    if (v == null || isNaN(v)) return '—';
    const abs = Math.abs(v);
    if (abs >= 1e9) return '₺' + (v/1e9).toFixed(2) + 'B';
    if (abs >= 1e6) return '₺' + (v/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return '₺' + (v/1e3).toFixed(0) + 'K';
    return '₺' + v.toFixed(0);
  };

  // Avg monthly revenue (frontend-computed)
  const avgMonthly = (d.core_total_12m_tl != null) ? d.core_total_12m_tl / 12 : null;

  // KPI 6: concentration shift — color INVERTED relative to Procurement.
  //   Δ positive (rising concentration)  → RED  (more risk)
  //   Δ negative (dispersing)            → GREEN (less risk)
  //   Δ small (stable)                   → muted
  const concDelta = d.top_3_share_delta_pp;
  let concClass = 'mover-flat';
  let concArrow = '–';
  if (concDelta != null) {
    if (concDelta >= 1.0) {
      concClass = 'mover-down'; // RED — concentration up = bad
      concArrow = '▲';
    } else if (concDelta <= -1.0) {
      concClass = 'mover-up';   // GREEN — concentration down = good
      concArrow = '▼';
    }
  }

  el.innerHTML = `
    <div class="proc-kpi-row proc-kpi-anchor">
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Top 3 customer share</div>
        <div class="proc-kpi-value">${_fmtPct(d.top_3_customer_share_pct)}</div>
        <div class="proc-kpi-sub">of core 12m revenue</div>
      </div>
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">FX-invoiced share</div>
        <div class="proc-kpi-value">${_fmtPct(d.fx_invoiced_share_pct)}</div>
        <div class="proc-kpi-sub">USD + EUR invoicing</div>
      </div>
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Active customers (12m)</div>
        <div class="proc-kpi-value">${_fmtInt(d.active_customer_count)}</div>
        <div class="proc-kpi-sub">distinct core customers</div>
      </div>
    </div>
    <div class="proc-kpi-row proc-kpi-context-4">
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Core revenue share</div>
        <div class="proc-kpi-value-sm">${_fmtPct(d.core_revenue_share_pct)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Avg monthly revenue</div>
        <div class="proc-kpi-value-sm">${_fmtTL(avgMonthly)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Contra share of gross</div>
        <div class="proc-kpi-value-sm">${_fmtPct(d.contra_share_pct)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Top 3 share Δ (${d.latest_month || '—'} vs ${d.prior_month || '—'})</div>
        <div class="proc-kpi-value-sm ${concClass}">
          ${concArrow} ${_fmtPP(concDelta)}
          <span class="proc-kpi-mover-detail">${_fmtPct(d.top_3_share_prior_pct)} → ${_fmtPct(d.top_3_share_latest_pct)}</span>
        </div>
      </div>
    </div>
  `;
}
// === END REVENUE KPI STRIP ===
'''

    js = js.rstrip() + JS_BLOCK
    print("  ✓ JS functions appended")

# Wire sub-tab activation hook
WIRE_MARKER = "loadRevenueKpis hook"
if WIRE_MARKER in js:
    print("  ⏭  sub-tab hook already wired")
else:
    OLD_WIRE = '''      // loadProcurementKpis hook (M2.2.2)
      if (btn.dataset.sub === 'ops-procurement' && typeof loadProcurementKpis === 'function') {
        if (!window._procKpisLoaded) {
          loadProcurementKpis();
          window._procKpisLoaded = true;
        }
      }'''

    NEW_WIRE = '''      // loadProcurementKpis hook (M2.2.2)
      if (btn.dataset.sub === 'ops-procurement' && typeof loadProcurementKpis === 'function') {
        if (!window._procKpisLoaded) {
          loadProcurementKpis();
          window._procKpisLoaded = true;
        }
      }
      // loadRevenueKpis hook (M2.3.2)
      if (btn.dataset.sub === 'ops-revenue' && typeof loadRevenueKpis === 'function') {
        if (!window._revenueKpisLoaded) {
          loadRevenueKpis();
          window._revenueKpisLoaded = true;
        }
      }'''

    if OLD_WIRE in js:
        js = js.replace(OLD_WIRE, NEW_WIRE, 1)
        print("  ✓ sub-tab activation wired to loadRevenueKpis")
    else:
        print("  ⚠️  procurement hook anchor not found — manual wiring may be needed")

APP_JS.write_text(js, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 4. CSS — add 4-column context grid variant
# ─────────────────────────────────────────────────────────────────────────
print("\n[4/5] Adding CSS for 4-card context row...")
css = CSS.read_text(encoding="utf-8")

CSS_MARKER = "/* === Revenue KPI strip (M2.3.2) — 4-card context === */"
if CSS_MARKER in css:
    print("  ⏭  CSS already present")
else:
    backup(CSS)
    CSS_BLOCK = '''

/* === Revenue KPI strip (M2.3.2) — 4-card context === */
/* Procurement uses .proc-kpi-context (3 cards). Revenue uses 4 cards.        */
/* Last card (Top 3 Δ) gets more room because it has two-line content.        */
.proc-kpi-context-4 {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1.6fr;
  gap: 12px;
}
'''
    css = css.rstrip() + CSS_BLOCK
    CSS.write_text(css, encoding="utf-8")
    print("  ✓ 4-card context CSS appended")


# ─────────────────────────────────────────────────────────────────────────
# 5. Cache buster
# ─────────────────────────────────────────────────────────────────────────
print("\n[5/5] Updating cache buster on app.v5.js reference...")
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
print("M2.3.2 — Revenue KPI strip complete (with avg monthly).")
print("=" * 60)
print()
print("Layout:")
print("  Anchor row (3): Top 3 share | FX share | Active customers")
print("  Context row (4): Core share | Avg monthly | Contra % | Top 3 Δ")
print()
print("Restart uvicorn (endpoint changed):")
print("  Ctrl+C, then: python -m uvicorn dashboard.server:app --port 8000")
print()
print("Browser: hard-refresh (cache buster auto-applied), Operations Intelligence > Revenue Reality.")
