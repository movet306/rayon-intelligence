"""
Counterparty UI fix — full dark-theme rewrite.

Replaces the entire Counterparty Explorer CSS block (M2.1, lines ~1566-1806)
with:
  - Correct selectors (#sub-ops-counterparty instead of #section-counterparty,
    which never matched after the section was nested under Operations).
  - Dark-theme colors using existing :root tokens (--bg, --card, --border,
    --text, --muted, --blue, --green, --orange, --red).
  - Tables that match the visual weight of Procurement/Cost top-10 tables.
  - Charts using brand blue (--blue) and dark grid lines.

Backup: style.v5.css.bak_cp_ui_fix
"""
from pathlib import Path

CSS = Path("dashboard/static/style.v5.css")


def backup(path):
    bak = path.with_suffix(path.suffix + ".bak_cp_ui_fix")
    if not bak.exists():
        bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  💾 backup: {bak}")


print("[1/2] Replacing Counterparty CSS block with dark-theme rewrite...")
css = CSS.read_text(encoding="utf-8")

START = "/* === COUNTERPARTY EXPLORER (M2.1) === */"
END   = "/* === END COUNTERPARTY EXPLORER (M2.1) === */"

start_idx = css.find(START)
end_idx   = css.find(END)

if start_idx < 0 or end_idx < 0:
    print("  ❌ Counterparty block markers not found")
    raise SystemExit(1)

end_idx_full = end_idx + len(END)

backup(CSS)

NEW_BLOCK = '''/* === COUNTERPARTY EXPLORER (M2.1, dark theme rewrite) === */
/* Selector fix: was #section-counterparty (never matched after the section  */
/* was nested as a sub-tab). Now uses #sub-ops-counterparty.                 */
/* All colors now reference :root tokens to stay in sync with the rest.      */

#sub-ops-counterparty .ce-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin: 12px 0 16px;
  flex-wrap: wrap;
}

#sub-ops-counterparty .ce-mode-toggle {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  background: var(--card);
}
#sub-ops-counterparty .ce-mode-btn {
  padding: 6px 14px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 13px;
  color: var(--muted);
  transition: background 0.12s ease, color 0.12s ease;
}
#sub-ops-counterparty .ce-mode-btn:hover {
  color: var(--text);
  background: rgba(255,255,255,0.04);
}
#sub-ops-counterparty .ce-mode-btn.ce-mode-active {
  background: var(--blue);
  color: #fff;
}

#sub-ops-counterparty .ce-search-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  max-width: 480px;
}
#sub-ops-counterparty #ce-search {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
  background: var(--card);
  color: var(--text);
}
#sub-ops-counterparty #ce-search::placeholder { color: var(--muted); }
#sub-ops-counterparty #ce-search:focus {
  outline: none;
  border-color: var(--blue);
}
#sub-ops-counterparty #ce-search-status {
  font-size: 12px;
  color: var(--muted);
  min-width: 80px;
}

/* ── Layout ─────────────────────────────────────────────────────────────── */
#sub-ops-counterparty .ce-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  min-height: 600px;
}

/* ── List pane ──────────────────────────────────────────────────────────── */
#sub-ops-counterparty .ce-list-pane {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--card);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
#sub-ops-counterparty .ce-list-header {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.02);
  font-size: 12px;
  display: flex;
  justify-content: space-between;
  color: var(--muted);
}
#sub-ops-counterparty .ce-list-hint { font-style: italic; }

#sub-ops-counterparty .ce-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  max-height: 700px;
}
#sub-ops-counterparty .ce-list-item {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  font-size: 12px;
  transition: background 0.12s ease;
}
#sub-ops-counterparty .ce-list-item:hover { background: rgba(255,255,255,0.04); }
#sub-ops-counterparty .ce-list-item-active {
  background: rgba(88,166,255,0.12) !important;
  border-left: 3px solid var(--blue);
  padding-left: 9px;
}
#sub-ops-counterparty .ce-li-name {
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
  line-height: 1.3;
}
#sub-ops-counterparty .ce-li-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 11px;
  color: var(--muted);
}
#sub-ops-counterparty .ce-li-amount { font-weight: 600; color: var(--blue); }
#sub-ops-counterparty .ce-li-rows { color: var(--muted); }
#sub-ops-counterparty .ce-li-tax {
  font-size: 10px;
  color: var(--muted);
  margin-top: 2px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
#sub-ops-counterparty .ce-list-empty {
  padding: 20px;
  text-align: center;
  color: var(--muted);
}

/* ── Detail pane ────────────────────────────────────────────────────────── */
#sub-ops-counterparty .ce-detail-pane {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 18px;
  overflow-y: auto;
}
#sub-ops-counterparty .ce-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  color: var(--muted);
}

#sub-ops-counterparty .ce-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 12px;
  margin-bottom: 16px;
}
#sub-ops-counterparty .ce-detail-name-block h3 {
  margin: 0 0 6px 0;
  font-size: 18px;
  color: var(--text);
}

#sub-ops-counterparty .ce-badges {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
#sub-ops-counterparty .ce-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 500;
}
#sub-ops-counterparty .ce-badge-warn {
  background: rgba(240,136,62,0.12);
  color: var(--orange);
  border: 1px solid rgba(240,136,62,0.30);
}
#sub-ops-counterparty .ce-badge-info {
  background: rgba(88,166,255,0.12);
  color: var(--blue);
  border: 1px solid rgba(88,166,255,0.30);
}
#sub-ops-counterparty .ce-badge-neutral {
  background: rgba(255,255,255,0.04);
  color: var(--muted);
  border: 1px solid var(--border);
}

#sub-ops-counterparty .ce-detail-meta {
  font-size: 11px;
  color: var(--muted);
  text-align: right;
  line-height: 1.6;
}
#sub-ops-counterparty .ce-meta-row span { color: var(--muted); }

/* ── Summary stat grid (24m TL/USD/EUR/Rows/Share/Last) ─────────────────── */
#sub-ops-counterparty .ce-summary-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 8px;
  margin-bottom: 18px;
}
#sub-ops-counterparty .ce-stat {
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px 10px;
}
#sub-ops-counterparty .ce-stat-label {
  font-size: 10px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}
#sub-ops-counterparty .ce-stat-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  margin-top: 2px;
}

/* ── Section blocks ─────────────────────────────────────────────────────── */
#sub-ops-counterparty .ce-block {
  margin-bottom: 18px;
}
#sub-ops-counterparty .ce-block h4 {
  font-size: 13px;
  margin: 0 0 8px 0;
  color: var(--text);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}
#sub-ops-counterparty .ce-row-2col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

/* ── Tables (the previously unreadable parts) ───────────────────────────── */
#sub-ops-counterparty .ce-table {
  width: 100%;
  font-size: 12px;
  border-collapse: collapse;
  background: transparent;
}
#sub-ops-counterparty .ce-table th,
#sub-ops-counterparty .ce-table td {
  padding: 7px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  color: var(--text);
}
#sub-ops-counterparty .ce-table th {
  color: var(--muted);
  font-weight: 600;
  background: rgba(255,255,255,0.02);
  text-transform: uppercase;
  font-size: 10.5px;
  letter-spacing: 0.4px;
}
#sub-ops-counterparty .ce-table tr:hover td {
  background: rgba(255,255,255,0.02);
}
#sub-ops-counterparty .ce-table td.num,
#sub-ops-counterparty .ce-table th.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
#sub-ops-counterparty .ce-empty-cell {
  color: var(--muted);
  font-style: italic;
}

/* ── Quality strip ──────────────────────────────────────────────────────── */
#sub-ops-counterparty .ce-quality-strip {
  display: flex;
  gap: 24px;
  font-size: 12px;
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--border);
  padding: 10px 14px;
  border-radius: 4px;
  color: var(--text);
}
#sub-ops-counterparty .ce-q-label { color: var(--muted); }

/* ── Monthly trend chart ────────────────────────────────────────────────── */
#sub-ops-counterparty .ce-chart {
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--border);
  border-radius: 4px;
  min-height: 140px;
  padding: 8px;
}
#sub-ops-counterparty .ce-svg {
  width: 100%;
  height: 140px;
}
#sub-ops-counterparty .ce-bar {
  fill: var(--blue);
  opacity: 0.85;
}
#sub-ops-counterparty .ce-bar:hover { opacity: 1; }
#sub-ops-counterparty .ce-grid {
  stroke: var(--border);
  stroke-width: 1;
  opacity: 0.5;
}
#sub-ops-counterparty .ce-axis-label {
  font-size: 9px;
  fill: var(--muted);
  font-family: -apple-system, sans-serif;
}

/* ── Mode badge (M2.1 v1.1, dark theme) ─────────────────────────────────── */
#sub-ops-counterparty .ce-badge-mode {
  background: rgba(88,166,255,0.12);
  color: var(--blue);
  border: 1px solid rgba(88,166,255,0.30);
}

/* ── Responsive ─────────────────────────────────────────────────────────── */
@media (max-width: 1200px) {
  #sub-ops-counterparty .ce-row-2col { grid-template-columns: 1fr; }
  #sub-ops-counterparty .ce-summary-grid { grid-template-columns: repeat(3, 1fr); }
  #sub-ops-counterparty .ce-layout { grid-template-columns: 280px 1fr; }
}
@media (max-width: 900px) {
  #sub-ops-counterparty .ce-layout { grid-template-columns: 1fr; }
  #sub-ops-counterparty .ce-summary-grid { grid-template-columns: repeat(2, 1fr); }
}

/* === END COUNTERPARTY EXPLORER (M2.1) === */'''

# Replace the old block (and the old "ce-badge-mode" addition that came right
# after the END marker) with the new self-contained block.
# We capture from START up to and including "background: #e7f5ff;" line if it
# exists, but more safely just replace [START..END_marker_inclusive].
new_css = css[:start_idx] + NEW_BLOCK + css[end_idx_full:]

# Also strip out the old detached ".ce-badge-mode" block that lives just after
# the original END marker (light-theme leftovers). It's typically:
#   /* === CE mode badge (M2.1 v1.1) === */
#   .ce-badge-mode { background: #e7f5ff; ... }
# We remove it because we re-defined .ce-badge-mode inside the scoped block.
import re
new_css = re.sub(
    r"\n+/\* === CE mode badge \(M2\.1 v1\.1\) === \*/\s*\.ce-badge-mode\s*\{[^}]*\}\s*",
    "\n",
    new_css,
    count=1,
)

CSS.write_text(new_css, encoding="utf-8")
print("  ✓ Counterparty CSS block replaced (dark theme, correct selectors)")


# ─────────────────────────────────────────────────────────────────────────
# 2. Cache buster on app.v5.js (CSS isn't versioned but JS is, so the
#    full page reload picks up CSS changes anyway). For peace of mind we
#    bump the JS version too.
# ─────────────────────────────────────────────────────────────────────────
print("\n[2/2] Updating cache buster on app.v5.js reference...")
INDEX = Path("dashboard/static/index.html")
import time as _time
ts = _time.strftime("%Y%m%d%H%M%S")
html = INDEX.read_text(encoding="utf-8")
new_html = re.sub(r'app\.v5\.js(\?[^"]*)?"', f'app.v5.js?v={ts}"', html)
if new_html != html:
    INDEX.write_text(new_html, encoding="utf-8")
    print(f"  ✓ cache buster updated to v={ts}")
else:
    print("  ⏭  no app.v5.js reference found")


print()
print("=" * 60)
print("Counterparty UI fix complete.")
print("=" * 60)
print()
print("What changed:")
print("  - All selectors moved from #section-counterparty (broken)")
print("    to #sub-ops-counterparty (correct).")
print("  - Light-theme colors replaced with dark-theme tokens")
print("    (var(--bg), --card, --border, --text, --muted, --blue, …).")
print("  - Tables (Purchase-side bucket split / Currency split / Top accounts /")
print("    Subtype split / Recent rows / Classification quality) now have")
print("    proper contrast, monospace alignment, hover states.")
print("  - Active list item gets a blue left-border accent.")
print("  - Mode badges (warn/info/neutral) use the global accent palette.")
print()
print("No backend / no uvicorn restart needed. Hard-refresh in browser.")
