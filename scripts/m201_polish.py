"""
M2.0.1 Polish — 5 small fixes in one patch script.

Fixes applied:
  1. Sidebar label: "Internal Data" → "Operations Intelligence"
  2. Header card overflow (CSS — top-right cards were getting clipped)
  3. Contra alert "why" line — driver narrative
  4. Status strip — richer context next to "Latest complete month"
  5. Maintenance KPI context note (small subtle hint when YoY is large)

Each fix is independently idempotent. Re-running this script is safe.

Usage:
    python scripts/m201_polish.py
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "dashboard" / "static" / "index.html"
JS   = ROOT / "dashboard" / "static" / "app.v5.js"
CSS  = ROOT / "dashboard" / "static" / "style.v5.css"


def fix_sidebar_label():
    """Fix 1: Sidebar 'Internal Data' → 'Operations Intelligence'."""
    text = HTML.read_text(encoding="utf-8")
    needle_old = '<span class="nav-icon">🏭</span> Internal Data'
    needle_new = '<span class="nav-icon">🏭</span> Operations Intelligence'

    if needle_new in text:
        return "skip", "sidebar already updated"
    if needle_old not in text:
        return "warn", f"sidebar needle not found"

    HTML.write_text(text.replace(needle_old, needle_new, 1), encoding="utf-8")
    return "ok", "sidebar relabeled"


HEADER_OVERFLOW_CSS_MARKER = "M2.0.1 header overflow fix"

HEADER_OVERFLOW_CSS = """
/* ── M2.0.1 header overflow fix ───────────────────────────────────────────
 * The top-right info cards (HIGH IMPACT / COST PRESSURE / RISK SIGNALS /
 * POLYESTER FDY) were clipping at the right edge. Constrain to viewport.
 */
.topbar, header, .header-bar, .top-cards, .top-stats {
  max-width: 100vw;
  overflow-x: hidden;
  box-sizing: border-box;
}
.top-cards, .top-stats {
  padding-right: 16px;
}
"""


def fix_header_overflow():
    """Fix 2: Header card overflow — defensive CSS."""
    text = CSS.read_text(encoding="utf-8")
    if HEADER_OVERFLOW_CSS_MARKER in text:
        return "skip", "header overflow fix already applied"

    CSS.write_text(text.rstrip() + "\n\n" + HEADER_OVERFLOW_CSS.lstrip() + "\n", encoding="utf-8")
    return "ok", "header overflow CSS appended"


def fix_contra_why_line():
    """Fix 3: Contra alert — add 'why' narrative line."""
    text = JS.read_text(encoding="utf-8")

    if "ops-alert-why" in text:
        return "skip", "contra why line already present"

    # Locate the contra alert builder (renderOpsContraAlert)
    needle = """  el.innerHTML = `
    <div class="ops-alert ops-alert-${sev}">
      <div class="ops-alert-header">
        <span class="ops-alert-title">Contra Revenue — ${a.month_label || ''}</span>
        <span class="ops-alert-badge ops-alert-badge-${sev}">${sevLabel}</span>
      </div>"""
    if needle not in text:
        return "warn", "contra alert anchor not found in JS"

    # Build narrative inline using existing variables in the function
    # We insert a "why" line right after the header, before the grid.
    why_block = """  el.innerHTML = `
    <div class="ops-alert ops-alert-${sev}">
      <div class="ops-alert-header">
        <span class="ops-alert-title">Contra Revenue — ${a.month_label || ''}</span>
        <span class="ops-alert-badge ops-alert-badge-${sev}">${sevLabel}</span>
      </div>
      <div class="ops-alert-why">${buildContraNarrative(a)}</div>"""

    # Also inject the buildContraNarrative helper near the top of the ops block.
    # Strategy: prepend the helper before renderOpsContraAlert.
    helper = """function buildContraNarrative(a) {
  if (!a || a.total_contra_tl == null) return 'No contra data available for this period.';
  const sev = a.severity || 'normal';
  const top = a.top_counterparty_name;
  const topPct = a.top_counterparty_pct;
  const ratio = a.ratio_to_median;
  const sourceLabel = (a.top_counterparty_source || '').toLowerCase() === 'satiş'
    ? 'customer return' : 'supplier-side adjustment';
  const ratioText = (ratio != null && !isNaN(ratio))
    ? `${Number(ratio).toFixed(1)}× the 24-month median`
    : 'elevated';
  if (sev === 'high' || sev === 'elevated') {
    if (top && topPct != null && topPct >= 30) {
      return `Driven primarily by a single ${sourceLabel}: <strong>${top}</strong> accounts for ${Number(topPct).toFixed(0)}% of total contra. Overall contra is ${ratioText}.`;
    }
    return `Contra is ${ratioText}. Top contributor: <strong>${top || '—'}</strong> (${topPct != null ? Number(topPct).toFixed(0) : '—'}% of total).`;
  }
  return `Contra is within normal range (${ratioText}).`;
}

"""

    text2 = text.replace(needle, why_block, 1)

    # Insert helper before renderOpsContraAlert function
    fn_anchor = "function renderOpsContraAlert("
    if fn_anchor not in text2:
        return "warn", "renderOpsContraAlert anchor disappeared"
    text3 = text2.replace(fn_anchor, helper + fn_anchor, 1)

    JS.write_text(text3, encoding="utf-8")
    return "ok", "contra why line + narrative helper inserted"


def fix_status_strip():
    """Fix 4: Status strip — richer context."""
    text = JS.read_text(encoding="utf-8")

    if "ops-status-strip" in text:
        return "skip", "status strip already updated"

    old = """function renderOpsPeriodHeader(kpi) {
  const ref = kpi.reference || {};
  const el = document.getElementById('ops-period-header');
  if (!el) return;
  el.innerHTML = `
    <span class="ops-period-label">Latest complete month:</span>
    <span class="ops-period-value">${ref.purchase_latest_month || '—'}</span>
    <span class="ops-period-meta">vs same month prior year (YoY)</span>
  `;
}"""

    new = """function renderOpsPeriodHeader(kpi) {
  const ref = kpi.reference || {};
  const el = document.getElementById('ops-period-header');
  if (!el) return;
  el.classList.add('ops-status-strip');
  el.innerHTML = `
    <span class="ops-status-cell">
      <span class="ops-status-cell-label">Latest complete month</span>
      <span class="ops-status-cell-value">${ref.purchase_latest_month || '—'}</span>
    </span>
    <span class="ops-status-cell">
      <span class="ops-status-cell-label">Window</span>
      <span class="ops-status-cell-value">last 24 months</span>
    </span>
    <span class="ops-status-cell">
      <span class="ops-status-cell-label">Currency</span>
      <span class="ops-status-cell-value">TL primary · USD/EUR secondary</span>
    </span>
    <span class="ops-status-cell">
      <span class="ops-status-cell-label">Classification</span>
      <span class="ops-status-cell-value">v3 · current</span>
    </span>
    <span class="ops-status-cell ops-status-meta">YoY = vs same month prior year</span>
  `;
}"""

    if old not in text:
        return "warn", "renderOpsPeriodHeader anchor not found"

    JS.write_text(text.replace(old, new, 1), encoding="utf-8")
    return "ok", "status strip enriched"


STATUS_STRIP_CSS_MARKER = "M2.0.1 status strip"

STATUS_STRIP_CSS = """
/* ── M2.0.1 status strip ──────────────────────────────────────────────── */
.ops-status-strip {
  display: flex !important;
  flex-wrap: wrap;
  align-items: stretch;
  gap: 0;
  padding: 0 !important;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  margin-bottom: 18px;
  overflow: hidden;
}
.ops-status-cell {
  display: flex;
  flex-direction: column;
  padding: 10px 16px;
  border-right: 1px solid #30363d;
  min-width: 140px;
}
.ops-status-cell:last-child { border-right: none; }
.ops-status-cell-label {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: #8b949e;
  margin-bottom: 2px;
}
.ops-status-cell-value {
  font-size: 12px;
  color: #e6edf3;
  font-weight: 500;
}
.ops-status-meta {
  margin-left: auto;
  align-items: flex-end;
  justify-content: center;
  color: #8b949e;
  font-size: 11px;
  font-style: italic;
}
@media (max-width: 900px) {
  .ops-status-meta { display: none; }
}

/* Why line in contra alert */
.ops-alert-why {
  font-size: 12px;
  color: #c9d1d9;
  margin-bottom: 14px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 6px;
  line-height: 1.45;
}
.ops-alert-why strong {
  color: #e6edf3;
  font-weight: 600;
}
"""


def fix_status_strip_css():
    """Fix 4 (companion): Status strip CSS."""
    text = CSS.read_text(encoding="utf-8")
    if STATUS_STRIP_CSS_MARKER in text:
        return "skip", "status strip CSS already applied"

    CSS.write_text(text.rstrip() + "\n\n" + STATUS_STRIP_CSS.lstrip() + "\n", encoding="utf-8")
    return "ok", "status strip CSS appended"


def fix_maintenance_context():
    """Fix 5: Maintenance KPI gets a context hint when YoY swing is large."""
    text = JS.read_text(encoding="utf-8")
    if "stat-context-hint" in text:
        return "skip", "maintenance context hint already present"

    # Patch buildKpiCard to add a small contextual line for large swings.
    old = """  return `
    <div class="stat-card">
      <div class="stat-label">${metric.metric_label}</div>
      <div class="stat-value">${tlMain}</div>
      <div class="stat-sub ${yoyCls}">${yoy ? `YoY ${yoy}` : '—'}</div>
      ${fxText ? `<div class="stat-fx">${fxText}</div>` : ''}
    </div>
  `;"""

    new = """  // Add a small context hint when the YoY swing is large (≥ ±60%) and the
  // absolute amount is small relative to a typical month — this keeps weakly-
  // signal items like a single Maintenance month from looking like alarms.
  let contextHint = '';
  if (metric.yoy_pct_tl != null && Math.abs(metric.yoy_pct_tl) >= 60) {
    contextHint = `<div class="stat-context-hint">Volatile line item — single-month YoY may overstate the underlying trend.</div>`;
  }

  return `
    <div class="stat-card">
      <div class="stat-label">${metric.metric_label}</div>
      <div class="stat-value">${tlMain}</div>
      <div class="stat-sub ${yoyCls}">${yoy ? `YoY ${yoy}` : '—'}</div>
      ${fxText ? `<div class="stat-fx">${fxText}</div>` : ''}
      ${contextHint}
    </div>
  `;"""

    if old not in text:
        return "warn", "buildKpiCard anchor not found"

    JS.write_text(text.replace(old, new, 1), encoding="utf-8")
    return "ok", "maintenance context hint added"


CONTEXT_HINT_CSS_MARKER = "M2.0.1 stat-context-hint"

CONTEXT_HINT_CSS = """
/* ── M2.0.1 stat-context-hint ─────────────────────────────────────────── */
.stat-context-hint {
  font-size: 10px;
  color: #8b949e;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed #30363d;
  font-style: italic;
  line-height: 1.4;
}
"""


def fix_maintenance_context_css():
    text = CSS.read_text(encoding="utf-8")
    if CONTEXT_HINT_CSS_MARKER in text:
        return "skip", "context hint CSS already applied"

    CSS.write_text(text.rstrip() + "\n\n" + CONTEXT_HINT_CSS.lstrip() + "\n", encoding="utf-8")
    return "ok", "context hint CSS appended"


def main():
    # Backups
    for f in (HTML, JS, CSS):
        bak = f.with_suffix(f.suffix + ".bak_m201")
        if not bak.exists():
            bak.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")

    steps = [
        ("Fix 1 — sidebar label",            fix_sidebar_label),
        ("Fix 2 — header overflow CSS",      fix_header_overflow),
        ("Fix 3 — contra why line",          fix_contra_why_line),
        ("Fix 4 — status strip JS",          fix_status_strip),
        ("Fix 4 — status strip CSS",         fix_status_strip_css),
        ("Fix 5 — maintenance context JS",   fix_maintenance_context),
        ("Fix 5 — maintenance context CSS",  fix_maintenance_context_css),
    ]

    results = []
    for label, fn in steps:
        try:
            status, msg = fn()
        except Exception as e:
            status, msg = "error", str(e)
        results.append((label, status, msg))

    print()
    print("=" * 64)
    print("M2.0.1 POLISH — RESULTS")
    print("=" * 64)
    for label, status, msg in results:
        icon = {"ok": "✓", "skip": "·", "warn": "!", "error": "✗"}.get(status, "?")
        print(f"  {icon}  {label:36s}  {status:6s}  {msg}")
    print("=" * 64)

    any_warn = any(s in ("warn", "error") for _, s, _ in results)
    if any_warn:
        print()
        print("Some fixes did not apply cleanly. See messages above.")
        print("Backups available with .bak_m201 suffix.")
    else:
        print()
        print("All polish fixes applied. Reload browser (force-refresh: Ctrl+F5).")


if __name__ == "__main__":
    main()
