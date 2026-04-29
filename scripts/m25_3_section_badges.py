"""
M2.5.3 — Section health badges (Overview Phase 1 final).

Frontend-only. Reuses overview-signals payload that loadOverviewSignals
already fetched. Each section header (PROCUREMENT / COST STRUCTURE /
REVENUE REALITY) gets:
  - a colored dot reflecting health (red/amber/green)
  - hover state + click handler that switches to the corresponding sub-tab

Health rollup:
  Procurement   = slot 'procurement_concentration' severity
  Cost          = slot 'margin_trend' severity
  Revenue       = WORST of (customer_concentration, contra_revenue)

Backups: .bak_m25_3 suffix.
"""
from pathlib import Path

APP_JS = Path("dashboard/static/app.v5.js")
INDEX  = Path("dashboard/static/index.html")
CSS    = Path("dashboard/static/style.v5.css")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m25_3")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. HTML — convert the static section title divs to identified containers
# ─────────────────────────────────────────────────────────────────────────
print("[1/4] Adding identifiers to section title divs in Overview HTML...")
html = INDEX.read_text(encoding="utf-8")

# Each section title is a `<div class="ops-panel-title">Procurement</div>` etc.
# We rewrite each one with an id so the JS can attach the badge + click target.

# Procurement
OLD_PROC = '<div class="ops-panel-title">Procurement</div>'
NEW_PROC = '<div class="ops-panel-title ops-section-header" id="ops-section-header-procurement" data-target="ops-procurement">Procurement</div>'

# Cost Structure
OLD_COST = '<div class="ops-panel-title">Cost Structure</div>'
NEW_COST = '<div class="ops-panel-title ops-section-header" id="ops-section-header-cost" data-target="ops-cost">Cost Structure</div>'

# Revenue Reality
OLD_REV = '<div class="ops-panel-title">Revenue Reality</div>'
NEW_REV = '<div class="ops-panel-title ops-section-header" id="ops-section-header-revenue" data-target="ops-revenue">Revenue Reality</div>'

patched = 0
for old, new, label in [
    (OLD_PROC, NEW_PROC, "Procurement"),
    (OLD_COST, NEW_COST, "Cost Structure"),
    (OLD_REV,  NEW_REV,  "Revenue Reality"),
]:
    if new in html:
        print(f"  ⏭  {label} header already patched")
    elif old not in html:
        print(f"  ❌ {label} header anchor not found: {old}")
        raise SystemExit(1)
    else:
        if patched == 0:
            backup(INDEX)
        html = html.replace(old, new, 1)
        patched += 1
        print(f"  ✓ {label} header now identified")

if patched > 0:
    INDEX.write_text(html, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 2. JS — extend renderOverviewSignals to also paint section badges
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/4] Adding renderSectionHealthBadges to app.v5.js...")
js = APP_JS.read_text(encoding="utf-8")

if "renderSectionHealthBadges" in js:
    print("  ⏭  badges renderer already present")
else:
    backup(APP_JS)

    NEW_FN = '''


/* ── Section health badges (M2.5.3) ──────────────────────────────────── */
/* Rolls up the overview-signals payload into one severity per section,   */
/* paints a dot on each section header, and wires the header to switch    */
/* to the corresponding sub-tab on click.                                 */
function renderSectionHealthBadges(signalsPayload) {
  const signals = signalsPayload?.signals || [];
  if (!signals.length) return;

  const bySlot = {};
  signals.forEach(s => { bySlot[s.signal_key] = s; });

  // Severity weight (higher = worse)
  const sevRank = { critical: 3, warning: 2, ok: 1, info: 1 };
  const _worst = (...keys) => {
    let worst = 'ok';
    keys.forEach(k => {
      const sev = bySlot[k]?.severity || 'ok';
      if ((sevRank[sev] || 0) > (sevRank[worst] || 0)) worst = sev;
    });
    return worst;
  };

  const sectionHealth = {
    procurement: _worst('procurement_concentration'),
    cost:        _worst('margin_trend'),
    revenue:     _worst('customer_concentration', 'contra_revenue'),
  };

  const _paintHeader = (id, severity) => {
    const el = document.getElementById(id);
    if (!el) return;
    // Reset previous severity classes
    el.classList.remove('section-health-critical', 'section-health-warning', 'section-health-ok');
    el.classList.add(`section-health-${severity}`);

    // Inject (or refresh) the dot + chevron decorations.
    // We rebuild the inner content each call so re-renders don't stack badges.
    const labelText = el.dataset.labelText || el.textContent.trim();
    el.dataset.labelText = labelText;
    el.innerHTML = `
      <span class="section-health-dot" aria-hidden="true"></span>
      <span class="section-health-label">${labelText}</span>
      <span class="section-health-chevron" aria-hidden="true">→</span>
    `;

    // Click handler — navigate to the matching sub-tab.
    if (!el.dataset.clickWired) {
      el.style.cursor = 'pointer';
      el.addEventListener('click', () => {
        const target = el.dataset.target;
        if (!target) return;
        const btn = document.querySelector(`.sub-tabs [data-sub="${target}"]`);
        if (btn) btn.click();
      });
      el.dataset.clickWired = '1';
    }
  };

  _paintHeader('ops-section-header-procurement', sectionHealth.procurement);
  _paintHeader('ops-section-header-cost',        sectionHealth.cost);
  _paintHeader('ops-section-header-revenue',     sectionHealth.revenue);
}
'''

    js = js.rstrip() + NEW_FN
    print("  ✓ renderSectionHealthBadges appended")

# Wire into renderOverviewSignals so badges paint right after the strip.
HOOK_MARKER = "renderSectionHealthBadges call inside renderOverviewSignals"
if HOOK_MARKER in js:
    print("  ⏭  renderOverviewSignals hook already wired")
else:
    OLD_HOOK = '''  el.innerHTML = signals.map(s => `
    <div class="signal-card signal-${s.severity || 'ok'}">'''
    NEW_HOOK = '''  // Paint section health badges from the same payload (M2.5.3)
  if (typeof renderSectionHealthBadges === 'function') {
    renderSectionHealthBadges(payload); // renderSectionHealthBadges call inside renderOverviewSignals
  }

  el.innerHTML = signals.map(s => `
    <div class="signal-card signal-${s.severity || 'ok'}">'''

    if OLD_HOOK in js:
        js = js.replace(OLD_HOOK, NEW_HOOK, 1)
        print("  ✓ renderOverviewSignals now triggers section health badges")
    else:
        print("  ⚠️  renderOverviewSignals anchor not found — manual wiring may be needed")

APP_JS.write_text(js, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 3. CSS — section header badge styling
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/4] Adding CSS for section health badges...")
css = CSS.read_text(encoding="utf-8")

CSS_MARKER = "/* === Section health badges (M2.5.3) === */"
if CSS_MARKER in css:
    print("  ⏭  CSS already present")
else:
    backup(CSS)
    CSS_BLOCK = '''

/* === Section health badges (M2.5.3) === */
/* Each .ops-section-header gets: colored dot + label + chevron, with     */
/* hover affordance and click-to-navigate behaviour wired in JS.          */
.ops-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: color 0.12s ease;
  user-select: none;
}
.ops-section-header:hover {
  color: var(--text-primary, #fff);
}
.section-health-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #868e96;             /* default muted */
  flex-shrink: 0;
  display: inline-block;
}
.section-health-critical .section-health-dot { background: #e03131; box-shadow: 0 0 6px rgba(224,49,49,0.45); }
.section-health-warning  .section-health-dot { background: #f59f00; box-shadow: 0 0 6px rgba(245,159,0,0.40); }
.section-health-ok       .section-health-dot { background: #2f9e44; box-shadow: 0 0 6px rgba(47,158,68,0.35); }

.section-health-label {
  font-weight: 500;
}

.section-health-chevron {
  margin-left: 6px;
  opacity: 0.4;
  font-size: 12px;
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.ops-section-header:hover .section-health-chevron {
  opacity: 0.85;
  transform: translateX(2px);
}
'''
    css = css.rstrip() + CSS_BLOCK
    CSS.write_text(css, encoding="utf-8")
    print("  ✓ section health CSS appended")


# ─────────────────────────────────────────────────────────────────────────
# 4. Cache buster
# ─────────────────────────────────────────────────────────────────────────
print("\n[4/4] Updating cache buster on app.v5.js reference...")
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
print("M2.5.3 — Section health badges complete.")
print("=" * 60)
print()
print("Each section header on Overview now shows:")
print("  - a colored dot (red/amber/green) reflecting that section's health")
print("  - a chevron arrow that gets emphasized on hover")
print("  - on click, navigates to the corresponding sub-tab")
print()
print("Health rollup (frontend-side):")
print("  Procurement = procurement_concentration severity")
print("  Cost        = margin_trend severity")
print("  Revenue     = worst of (customer_concentration, contra_revenue)")
print()
print("No backend / no uvicorn restart needed (frontend-only).")
print("Browser: hard-refresh, Operations Intelligence > Overview.")
