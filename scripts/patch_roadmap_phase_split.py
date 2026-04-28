"""
Patch ROADMAP.md — make Procurement Phase 1 / Phase 2 split explicit.
Adds the M2.2.x micro-iteration breakdown and today's progress to the
Decision log + Today's plan sections.
"""
from pathlib import Path

ROADMAP = Path("ROADMAP.md")
text = ROADMAP.read_text(encoding="utf-8")

bak = ROADMAP.with_suffix(".md.bak_phase_split")
if not bak.exists():
    bak.write_text(text, encoding="utf-8")
    print(f"Backup: {bak}")


# 1. Replace the M2.2 section block with a more granular Phase 1 / Phase 2 split

OLD_BLOCK = """#### M2.2 — Procurement Phase 1 *(first)*

**Goal:** Move Procurement from "stacked bar + flat table" to a diagnostic surface.

**Adds:**
- Procurement mix % over time chart (alongside the existing absolute TL chart) — exposes mix shift while totals grow
- Supplier concentration trend chart (top 1 / top 3 / top 10 share over time)
- Currency composition strip (TRY / USD / EUR invoicing mix)
- Top supplier table enrichment:
  - share_of_total_12m %
  - last_invoice_date
  - trend direction (up/down/flat indicator or sparkline)
  - verification / no-tax / drift badges (already in Counterparty Explorer logic)
- Row-click → opens Counterparty Explorer detail drawer (cross-section navigation, reuses existing endpoint)
- KPI strip additions: Top 3 supplier share %, FX-invoiced share %, yarn share, greige share, active supplier count, largest monthly increase/decrease

**Deferred to Procurement Phase 2:**
- Top suppliers by selected bucket (requires bucket dropdown — deferred to filter architecture)
- Variance drivers panel
- Fiber / material family mix (cotton/polyester/nylon/elastane/blend) — *conditional, depends on data inventory*"""

NEW_BLOCK = """#### M2.2 — Procurement Phase 1 *(first)*

**Goal:** Move Procurement from "stacked bar + flat table" to a diagnostic surface.

Broken into micro-iterations:

| ID | Item | Status |
|---|---|---|
| M2.2.1 | Top Suppliers table enrichment (share %, last invoice, trend ▲/▼/–, badges) | ✅ done 2026-04-28 |
| M2.2.2 | KPI strip additions (top 3 supplier share, FX-invoiced share, yarn share, greige share, active supplier count, largest monthly Δ) | pending |
| M2.2.3 | Chart 2 — Procurement mix % over time | pending |
| M2.2.4 | Chart 3 — Supplier concentration trend (top 1 / top 3 / top 10 share over time) | pending |
| M2.2.5 | Chart 4 — Currency composition (TRY / USD / EUR invoicing mix) | pending |
| M2.2.6 | Detail endpoint bottleneck fix (28s → <1s) — **prerequisite for drawer** | pending |
| M2.2.7 | Row-click → Counterparty Explorer detail drawer | pending |

**Discipline note:** M2.2.7 (drawer) does not start before M2.2.6 (bottleneck fix). Building a drawer over a 28s endpoint violates discipline rule #7 (performance bottlenecks block dependent feature work).

**Deferred to Procurement Phase 2 (M2.6) — NOT skipped, sequenced:**
- Top suppliers by selected bucket (requires real filter — couples to M2.7 filter architecture)
- Monthly variance drivers panel (biggest supplier movers, biggest bucket movers)
- Fiber / material family mix (cotton / polyester / nylon / elastane / blend) — *conditional, depends on data inventory*"""

if NEW_BLOCK in text:
    print("Already up-to-date.")
elif OLD_BLOCK not in text:
    print("ERROR: original M2.2 block not found.")
    raise SystemExit(1)
else:
    text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
    print("✓ M2.2 block updated with micro-iterations and Phase 2 deferred list")


# 2. Append decision log entries for today's progress

OLD_LOG_TAIL = "- **2026-04-28** — ROADMAP.md established. Diagnostic uplift order: Procurement → Revenue Reality → Cost Structure → Overview. Filter architecture deferred to M2.7. Country/knit-woven marked conditional."

NEW_LOG_ADDITION = """- **2026-04-28** — ROADMAP.md established. Diagnostic uplift order: Procurement → Revenue Reality → Cost Structure → Overview. Filter architecture deferred to M2.7. Country/knit-woven marked conditional.
- **2026-04-28** — Migration 015: `v_top_suppliers_overall` enriched with share_pct, trend_direction, vergi_numarasi, is_verified, name_variants_count.
- **2026-04-28** — M2.2.1 Top Suppliers table enrichment shipped. EKİN DOKUMA share visible at 17.47% with ▲ trend; top 3 concentration ~33%. Diagnostic seviyeye ilk geçiş.
- **2026-04-28** — Procurement Phase 1 broken into M2.2.1–M2.2.7 micro-iterations. M2.2.7 (drawer) gated on M2.2.6 (detail endpoint bottleneck fix) per discipline rule #7."""

if NEW_LOG_ADDITION in text:
    pass
elif OLD_LOG_TAIL in text:
    text = text.replace(OLD_LOG_TAIL, NEW_LOG_ADDITION, 1)
    print("✓ Decision log appended with today's milestones")
else:
    print("WARN: decision log tail not found, skipping log update")


# 3. Update Today's Plan section

OLD_TODAY = """**Block 3 (rest of day) — M2.2 Procurement Phase 1 start:**
- Backend: extend top-suppliers endpoint with new columns (share_of_total_12m, last_invoice_date, trend direction, badges)
- Frontend: enrich Top 10 Suppliers table
- Stretch: row-click → Counterparty drawer wiring

**Stop criterion for today:** Procurement table enriched and Counterparty drawer wired from row click. Mix % chart and concentration trend chart roll into tomorrow if energy/time runs out — no rush, breadth-first means tempo matters more than completeness within a single day."""

NEW_TODAY = """**Block 3 (rest of day) — M2.2 Procurement Phase 1 (in progress):**
- ✅ M2.2.1 Top Suppliers table enrichment (Migration 015 + endpoint + UI)
- ▢ M2.2.2 KPI strip
- ▢ M2.2.3 Chart 2 — Mix % over time
- ▢ M2.2.4 Chart 3 — Concentration trend
- ▢ M2.2.5 Chart 4 — Currency composition
- ▢ M2.2.6 Detail endpoint bottleneck fix (prerequisite for drawer)
- ▢ M2.2.7 Row-click drawer

**Stop criterion for today:** as much of M2.2.2 → M2.2.5 (KPIs + 3 charts) as energy allows, then M2.2.6 bottleneck fix, then M2.2.7 drawer if time permits. Breadth over depth — tomorrow Revenue Phase 1 if Procurement Phase 1 complete."""

if NEW_TODAY in text:
    pass
elif OLD_TODAY in text:
    text = text.replace(OLD_TODAY, NEW_TODAY, 1)
    print("✓ Today's plan updated with M2.2.x progress tracking")
else:
    print("WARN: today's plan section not found, skipping update")


ROADMAP.write_text(text, encoding="utf-8")
print("\nROADMAP.md updated.")
