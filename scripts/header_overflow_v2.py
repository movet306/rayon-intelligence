"""
M2.0.1 follow-up: header overflow fix v2.

The earlier defensive CSS targeted generic selectors (header, .top-cards) that
do not exist in this dashboard. The actual layout uses #header > .kpi-strip >
.kpi-card with fixed min-widths. The fix narrows the cards on narrow viewports
without changing the desktop look on wide screens.

Idempotent.
"""
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "dashboard" / "static" / "style.v5.css"

MARKER = "M2.0.1 header overflow v2"

CSS_FIX = """
/* ── M2.0.1 header overflow v2 ────────────────────────────────────────────
 * Real selectors this time. The header uses #header > .kpi-strip > .kpi-card
 * with min-width: 140px and padding: 8px 16px on each card. With four cards
 * plus the title and 28px container padding, the strip overflows on viewports
 * narrower than ~1300px. Fix: tighten kpi-card spacing globally and let the
 * strip wrap if the viewport is too narrow.
 */
#header {
  padding: 0 16px;       /* was 28px */
  gap: 16px;             /* was 24px */
  flex-wrap: nowrap;
  overflow: hidden;
}
.header-title {
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.kpi-strip {
  flex-shrink: 0;
  flex-wrap: nowrap;
}
.kpi-card {
  min-width: 0;          /* was 140px — let cards shrink if needed */
  padding: 6px 12px;     /* was 8px 16px */
  white-space: nowrap;
}
.kpi-card .kpi-value { font-size: 16px; }   /* was 18px */
.kpi-card .kpi-label { font-size: 9px; }    /* was 10px */
.kpi-card .kpi-sub   { font-size: 9px; }    /* was 10px */

@media (max-width: 1400px) {
  #header { padding: 0 12px; gap: 12px; }
  .kpi-card { padding: 6px 10px; }
}
@media (max-width: 1200px) {
  .kpi-card .kpi-sub { display: none; }
}
"""


def main():
    text = CSS.read_text(encoding="utf-8")
    if MARKER in text:
        print("Header overflow v2 already applied. Skipping.")
        return
    CSS.write_text(text.rstrip() + "\n\n" + CSS_FIX.lstrip() + "\n", encoding="utf-8")
    print("Header overflow v2 applied to style.v5.css.")
    print("Reload browser with Ctrl+F5 to see the change.")


if __name__ == "__main__":
    main()
