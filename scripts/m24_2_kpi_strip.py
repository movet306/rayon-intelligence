"""
M2.4.2 — Cost Structure Phase 1 KPI strip.

Backend: new endpoint /api/internal/cost-kpis (reads v_cost_kpis — Migration 023)
Frontend: 4-card context layout (mirrors Revenue strip).
          Anchor row (3): Operating cost share | Outsourced share | Cost suppliers
          Context row (3): Maintenance share | Avg monthly cost | Cost/revenue Δ

KPI 6 = Cost/revenue ratio Δ (pp). Color INVERTED (rising ratio = margin
compression = RED, same as Revenue concentration shift).

Backups: .bak_m24_2 suffix.
"""
from pathlib import Path

SERVER = Path("dashboard/server.py")
INDEX  = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")
CSS    = Path("dashboard/static/style.v5.css")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m24_2")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. Backend — new endpoint
# ─────────────────────────────────────────────────────────────────────────
print("[1/5] Adding /api/internal/cost-kpis endpoint...")
text = SERVER.read_text(encoding="utf-8")

ENDPOINT_MARKER = '@app.get("/api/internal/cost-kpis")'
if ENDPOINT_MARKER in text:
    print("  ⏭  endpoint already present")
else:
    backup(SERVER)

    ANCHOR = "# ── /api/internal/top-cost-suppliers ───────"
    if ANCHOR not in text:
        # Try alternate anchor (top-customers) for backward compat
        ANCHOR = "# ── /api/internal/top-customers ───────"
        if ANCHOR not in text:
            print("  ❌ no anchor found")
            raise SystemExit(1)

    NEW_ENDPOINT = '''# ── /api/internal/cost-kpis ────────────────────────────────────────────────
# M2.4.2 — Cost Structure Phase 1 KPI strip.
# Returns 6 metrics over the 12m rolling window + 3m vs 3m margin trend.
# KPI 6 = cost/revenue ratio Δ (pp). Positive = margin compression.
@app.get("/api/internal/cost-kpis")
def internal_cost_kpis():
    rows = _rows("""
        SELECT
            cost_share_of_revenue_pct::float       AS cost_share_of_revenue_pct,
            outsourced_processing_share_pct::float AS outsourced_processing_share_pct,
            active_cost_supplier_count,
            maintenance_share_pct::float           AS maintenance_share_pct,
            avg_monthly_cost_tl::float             AS avg_monthly_cost_tl,
            cost_revenue_ratio_delta_pp::float     AS cost_revenue_ratio_delta_pp,
            cost_revenue_ratio_recent_pct::float   AS cost_revenue_ratio_recent_pct,
            cost_revenue_ratio_prior_pct::float    AS cost_revenue_ratio_prior_pct,
            recent_window_start,
            recent_window_end,
            prior_window_start,
            prior_window_end,
            cost_total_12m_tl::float               AS cost_total_12m_tl,
            revenue_total_12m_tl::float            AS revenue_total_12m_tl
        FROM v_cost_kpis
    """)
    if not rows:
        return {"error": "no cost data"}
    return rows[0]


'''

    text = text.replace(ANCHOR, NEW_ENDPOINT + ANCHOR, 1)
    SERVER.write_text(text, encoding="utf-8")
    print("  ✓ endpoint added")


# ─────────────────────────────────────────────────────────────────────────
# 2. HTML — insert KPI strip into Cost sub-section, before chart
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/5] Inserting KPI strip into Cost sub-section HTML...")
html = INDEX.read_text(encoding="utf-8")

if 'id="ops-cost-kpis"' in html:
    print("  ⏭  KPI strip already present")
else:
    OLD_8 = '''<div id="sub-ops-cost" class="sub-section">
        <div class="chart-panel">'''
    NEW_8 = '''<div id="sub-ops-cost" class="sub-section">
        <div id="ops-cost-kpis" class="proc-kpi-strip" style="margin-bottom:16px"></div>
        <div class="chart-panel">'''

    OLD_6 = '''<div id="sub-ops-cost" class="sub-section">
      <div class="chart-panel">'''
    NEW_6 = '''<div id="sub-ops-cost" class="sub-section">
      <div id="ops-cost-kpis" class="proc-kpi-strip" style="margin-bottom:16px"></div>
      <div class="chart-panel">'''

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
        print("  ❌ Cost sub-section anchor not found")
        idx = html.find('sub-ops-cost')
        if idx > 0:
            print("  Context: " + repr(html[idx-30:idx+200]))
        raise SystemExit(1)


# ─────────────────────────────────────────────────────────────────────────
# 3. JS — fetch + render
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/5] Adding fetch + render for cost KPI strip...")
js = APP_JS.read_text(encoding="utf-8")

JS_MARKER = "// === COST KPI STRIP (M2.4.2) ==="

if JS_MARKER in js:
    print("  ⏭  JS already patched")
else:
    backup(APP_JS)

    JS_BLOCK = '''


// === COST KPI STRIP (M2.4.2) ===
async function loadCostKpis() {
  const el = document.getElementById('ops-cost-kpis');
  if (!el) return;
  try {
    const data = await api('/api/internal/cost-kpis');
    if (!data || data.error) {
      el.innerHTML = '<div class="empty-state">No cost KPI data.</div>';
      return;
    }
    renderCostKpis(data);
  } catch (e) {
    console.error('cost-kpis fetch failed', e);
    el.innerHTML = '<div class="empty-state">Failed to load KPIs.</div>';
  }
}

function renderCostKpis(d) {
  const el = document.getElementById('ops-cost-kpis');

  const _fmtPct = v => (v == null || isNaN(v)) ? '—' : v.toFixed(2) + '%';
  const _fmtPctSm = v => (v == null || isNaN(v)) ? '—' : v.toFixed(1) + '%';
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

  // KPI 6: cost/revenue ratio shift — color INVERTED.
  //   Δ positive (ratio up = margin compression) → RED  (bad)
  //   Δ negative (ratio down = margin expansion) → GREEN (good)
  //   Δ small (stable)                          → muted
  const ratioDelta = d.cost_revenue_ratio_delta_pp;
  let ratioClass = 'mover-flat';
  let ratioArrow = '–';
  if (ratioDelta != null) {
    if (ratioDelta >= 0.5) {
      ratioClass = 'mover-down'; // RED — margin compression
      ratioArrow = '▲';
    } else if (ratioDelta <= -0.5) {
      ratioClass = 'mover-up';   // GREEN — margin expansion
      ratioArrow = '▼';
    }
  }

  // 3m window labels (e.g. "2026-01—2026-03 vs 2025-10—2025-12")
  const recentLabel = (d.recent_window_start && d.recent_window_end)
    ? `${d.recent_window_start}—${d.recent_window_end}`
    : '—';
  const priorLabel = (d.prior_window_start && d.prior_window_end)
    ? `${d.prior_window_start}—${d.prior_window_end}`
    : '—';

  el.innerHTML = `
    <div class="proc-kpi-row proc-kpi-anchor">
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Operating cost share of revenue</div>
        <div class="proc-kpi-value">${_fmtPct(d.cost_share_of_revenue_pct)}</div>
        <div class="proc-kpi-sub">excludes raw materials (in Procurement)</div>
      </div>
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Outsourced processing share</div>
        <div class="proc-kpi-value">${_fmtPct(d.outsourced_processing_share_pct)}</div>
        <div class="proc-kpi-sub">of total operating cost</div>
      </div>
      <div class="proc-kpi-card proc-kpi-large">
        <div class="proc-kpi-label">Active cost suppliers (12m)</div>
        <div class="proc-kpi-value">${_fmtInt(d.active_cost_supplier_count)}</div>
        <div class="proc-kpi-sub">distinct, cost scope only</div>
      </div>
    </div>
    <div class="proc-kpi-row proc-kpi-context-3">
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Maintenance share</div>
        <div class="proc-kpi-value-sm">${_fmtPct(d.maintenance_share_pct)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Avg monthly cost</div>
        <div class="proc-kpi-value-sm">${_fmtTL(d.avg_monthly_cost_tl)}</div>
      </div>
      <div class="proc-kpi-card proc-kpi-small">
        <div class="proc-kpi-label">Cost/revenue Δ (${recentLabel} vs ${priorLabel})</div>
        <div class="proc-kpi-value-sm ${ratioClass}">
          ${ratioArrow} ${_fmtPP(ratioDelta)}
          <span class="proc-kpi-mover-detail">${_fmtPctSm(d.cost_revenue_ratio_prior_pct)} → ${_fmtPctSm(d.cost_revenue_ratio_recent_pct)}</span>
        </div>
      </div>
    </div>
  `;
}
// === END COST KPI STRIP ===
'''

    js = js.rstrip() + JS_BLOCK
    print("  ✓ JS functions appended")

# Wire sub-tab activation hook
WIRE_MARKER = "loadCostKpis hook"
if WIRE_MARKER in js:
    print("  ⏭  sub-tab hook already wired")
else:
    OLD_WIRE = '''      // loadCostSuppliersTable hook (M2.4.1)
      if (btn.dataset.sub === 'ops-cost' && typeof loadCostSuppliersTable === 'function') {
        if (!window._costSuppliersLoaded) {
          loadCostSuppliersTable();
          window._costSuppliersLoaded = true;
        }
      }'''

    NEW_WIRE = '''      // loadCostSuppliersTable hook (M2.4.1)
      if (btn.dataset.sub === 'ops-cost' && typeof loadCostSuppliersTable === 'function') {
        if (!window._costSuppliersLoaded) {
          loadCostSuppliersTable();
          window._costSuppliersLoaded = true;
        }
      }
      // loadCostKpis hook (M2.4.2)
      if (btn.dataset.sub === 'ops-cost' && typeof loadCostKpis === 'function') {
        if (!window._costKpisLoaded) {
          loadCostKpis();
          window._costKpisLoaded = true;
        }
      }'''

    if OLD_WIRE in js:
        js = js.replace(OLD_WIRE, NEW_WIRE, 1)
        print("  ✓ sub-tab activation wired to loadCostKpis")
    else:
        print("  ⚠️  Cost suppliers hook anchor not found — manual wiring may be needed")

APP_JS.write_text(js, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 4. CSS — 3-card context grid (proc-kpi-context-3)
# ─────────────────────────────────────────────────────────────────────────
print("\n[4/5] Adding CSS for 3-card context row...")
css = CSS.read_text(encoding="utf-8")

CSS_MARKER = "/* === Cost KPI strip (M2.4.2) — 3-card context === */"
if CSS_MARKER in css:
    print("  ⏭  CSS already present")
else:
    backup(CSS)
    CSS_BLOCK = '''

/* === Cost KPI strip (M2.4.2) — 3-card context === */
/* Cost has 3 context cards (no avg-monthly + 4-card layout like Revenue).    */
/* Last card (Cost/revenue Δ) gets more room because it has two-line content. */
.proc-kpi-context-3 {
  display: grid;
  grid-template-columns: 1fr 1fr 1.6fr;
  gap: 12px;
}
'''
    css = css.rstrip() + CSS_BLOCK
    CSS.write_text(css, encoding="utf-8")
    print("  ✓ 3-card context CSS appended")


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
print("M2.4.2 — Cost KPI strip complete.")
print("=" * 60)
print()
print("Layout:")
print("  Anchor row (3): Operating cost share | Outsourced share | Cost suppliers")
print("  Context row (3): Maintenance share | Avg monthly cost | Cost/revenue Δ")
print()
print("Color semantics for KPI 6 (cost/revenue ratio shift):")
print("  ▲ red   = ratio RISING  = margin compression (bad)")
print("  ▼ green = ratio FALLING = margin expansion (good)")
print("  – muted = stable")
print()
print("Restart uvicorn (endpoint changed):")
print("  Ctrl+C, then: python -m uvicorn dashboard.server:app --port 8000")
print()
print("Browser: hard-refresh, Operations Intelligence > Cost Structure.")
