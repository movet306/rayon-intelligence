"""
pi_1_3_action_watch_all.py - Tier the signal feed into Action / Watch / All.

Replaces the flat _renderEarlyWarningBar render with a 3-tier presentation:

  Action Now (max 3)   — severity in {critical, high}
  Watch (max 5)        — severity = medium
  All Signals          — everything else (low) + overflow from Action/Watch caps

Behavior:
  - Sorting: severity rank, then signal_date DESC, then created_at DESC
    (already applied server-side via the v_active_signals view).
  - Caps are HARD: if 4 high-severity signals exist, only top 3 go to Action;
    the 4th cascades down to Watch (and on to All if Watch is also full).
  - Section headers are collapsible (▼ open / ▶ closed). Action and Watch
    open by default; All collapsed by default.
  - Empty Action / Watch sections are still shown with a muted "şu an X yok"
    line so the user can see at a glance that the relevant tier is calm.

No backend changes — purely frontend re-render. Server still returns the
same flat array from /api/price_intelligence_signals.

Reversal: revert _renderEarlyWarningBar to the previous flat .map().join('').

Idempotent.
"""
from pathlib import Path
import re
import sys
import time

REPO = Path(__file__).resolve().parent.parent
APPJS = REPO / "dashboard" / "static" / "app.v5.js"
INDEX = REPO / "dashboard" / "static" / "index.html"
CSS   = REPO / "dashboard" / "static" / "style.v5.css"

src = APPJS.read_text(encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# Replace the entire _renderEarlyWarningBar function body
# ─────────────────────────────────────────────────────────────────────────────
OLD_FN = """function _renderEarlyWarningBar(bar, signals) {
  if (!signals || !signals.length) {
    bar.innerHTML = '<div class="no-signals-muted">Aktif fiyat sinyali yok — piyasalar sakin</div>';
    return;
  }

  const SEV_LABEL  = { critical: 'KRİTİK', high: 'YÜKSEK', medium: 'ORTA', low: 'DÜŞÜK' };
  const TYPE_LABEL = {
    COST_PRESSURE_UP:        'Maliyet Artışı',
    COST_PRESSURE_DOWN:      'Maliyet Düşüşü',
    UPSTREAM_DOWNSTREAM_DIVG:'Zincir Uyumsuzluğu',
    SPREAD_WIDENING:         'Spread Genişleme',
    SPREAD_TIGHTENING:       'Spread Daralma',
    VOLATILITY_SPIKE:        'Volatilite',
    DELAYED_PASS_THROUGH_RISK:'Gecikmiş Yansıma',
    DATA_QUALITY_WARNING:    'Veri Uyarısı',
  };

  bar.innerHTML = signals.map(s => {
    const sev      = s.severity || 'low';
    const typeText = TYPE_LABEL[s.signal_type] || s.signal_type;
    const valChip  = s.value_pct != null
      ? `<div class="ew-value-chip">${s.value_pct > 0 ? '+' : ''}${s.value_pct.toFixed(1)}%</div>` : '';
    const lagHtml  = (s.turkey_lag_min && s.turkey_lag_max)
      ? `<div class="ew-lag">&#8594; Türkiye tahmini: ${s.turkey_lag_min}–${s.turkey_lag_max} hafta</div>` : '';
    const impl     = s.business_implication
      ? `<div class="ew-implication">${esc(s.business_implication)}</div>` : '';

    return `
      <div class="early-warning-card ew-card-${sev}">
        <div class="ew-left">
          <span class="ew-type-badge ew-badge-${sev}">${typeText}</span>
          <span class="ew-sev-text">${SEV_LABEL[sev] || sev}</span>
        </div>
        <div class="ew-content">
          <div class="ew-explanation">${esc(s.explanation)}</div>
          ${impl}${lagHtml}
        </div>
        ${valChip}
      </div>`;
  }).join('');
}"""

NEW_FN = """function _renderEarlyWarningBar(bar, signals) {
  // PI-1.3: tiered presentation (Action / Watch / All) with hard caps.
  if (!signals || !signals.length) {
    bar.innerHTML = '<div class="no-signals-muted">Aktif fiyat sinyali yok — piyasalar sakin</div>';
    return;
  }

  const SEV_LABEL  = { critical: 'KRİTİK', high: 'YÜKSEK', medium: 'ORTA', low: 'DÜŞÜK' };
  const TYPE_LABEL = {
    COST_PRESSURE_UP:        'Maliyet Artışı',
    COST_PRESSURE_DOWN:      'Maliyet Düşüşü',
    UPSTREAM_DOWNSTREAM_DIVG:'Zincir Uyumsuzluğu',
    SPREAD_WIDENING:         'Spread Genişleme',
    SPREAD_TIGHTENING:       'Spread Daralma',
    VOLATILITY_SPIKE:        'Volatilite',
    DELAYED_PASS_THROUGH_RISK:'Gecikmiş Yansıma',
    DATA_QUALITY_WARNING:    'Veri Uyarısı',
  };

  // Render a single signal card (unchanged from the previous flat version).
  const renderCard = (s) => {
    const sev      = s.severity || 'low';
    const typeText = TYPE_LABEL[s.signal_type] || s.signal_type;
    const valChip  = s.value_pct != null
      ? `<div class="ew-value-chip">${s.value_pct > 0 ? '+' : ''}${s.value_pct.toFixed(1)}%</div>` : '';
    const lagHtml  = (s.turkey_lag_min && s.turkey_lag_max)
      ? `<div class="ew-lag">&#8594; Türkiye tahmini: ${s.turkey_lag_min}–${s.turkey_lag_max} hafta</div>` : '';
    const impl     = s.business_implication
      ? `<div class="ew-implication">${esc(s.business_implication)}</div>` : '';
    return `
      <div class="early-warning-card ew-card-${sev}">
        <div class="ew-left">
          <span class="ew-type-badge ew-badge-${sev}">${typeText}</span>
          <span class="ew-sev-text">${SEV_LABEL[sev] || sev}</span>
        </div>
        <div class="ew-content">
          <div class="ew-explanation">${esc(s.explanation)}</div>
          ${impl}${lagHtml}
        </div>
        ${valChip}
      </div>`;
  };

  // Tier the signals. Server already returns them sorted by severity then
  // signal_date DESC (via v_active_signals), so we just walk the array and
  // partition with hard caps.
  const ACTION_CAP = 3;
  const WATCH_CAP  = 5;

  const action = [];
  const watch  = [];
  const all    = [];

  signals.forEach(s => {
    const sev = s.severity || 'low';
    if ((sev === 'critical' || sev === 'high') && action.length < ACTION_CAP) {
      action.push(s);
    } else if (sev === 'medium' && watch.length < WATCH_CAP) {
      watch.push(s);
    } else {
      all.push(s);
    }
  });

  // Render a section. Action and Watch are open by default and always shown
  // (with a muted note when empty so the user can read "calm" at a glance).
  // All Signals is collapsed by default and hidden if empty.
  const renderSection = (label, items, opts) => {
    const { defaultOpen, idSuffix, emptyMsg, hideWhenEmpty } = opts;
    if (!items.length && hideWhenEmpty) return '';
    const openCls = defaultOpen ? 'open' : '';
    const chevron = defaultOpen ? '▼' : '▶';
    const body = items.length
      ? items.map(renderCard).join('')
      : `<div class="ew-section-empty">${emptyMsg}</div>`;
    return `
      <div class="ew-section ${openCls}" data-section="${idSuffix}">
        <div class="ew-section-header" onclick="this.parentElement.classList.toggle('open');
                                                 const c=this.querySelector('.ew-chevron');
                                                 if(c)c.textContent=this.parentElement.classList.contains('open')?'▼':'▶';">
          <span class="ew-chevron">${chevron}</span>
          <span class="ew-section-label">${label}</span>
          <span class="ew-section-count">(${items.length})</span>
        </div>
        <div class="ew-section-content">${body}</div>
      </div>`;
  };

  bar.innerHTML =
    renderSection('Action Now', action, {
      defaultOpen: true,
      idSuffix: 'action',
      emptyMsg: 'Şu an aksiyon gerektiren kritik / yüksek sinyal yok.',
      hideWhenEmpty: false,
    }) +
    renderSection('Watch', watch, {
      defaultOpen: true,
      idSuffix: 'watch',
      emptyMsg: 'Orta seviye izleme sinyali yok.',
      hideWhenEmpty: false,
    }) +
    renderSection('Tüm Sinyaller', all, {
      defaultOpen: false,
      idSuffix: 'all',
      emptyMsg: '',
      hideWhenEmpty: true,
    });
}"""

if "PI-1.3: tiered presentation" in src:
    print("[skip] _renderEarlyWarningBar already tiered")
elif OLD_FN in src:
    src = src.replace(OLD_FN, NEW_FN)
    APPJS.write_text(src, encoding="utf-8")
    print("[OK]  _renderEarlyWarningBar replaced with tiered version")
else:
    print("[X]   _renderEarlyWarningBar function body did not match the expected form")
    print("      (was the function edited since the patch was generated?)")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Append CSS for the new section structure
# ─────────────────────────────────────────────────────────────────────────────
css_src = CSS.read_text(encoding="utf-8")

NEW_CSS = """

/* ── PI-1.3: Action / Watch / All section tiers ───────────────────────────── */
.ew-section {
  margin-bottom: 18px;
}
.ew-section-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  cursor: pointer;
  padding: 6px 4px;
  user-select: none;
  border-bottom: 1px solid var(--border, #2a2f3a);
  margin-bottom: 8px;
}
.ew-section-header:hover {
  background: rgba(255, 255, 255, 0.02);
}
.ew-chevron {
  font-size: 11px;
  color: var(--muted, #8a92a3);
  width: 12px;
  display: inline-block;
  text-align: center;
}
.ew-section-label {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--text, #e6e9ef);
}
.ew-section-count {
  font-size: 12px;
  color: var(--muted, #8a92a3);
  font-weight: 400;
}
.ew-section-content {
  display: none;
}
.ew-section.open .ew-section-content {
  display: block;
}
.ew-section-empty {
  padding: 10px 4px;
  font-size: 12px;
  color: var(--muted, #8a92a3);
  font-style: italic;
}
"""

if "/* ── PI-1.3: Action / Watch / All section tiers" in css_src:
    print("[skip] CSS for tiered sections already present")
else:
    CSS.write_text(css_src.rstrip() + NEW_CSS, encoding="utf-8")
    print("[OK]  CSS for tiered sections appended to style.v5.css")

# ─────────────────────────────────────────────────────────────────────────────
# Bump cache busters on app.v5.js AND style.v5.css
# ─────────────────────────────────────────────────────────────────────────────
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())

m_js = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m_js:
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    print(f"[OK]  index.html: app.v5.js cache buster -> {ts}")

m_css = re.search(r'style\.v5\.css\?v=(\S+?)"', html)
if m_css:
    html = re.sub(r'style\.v5\.css\?v=\S+?"', f'style.v5.css?v={ts}"', html)
    print(f"[OK]  index.html: style.v5.css cache buster -> {ts}")

INDEX.write_text(html, encoding="utf-8")

print()
print("Done. Browser: Ctrl+Shift+R on Price Intelligence.")
print()
print("Expected with current data (9 signals: 5 medium, 4 low):")
print("  Action Now (0)   open, with muted 'şu an aksiyon yok' note")
print("  Watch (5)        open, 5 medium-severity cards")
print("  Tüm Sinyaller (4) collapsed, click to expand")
print()
print("Click any section header to toggle open/closed.")
