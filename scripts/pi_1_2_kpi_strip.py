"""
pi_1_2_kpi_strip.py - Add Price Intelligence-specific KPI strip.

Problem:
  The global header KPI strip pulls from market_signals (news table).
  When viewing Price Intelligence sub-tab, KPIs ('HIGH IMPACT 0') contradict
  the visible feed (which shows YÜKSEK signals from price_intelligence_signals).

Solution:
  1. Add a new endpoint /api/price_intelligence_stats backed by
     price_intelligence_signals (price world, not news world).
  2. Add a new in-section KPI strip rendered inside <section id="section-prices">.
  3. Hide the global header KPI strip whenever the Price Intelligence section
     is the active view.

Idempotent: re-running prints '[skip]' for each step that's already applied.

Touches three files:
  dashboard/server.py       - add /api/price_intelligence_stats endpoint
  dashboard/static/index.html - add #kpi-strip-price block + bump cache buster
  dashboard/static/app.v5.js  - add loader + visibility toggle

Touches NO database tables, NO views, NO existing endpoints, NO CSS classes.
Fully reversible via `git revert`.

KPI definitions (locked per design review):
  Action Now            = severity='high' AND last 7d AND suppressed=false
                          AND (rayon_relevance_score IS NULL OR
                               rayon_relevance_score >= 2)
                          [relevance filter is permissive while dim_material
                           is empty; activates automatically once populated.]
  Cost Pressure Up      = signal_type='COST_PRESSURE_UP' AND last 7d
                          AND suppressed=false (clusters dedup'd by chain+material)
  Cost Pressure Down    = signal_type='COST_PRESSURE_DOWN' AND last 7d
                          AND suppressed=false (clusters dedup'd by chain+material)
  Polyester FDY         = latest USD price for material='polyester_fdy'
                          (anchor benchmark — same source as global strip)
"""
from pathlib import Path
import re
import sys
import time

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "dashboard" / "server.py"
INDEX = REPO / "dashboard" / "static" / "index.html"
APPJS = REPO / "dashboard" / "static" / "app.v5.js"

# ─────────────────────────────────────────────────────────────────────────────
# 1. server.py — append new endpoint at end of file
# ─────────────────────────────────────────────────────────────────────────────

SERVER_MARKER = "# ── /api/price_intelligence_stats ─────────────────────────"
SERVER_BLOCK = '''

# ── /api/price_intelligence_stats ──────────────────────────────────────────────

@app.get("/api/price_intelligence_stats")
def price_intelligence_stats():
    """
    KPI strip data for the Price Intelligence sub-tab.

    Backed by price_intelligence_signals (chain mismatch / cost pressure / etc.),
    NOT by market_signals (news). Avoids the conceptual mismatch where the
    global header strip showed 'HIGH IMPACT 0' while the price feed showed
    YÜKSEK signals.

    Action Now uses a permissive Rayon-relevance filter that auto-activates
    once dim_material is populated in PI-2.
    """
    # 1. Action Now — high severity, last 7d, Rayon-relevant (or unscored)
    action_now = _one(
        """
        SELECT COUNT(DISTINCT (
                 signal_type, chain,
                 COALESCE(material_slug, ''),
                 COALESCE(upstream_slug, ''),
                 COALESCE(downstream_slug, '')
               ))::int AS n
        FROM price_intelligence_signals s
        LEFT JOIN dim_material m ON m.slug = s.material_slug
        WHERE s.signal_date >= NOW() - INTERVAL '7 days'
          AND s.suppressed = FALSE
          AND s.severity = 'high'
          AND (m.rayon_relevance_score IS NULL OR m.rayon_relevance_score >= 2)
        """,
    ).get("n", 0)

    # 2. Cost Pressure Up — distinct (chain, material) clusters, last 7d
    cost_up = _one(
        """
        SELECT COUNT(DISTINCT (chain, COALESCE(material_slug, '')))::int AS n
        FROM price_intelligence_signals
        WHERE signal_date >= NOW() - INTERVAL '7 days'
          AND suppressed = FALSE
          AND signal_type IN ('COST_PRESSURE_UP', 'UPSTREAM_DOWNSTREAM_DIVG',
                              'DELAYED_PASS_THROUGH_RISK')
        """,
    ).get("n", 0)

    # 3. Cost Pressure Down — distinct (chain, material) clusters, last 7d
    cost_down = _one(
        """
        SELECT COUNT(DISTINCT (chain, COALESCE(material_slug, '')))::int AS n
        FROM price_intelligence_signals
        WHERE signal_date >= NOW() - INTERVAL '7 days'
          AND suppressed = FALSE
          AND signal_type = 'COST_PRESSURE_DOWN'
        """,
    ).get("n", 0)

    # 4. Polyester FDY benchmark — latest USD spot
    poly = _one(
        """
        SELECT price_usd::float    AS price_usd,
               change_7d::float    AS change_7d
        FROM price_metrics_daily
        WHERE material = 'polyester_fdy' AND frequency = 'daily'
        ORDER BY metric_date DESC
        LIMIT 1
        """,
    )

    return {
        "action_now":          action_now,
        "cost_pressure_up":    cost_up,
        "cost_pressure_down":  cost_down,
        "polyester_fdy_usd":   poly.get("price_usd"),
        "polyester_fdy_chg7d": poly.get("change_7d"),
    }
'''

# ─────────────────────────────────────────────────────────────────────────────
# 2. index.html — add in-section KPI strip
# ─────────────────────────────────────────────────────────────────────────────

INDEX_MARKER = 'id="kpi-strip-price"'
INDEX_OLD = (
    '  <section id="section-prices" class="section">\n'
    '    <div class="section-title">Emtia Fiyat İstihbaratı</div>'
)
INDEX_NEW = (
    '  <section id="section-prices" class="section">\n'
    '    <div class="section-title">Emtia Fiyat İstihbaratı</div>\n'
    '\n'
    '    <!-- Price Intelligence specific KPI strip (PI-1.2) -->\n'
    '    <div class="kpi-strip" id="kpi-strip-price" style="margin-bottom:16px">\n'
    '      <div class="kpi-card">\n'
    '        <div class="kpi-label">Action Now (7d)</div>\n'
    '        <div class="kpi-value" id="kpi-pi-action">—</div>\n'
    '        <div class="kpi-sub">high severity · Rayon-relevant</div>\n'
    '      </div>\n'
    '      <div class="kpi-card">\n'
    '        <div class="kpi-label">Cost Pressure Up (7d)</div>\n'
    '        <div class="kpi-value" id="kpi-pi-cost-up">—</div>\n'
    '        <div class="kpi-sub">upstream / mismatch / delayed</div>\n'
    '      </div>\n'
    '      <div class="kpi-card">\n'
    '        <div class="kpi-label">Cost Pressure Down (7d)</div>\n'
    '        <div class="kpi-value" id="kpi-pi-cost-down">—</div>\n'
    '        <div class="kpi-sub">negotiation opportunity</div>\n'
    '      </div>\n'
    '      <div class="kpi-card">\n'
    '        <div class="kpi-label">Polyester FDY Benchmark</div>\n'
    '        <div class="kpi-value" id="kpi-pi-fdy">—</div>\n'
    '        <div class="kpi-sub">USD / ton · China spot</div>\n'
    '        <div class="kpi-change" id="kpi-pi-fdy-change"></div>\n'
    '      </div>\n'
    '    </div>'
)

# ─────────────────────────────────────────────────────────────────────────────
# 3. app.v5.js — add loader + global strip toggle
# ─────────────────────────────────────────────────────────────────────────────

JS_MARKER = "// PI-1.2: Price Intelligence KPI strip"
JS_BLOCK = """

// PI-1.2: Price Intelligence KPI strip
async function _loadPriceIntelStats() {
  try {
    const stats = await api('/api/price_intelligence_stats');
    setText('kpi-pi-action',     stats.action_now ?? '—');
    setText('kpi-pi-cost-up',    stats.cost_pressure_up ?? '—');
    setText('kpi-pi-cost-down',  stats.cost_pressure_down ?? '—');

    const fdyUsd = stats.polyester_fdy_usd;
    setText('kpi-pi-fdy', fdyUsd != null ? `$${Math.round(fdyUsd).toLocaleString()}` : '—');

    const chg = stats.polyester_fdy_chg7d;
    const chgEl = document.getElementById('kpi-pi-fdy-change');
    if (chgEl) {
      if (chg != null) {
        const sign = chg >= 0 ? '+' : '';
        const cls = chg >= 0 ? 'kpi-change-up' : 'kpi-change-down';
        chgEl.textContent = `${sign}${chg.toFixed(1)}% 7d`;
        chgEl.className = `kpi-change ${cls}`;
      } else {
        chgEl.textContent = '';
      }
    }
  } catch (e) {
    console.warn('Price Intelligence stats failed:', e);
  }
}

// Show/hide the global header KPI strip vs the Price Intelligence-specific one.
// Called on every section navigation.
function _togglePriceIntelKpiStrip() {
  const active = document.querySelector('section.section.active');
  const isPriceTab = active && active.id === 'section-prices';

  // Global header strip lives in <header>, has class 'kpi-strip' and no id.
  // The PI-specific one has id='kpi-strip-price'. Hide global on price tab.
  const headerStrip = document.querySelector('header .kpi-strip');
  if (headerStrip) {
    headerStrip.style.display = isPriceTab ? 'none' : '';
  }

  if (isPriceTab) _loadPriceIntelStats();
}

// Hook into existing nav-item click handlers AFTER they've fired.
document.addEventListener('click', (ev) => {
  const navItem = ev.target.closest('.nav-item[data-section]');
  if (!navItem) return;
  // Defer to next tick so the .active class swap has happened.
  setTimeout(_togglePriceIntelKpiStrip, 0);
});

// Run once on initial load to catch direct landing on Price Intelligence.
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(_togglePriceIntelKpiStrip, 100);
});
"""

# ─────────────────────────────────────────────────────────────────────────────
# Apply
# ─────────────────────────────────────────────────────────────────────────────

# 1. server.py
src = SERVER.read_text(encoding="utf-8")
if SERVER_MARKER in src:
    print("[skip] server.py already has /api/price_intelligence_stats")
else:
    SERVER.write_text(src.rstrip() + "\n" + SERVER_BLOCK + "\n", encoding="utf-8")
    print("[OK]   server.py: appended /api/price_intelligence_stats endpoint")

# 2. index.html
html = INDEX.read_text(encoding="utf-8")
if INDEX_MARKER in html:
    print("[skip] index.html already has #kpi-strip-price")
elif INDEX_OLD in html:
    html = html.replace(INDEX_OLD, INDEX_NEW)
    # bump cache buster on app.v5.js
    ts = int(time.time())
    m = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
    if m:
        old_v = m.group(1)
        html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
        print(f"[OK]   index.html: cache buster app.v5.js?v={old_v} -> ?v={ts}")
    INDEX.write_text(html, encoding="utf-8")
    print("[OK]   index.html: inserted #kpi-strip-price block")
else:
    print("[X]    index.html: could not find expected anchor for #kpi-strip-price")
    print(f"       Looked for:\n{INDEX_OLD!r}")
    sys.exit(1)

# 3. app.v5.js
js = APPJS.read_text(encoding="utf-8")
if JS_MARKER in js:
    print("[skip] app.v5.js already has _loadPriceIntelStats")
else:
    APPJS.write_text(js.rstrip() + "\n" + JS_BLOCK + "\n", encoding="utf-8")
    print("[OK]   app.v5.js: appended _loadPriceIntelStats + toggle")

print("\nDone. Next:")
print("  1. Restart dashboard:  python -m uvicorn dashboard.server:app --reload")
print("  2. Browser: Ctrl+Shift+R, navigate to Price Intelligence")
print("  3. Verify:")
print("     - new KPI strip below 'Emtia Fiyat İstihbaratı' title")
print("     - global header strip hidden on Price tab, visible on others")
print("     - Action Now should show '1' (matches diagnostic: 1 high signal)")
print("     - Cost Pressure Up should show '~3' (PTA/POY divergence + cost up)")
print("     - Cost Pressure Down should show '1' (Adipic Asit -6.5%)")
