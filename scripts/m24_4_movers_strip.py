"""
M2.4.4 — Cost Structure Phase 1 Movers strip.

Backend: new endpoint /api/internal/cost-movers (reads v_cost_movers — Migration 025)
Frontend: 3 separate cards (NOT in KPI strip), inserted between KPI strip and
          the absolute TL chart. Each card represents one slot:
            - biggest_increase   : RED border, ▲ icon
            - biggest_decrease   : GREEN border, ▼ icon
            - highest_volatility : YELLOW/AMBER border, ~ icon, shows CV value

When a slot returns no row (threshold not met), the card shows
"no significant change this month".

Backups: .bak_m24_4 suffix.
"""
from pathlib import Path

SERVER = Path("dashboard/server.py")
INDEX  = Path("dashboard/static/index.html")
APP_JS = Path("dashboard/static/app.v5.js")
CSS    = Path("dashboard/static/style.v5.css")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_m24_4")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


# ─────────────────────────────────────────────────────────────────────────
# 1. Backend — new endpoint
# ─────────────────────────────────────────────────────────────────────────
print("[1/5] Adding /api/internal/cost-movers endpoint...")
text = SERVER.read_text(encoding="utf-8")

ENDPOINT_MARKER = '@app.get("/api/internal/cost-movers")'
if ENDPOINT_MARKER in text:
    print("  ⏭  endpoint already present")
else:
    backup(SERVER)

    ANCHOR = '@app.get("/api/internal/top-cost-suppliers")'
    if ANCHOR not in text:
        ANCHOR = "# ── /api/internal/top-customers ───────"
        if ANCHOR not in text:
            print("  ❌ no anchor found")
            raise SystemExit(1)

    NEW_ENDPOINT = '''# ── /api/internal/cost-movers ──────────────────────────────────────────────
# M2.4.4 — Cost Structure Phase 1 Movers strip.
# Returns up to 3 slots (biggest_increase, biggest_decrease, highest_volatility).
# Each slot may be absent if threshold not met (frontend renders empty state).
@app.get("/api/internal/cost-movers")
def internal_cost_movers():
    rows = _rows("""
        SELECT
            display_order,
            slot,
            bucket,
            pct_change::float        AS pct_change,
            abs_change_tl::float     AS abs_change_tl,
            latest_tl::float         AS latest_tl,
            prior_tl::float          AS prior_tl,
            cv::float                AS cv,
            stdev_tl::float          AS stdev_tl,
            mean_tl::float           AS mean_tl
        FROM v_cost_movers
        ORDER BY display_order
    """)
    return {
        "movers": rows,
        "thresholds": {
            "increase_pct":   5.0,
            "decrease_pct":  -5.0,
            "volatility_cv":  0.20,
        },
        "window": {
            "movers":     "latest complete month vs prior complete month",
            "volatility": "last 12 months",
        },
    }


'''

    text = text.replace(ANCHOR, NEW_ENDPOINT + ANCHOR, 1)
    SERVER.write_text(text, encoding="utf-8")
    print("  ✓ endpoint added")


# ─────────────────────────────────────────────────────────────────────────
# 2. HTML — insert movers strip below KPI strip, above the absolute chart
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/5] Inserting Movers strip into Cost sub-section HTML...")
html = INDEX.read_text(encoding="utf-8")

if 'id="ops-cost-movers"' in html:
    print("  ⏭  Movers strip already present")
else:
    # Anchor: right after the KPI strip div, before the chart-panel.
    OLD_8 = '''<div id="ops-cost-kpis" class="proc-kpi-strip" style="margin-bottom:16px"></div>
        <div class="chart-panel">'''
    NEW_8 = '''<div id="ops-cost-kpis" class="proc-kpi-strip" style="margin-bottom:16px"></div>
        <div id="ops-cost-movers" class="cost-movers-strip" style="margin-bottom:16px"></div>
        <div class="chart-panel">'''

    OLD_6 = '''<div id="ops-cost-kpis" class="proc-kpi-strip" style="margin-bottom:16px"></div>
      <div class="chart-panel">'''
    NEW_6 = '''<div id="ops-cost-kpis" class="proc-kpi-strip" style="margin-bottom:16px"></div>
      <div id="ops-cost-movers" class="cost-movers-strip" style="margin-bottom:16px"></div>
      <div class="chart-panel">'''

    if OLD_8 in html:
        backup(INDEX)
        html = html.replace(OLD_8, NEW_8, 1)
        INDEX.write_text(html, encoding="utf-8")
        print("  ✓ Movers strip container inserted (8-space indent)")
    elif OLD_6 in html:
        backup(INDEX)
        html = html.replace(OLD_6, NEW_6, 1)
        INDEX.write_text(html, encoding="utf-8")
        print("  ✓ Movers strip container inserted (6-space indent)")
    else:
        print("  ❌ KPI strip anchor not found")
        idx = html.find('ops-cost-kpis')
        if idx > 0:
            print("  Context: " + repr(html[idx-30:idx+200]))
        raise SystemExit(1)


# ─────────────────────────────────────────────────────────────────────────
# 3. JS — fetch + render
# ─────────────────────────────────────────────────────────────────────────
print("\n[3/5] Adding Cost Movers strip to app.v5.js...")
js = APP_JS.read_text(encoding="utf-8")

JS_MARKER = "// === COST MOVERS STRIP (M2.4.4) ==="

if JS_MARKER in js:
    print("  ⏭  JS already patched")
else:
    backup(APP_JS)

    JS_BLOCK = '''


// === COST MOVERS STRIP (M2.4.4) ===
async function loadCostMovers() {
  const el = document.getElementById('ops-cost-movers');
  if (!el) return;
  try {
    const data = await api('/api/internal/cost-movers');
    if (!data) return;
    renderCostMovers(data);
  } catch (e) {
    console.error('cost-movers fetch failed', e);
  }
}

function renderCostMovers(payload) {
  const el = document.getElementById('ops-cost-movers');
  const movers = payload?.movers || [];

  // Index by slot for O(1) lookup
  const bySlot = {};
  movers.forEach(m => { bySlot[m.slot] = m; });

  const _fmtTL = v => {
    if (v == null || isNaN(v)) return '—';
    const abs = Math.abs(v);
    const sign = v < 0 ? '-' : '';
    if (abs >= 1e9) return sign + '₺' + (abs/1e9).toFixed(2) + 'B';
    if (abs >= 1e6) return sign + '₺' + (abs/1e6).toFixed(1) + 'M';
    if (abs >= 1e3) return sign + '₺' + (abs/1e3).toFixed(0) + 'K';
    return sign + '₺' + abs.toFixed(0);
  };
  const _fmtPct = v => {
    if (v == null || isNaN(v)) return '—';
    const sign = v >= 0 ? '+' : '';
    return sign + v.toFixed(1) + '%';
  };

  const _renderCard = (slotKey, label, kind) => {
    const m = bySlot[slotKey];
    const empty = !m || !m.bucket;
    const emptyMsg = (kind === 'volatility')
      ? 'no high-volatility bucket (CV < 0.20)'
      : 'no significant change this month';

    if (empty) {
      return `
        <div class="cost-mover-card cost-mover-${kind} cost-mover-empty">
          <div class="cost-mover-label">${label}</div>
          <div class="cost-mover-value">—</div>
          <div class="cost-mover-sub">${emptyMsg}</div>
        </div>`;
    }

    if (kind === 'volatility') {
      return `
        <div class="cost-mover-card cost-mover-${kind}">
          <div class="cost-mover-label">${label}</div>
          <div class="cost-mover-value">~ ${m.bucket}</div>
          <div class="cost-mover-sub">CV ${m.cv != null ? m.cv.toFixed(2) : '—'}</div>
        </div>`;
    }

    // increase / decrease
    const arrow = (kind === 'increase') ? '▲' : '▼';
    const pctStr = _fmtPct(m.pct_change);
    const absStr = _fmtTL(m.abs_change_tl);
    return `
      <div class="cost-mover-card cost-mover-${kind}">
        <div class="cost-mover-label">${label}</div>
        <div class="cost-mover-value">${arrow} ${m.bucket}</div>
        <div class="cost-mover-sub">${pctStr} <span class="cost-mover-abs">(${absStr})</span></div>
      </div>`;
  };

  el.innerHTML = `
    ${_renderCard('biggest_increase',   'Biggest increase',   'increase')}
    ${_renderCard('biggest_decrease',   'Biggest decrease',   'decrease')}
    ${_renderCard('highest_volatility', 'Highest volatility (12m)', 'volatility')}
  `;
}
// === END COST MOVERS STRIP ===
'''

    js = js.rstrip() + JS_BLOCK
    print("  ✓ JS functions appended")

# Wire sub-tab activation hook
WIRE_MARKER = "loadCostMovers hook"
if WIRE_MARKER in js:
    print("  ⏭  sub-tab hook already wired")
else:
    OLD_WIRE = '''      // loadCostKpis hook (M2.4.2)
      if (btn.dataset.sub === 'ops-cost' && typeof loadCostKpis === 'function') {
        if (!window._costKpisLoaded) {
          loadCostKpis();
          window._costKpisLoaded = true;
        }
      }'''

    NEW_WIRE = '''      // loadCostKpis hook (M2.4.2)
      if (btn.dataset.sub === 'ops-cost' && typeof loadCostKpis === 'function') {
        if (!window._costKpisLoaded) {
          loadCostKpis();
          window._costKpisLoaded = true;
        }
      }
      // loadCostMovers hook (M2.4.4)
      if (btn.dataset.sub === 'ops-cost' && typeof loadCostMovers === 'function') {
        if (!window._costMoversLoaded) {
          loadCostMovers();
          window._costMoversLoaded = true;
        }
      }'''

    if OLD_WIRE in js:
        js = js.replace(OLD_WIRE, NEW_WIRE, 1)
        print("  ✓ sub-tab activation wired to loadCostMovers")
    else:
        print("  ⚠️  Cost KPI hook anchor not found — manual wiring may be needed")

APP_JS.write_text(js, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 4. CSS — movers strip styling
# ─────────────────────────────────────────────────────────────────────────
print("\n[4/5] Adding CSS for cost movers strip...")
css = CSS.read_text(encoding="utf-8")

CSS_MARKER = "/* === Cost movers strip (M2.4.4) === */"
if CSS_MARKER in css:
    print("  ⏭  CSS already present")
else:
    backup(CSS)
    CSS_BLOCK = '''

/* === Cost movers strip (M2.4.4) === */
/* 3 cards side-by-side with kind-based left border accent.                */
/* increase   = red    (cost rising, margin pressure)                      */
/* decrease   = green  (cost falling, margin relief)                       */
/* volatility = amber  (warning, neutral semantics)                        */
.cost-movers-strip {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}
.cost-mover-card {
  background: var(--bg-card, rgba(255,255,255,0.04));
  border: 1px solid var(--border-subtle, rgba(255,255,255,0.06));
  border-left-width: 3px;
  border-radius: 6px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cost-mover-increase   { border-left-color: #e03131; }
.cost-mover-decrease   { border-left-color: #2f9e44; }
.cost-mover-volatility { border-left-color: #f59f00; }
.cost-mover-empty      { opacity: 0.6; }

.cost-mover-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted, #888);
}
.cost-mover-value {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary, #fff);
  font-family: var(--font-mono, 'Inter', sans-serif);
}
.cost-mover-increase   .cost-mover-value { color: #ff6b6b; }
.cost-mover-decrease   .cost-mover-value { color: #51cf66; }
.cost-mover-volatility .cost-mover-value { color: #ffd43b; }

.cost-mover-sub {
  font-size: 12px;
  color: var(--text-muted, #aaa);
}
.cost-mover-abs {
  color: var(--text-muted, #888);
  font-size: 11.5px;
}
'''
    css = css.rstrip() + CSS_BLOCK
    CSS.write_text(css, encoding="utf-8")
    print("  ✓ movers strip CSS appended")


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
print("M2.4.4 — Cost Movers strip complete.")
print("=" * 60)
print()
print("Cost Structure sub-tab is now Phase 1 complete:")
print("  - KPI strip (M2.4.2)            6 metrics")
print("  - Movers strip (M2.4.4)         3 cards: increase | decrease | volatility")
print("  - Absolute TL chart (existing)")
print("  - Mix % chart (M2.4.3)")
print("  - Provisional logistics note")
print("  - Top 10 Cost Suppliers (M2.4.1)")
print()
print("Restart uvicorn (new endpoint added):")
print("  Ctrl+C, then: python -m uvicorn dashboard.server:app --port 8000")
print()
print("Browser: hard-refresh, Operations Intelligence > Cost Structure.")
