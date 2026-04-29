"""
M2.5.1 — Overview Phase 1 Top Signals strip.

Backend: new endpoint /api/internal/overview-signals (reads v_overview_signals
        — Migration 026)
Frontend: 4-card strip inserted at the TOP of the Overview sub-section, above
          the existing KPI wall. Each card has:
            - severity color (critical=red / warning=amber / ok=green)
            - title
            - metric_text (1 metric)
            - why_text (1 reason line)

Backups: .bak_m25_1 suffix.
"""
from pathlib import Path

SERVER = Path("dashboard/server.py")
INDEX  = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")
CSS    = Path("dashboard/static/style.v5.css")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m25_1")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. Backend — new endpoint
# ─────────────────────────────────────────────────────────────────────────
print("[1/5] Adding /api/internal/overview-signals endpoint...")
text = SERVER.read_text(encoding="utf-8")

ENDPOINT_MARKER = '@app.get("/api/internal/overview-signals")'
if ENDPOINT_MARKER in text:
    print("  ⏭  endpoint already present")
else:
    backup(SERVER)

    # Insert before kpi-latest-month (it's the de-facto Overview endpoint)
    ANCHOR = '@app.get("/api/internal/kpi-latest-month")'
    if ANCHOR not in text:
        print("  ❌ anchor not found")
        raise SystemExit(1)

    NEW_ENDPOINT = '''@app.get("/api/internal/overview-signals")
def internal_overview_signals():
    """
    M2.5.1 — Overview Phase 1 top-signals strip.
    Returns 4 fixed slots: customer_concentration, procurement_concentration,
    contra_revenue, margin_trend. Severity is rule-based (see migration 026).
    """
    rows = _rows("""
        SELECT
            display_order,
            signal_key,
            severity,
            title,
            metric_text,
            why_text
        FROM v_overview_signals
        ORDER BY display_order
    """)
    return {"signals": rows}


'''

    text = text.replace(ANCHOR, NEW_ENDPOINT + ANCHOR, 1)
    SERVER.write_text(text, encoding="utf-8")
    print("  ✓ endpoint added before kpi-latest-month")


# ─────────────────────────────────────────────────────────────────────────
# 2. HTML — insert signals strip at the top of Overview sub-section
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/5] Inserting signals strip at top of Overview sub-section...")
html = INDEX.read_text(encoding="utf-8")

if 'id="ops-signals-strip"' in html:
    print("  ⏭  signals strip already present")
else:
    # Anchor: just inside <div id="sub-ops-overview" class="sub-section active">
    OLD_8 = '''<div id="sub-ops-overview" class="sub-section active">
        <div class="ops-period-header" id="ops-period-header"></div>'''
    NEW_8 = '''<div id="sub-ops-overview" class="sub-section active">
        <div id="ops-signals-strip" class="signals-strip" style="margin-bottom:16px"></div>
        <div class="ops-period-header" id="ops-period-header"></div>'''

    OLD_6 = '''<div id="sub-ops-overview" class="sub-section active">
      <div class="ops-period-header" id="ops-period-header"></div>'''
    NEW_6 = '''<div id="sub-ops-overview" class="sub-section active">
      <div id="ops-signals-strip" class="signals-strip" style="margin-bottom:16px"></div>
      <div class="ops-period-header" id="ops-period-header"></div>'''

    if OLD_8 in html:
        backup(INDEX)
        html = html.replace(OLD_8, NEW_8, 1)
        INDEX.write_text(html, encoding="utf-8")
        print("  ✓ signals strip container inserted (8-space indent)")
    elif OLD_6 in html:
        backup(INDEX)
        html = html.replace(OLD_6, NEW_6, 1)
        INDEX.write_text(html, encoding="utf-8")
        print("  ✓ signals strip container inserted (6-space indent)")
    else:
        print("  ❌ Overview sub-section anchor not found")
        idx = html.find('sub-ops-overview')
        if idx > 0:
            print("  Context: " + repr(html[idx-30:idx+200]))
        raise SystemExit(1)


# ─────────────────────────────────────────────────────────────────────────
# 3. JS — fetch + render
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/5] Adding signals strip renderer to app.v5.js...")
js = APP_JS.read_text(encoding="utf-8")

JS_MARKER = "// === OVERVIEW SIGNALS STRIP (M2.5.1) ==="

if JS_MARKER in js:
    print("  ⏭  JS already patched")
else:
    backup(APP_JS)

    JS_BLOCK = '''


// === OVERVIEW SIGNALS STRIP (M2.5.1) ===
async function loadOverviewSignals() {
  const el = document.getElementById('ops-signals-strip');
  if (!el) return;
  try {
    const data = await api('/api/internal/overview-signals');
    if (!data) return;
    renderOverviewSignals(data);
  } catch (e) {
    console.error('overview-signals fetch failed', e);
  }
}

function renderOverviewSignals(payload) {
  const el = document.getElementById('ops-signals-strip');
  const signals = payload?.signals || [];
  if (!signals.length) {
    el.innerHTML = '';
    return;
  }

  // Severity → CSS class + icon
  const _sevIcon = sev => {
    if (sev === 'critical') return '🔴';
    if (sev === 'warning')  return '🟡';
    if (sev === 'ok')       return '🟢';
    return '⚪';
  };

  el.innerHTML = signals.map(s => `
    <div class="signal-card signal-${s.severity || 'ok'}">
      <div class="signal-head">
        <span class="signal-icon">${_sevIcon(s.severity)}</span>
        <span class="signal-title">${(s.title || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')}</span>
      </div>
      <div class="signal-metric">${(s.metric_text || '—').replace(/&/g,'&amp;').replace(/</g,'&lt;')}</div>
      <div class="signal-why">${(s.why_text || '').replace(/&/g,'&amp;').replace(/</g,'&lt;')}</div>
    </div>
  `).join('');
}
// === END OVERVIEW SIGNALS STRIP ===
'''

    js = js.rstrip() + JS_BLOCK
    print("  ✓ JS functions appended")

# Wire into loadInternal — Overview sub-tab is the default active tab,
# so we need signals to load alongside the rest of the overview data.
WIRE_MARKER = "loadOverviewSignals call inside loadInternal"
if WIRE_MARKER in js:
    print("  ⏭  loadInternal call already wired")
else:
    OLD_WIRE = '''    renderOpsContraAlert(contra);'''
    NEW_WIRE = '''    renderOpsContraAlert(contra);
    if (typeof loadOverviewSignals === 'function') loadOverviewSignals(); // loadOverviewSignals call inside loadInternal'''

    if OLD_WIRE in js:
        js = js.replace(OLD_WIRE, NEW_WIRE, 1)
        print("  ✓ loadOverviewSignals wired into loadInternal")
    else:
        print("  ⚠️  loadInternal anchor not found — manual wiring may be needed")

APP_JS.write_text(js, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 4. CSS — signals strip styling
# ─────────────────────────────────────────────────────────────────────────
print("\n[4/5] Adding CSS for signals strip...")
css = CSS.read_text(encoding="utf-8")

CSS_MARKER = "/* === Overview signals strip (M2.5.1) === */"
if CSS_MARKER in css:
    print("  ⏭  CSS already present")
else:
    backup(CSS)
    CSS_BLOCK = '''

/* === Overview signals strip (M2.5.1) === */
/* 4 cards side-by-side at the top of Overview. Severity drives left border. */
/* critical = red    (must-act signal)                                       */
/* warning  = amber  (watch zone)                                            */
/* ok       = green  (within normal range)                                   */
.signals-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.signal-card {
  background: var(--bg-card, rgba(255,255,255,0.04));
  border: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
  border-left-width: 3px;
  border-radius: 6px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 90px;
}
.signal-critical { border-left-color: #e03131; }
.signal-warning  { border-left-color: #f59f00; }
.signal-ok       { border-left-color: #2f9e44; }

.signal-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted, #888);
}
.signal-icon { font-size: 11px; }
.signal-title {
  font-weight: 500;
}
.signal-metric {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--text-primary, #fff);
  font-family: var(--font-mono, 'Inter', sans-serif);
}
.signal-critical .signal-metric { color: #ff6b6b; }
.signal-warning  .signal-metric { color: #ffd43b; }
.signal-ok       .signal-metric { color: #51cf66; }

.signal-why {
  font-size: 12px;
  color: var(--text-muted, #aaa);
  line-height: 1.35;
}

@media (max-width: 1100px) {
  .signals-strip { grid-template-columns: repeat(2, 1fr); }
}
'''
    css = css.rstrip() + CSS_BLOCK
    CSS.write_text(css, encoding="utf-8")
    print("  ✓ signals strip CSS appended")


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
print("M2.5.1 — Overview Top Signals strip complete.")
print("=" * 60)
print()
print("Overview sub-tab now has at the top:")
print("  - 4 signal cards: customer concentration | procurement concentration | contra | margin trend")
print("  - Existing KPI wall and contra alert remain below.")
print()
print("Restart uvicorn (new endpoint added):")
print("  Ctrl+C, then: python -m uvicorn dashboard.server:app --port 8000")
print()
print("Browser: hard-refresh, default Overview tab will show the strip.")
