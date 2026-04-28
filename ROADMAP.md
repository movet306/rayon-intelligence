# Rayon Intelligence — ROADMAP

> **Living document.** Last updated: 2026-04-28. Owner: Mert Ovet.
> Strategy: **breadth-first diagnostic uplift**, then second-pass deepening, then filter architecture, then enrichment.

---

## North Star

Move the whole platform from **descriptive** ("what happened") to **diagnostic** ("why it happened"), and eventually to **decision-supportive** ("what should we do"), in a disciplined order without scope creep.

Current state: **mostly descriptive.** Visual quality and basic numbers are in place; explainability and drill-down are not.

---

## Active work streams

| # | Stream | State | Next step |
|---|---|---|---|
| 1 | **Operations Intelligence (M2.x)** | M2.0 + M2.0.1 + M2.1 v1.1 done. Counterparty list <1s, detail pending bottleneck fix. | Diagnostic uplift, see § Operations Intelligence Plan |
| 2 | **Yarn Intelligence** | Phase 1 done (PES FDY/DTY + PA6/PA6.6). Phase 2 pending (cotton/blend/viscose/elastane). | Pause until M2 diagnostic uplift complete |
| 3 | **Price Intelligence** | v2 live. `build_price_signals.py` and `ice_cotton.py` not yet in GitHub Actions. | Ops fix — single workflow patch (see § Quick Wins) |
| 4 | **Tekstil Haber Botu v3** | Live, daily 08:00. textileworld.com 504 + zero-article issue under investigation. | Watch + fix when stable |
| 5 | **Counterparty Explorer perf** | Migration 014 (MV) done. List <1s ✓. Detail endpoint 28s ✗ (TRIM fix didn't address bottleneck). | profile_detail.py + fix (15-30 min) |
| 6 | **Platform deployment** | Local-only. Railway/Render not configured. | Defer to post-M2.x |
| 7 | **Supplier quote bank** | Empty. Manual entry pending. | Iterative, low priority |
| 8 | **Faz 2 learning roadmap** | In progress (Python AI → LLM → RAG → Agents). | Parallel, ~5h/week |

---

## Operations Intelligence Plan

### Maturity model

```
Level 1 — Descriptive       "what happened"           ← current state
Level 2 — Diagnostic        "why it happened"         ← M2.x target
Level 3 — Decision-support  "what should we do"       ← M3+ target
```

### Strategy: breadth-first uplift

Do NOT fully deepen one section before touching the others. Bring all 4 sections from Level 1 to Level 2 in a coordinated pass first. Then iterate.

### Section priority (rationale-backed)

| Order | Section | Why this rank |
|---|---|---|
| 1 | **Procurement** | Rayon's value chain starts here. Supplier dependency, fiber mix, FX exposure, bucket distribution all live here. |
| 2 | **Revenue Reality** | Core revenue, contra, customer concentration — direct decision drivers. |
| 3 | **Cost Structure** | Important but currently produces fewer direct actions. Logistics still provisional. Needs more context layers to mature. |
| 4 | **Overview** | Summarizes the others. Cannot intelligently summarize what isn't yet rich. |

### Section-level scope (Phase 1 = breadth uplift, Phase 2 = deepening)

#### M2.2 — Procurement Phase 1 *(first)*

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
- Fiber / material family mix (cotton / polyester / nylon / elastane / blend) — *conditional, depends on data inventory*

#### M2.3 — Revenue Reality Phase 1 *(second)*

**Goal:** Move Revenue Reality from "gross/net trend + flat table" to diagnostic.

**Adds:**
- Contra % trend chart (separate from gross-vs-net)
- Customer concentration trend chart (top 1 / top 3 / top 10 share over time)
- Returns vs discounts split (separate metric and trend)
- Top customer table enrichment: share_of_total_12m %, last_invoice_date, trend direction, YoY change
- Row-click → Counterparty Explorer detail drawer (sales mode)
- KPI strip additions: contra % of gross, top customer share %, FX-invoiced revenue share, secondary service revenue separated
- Top contra-driving customers table
- Concentration risk badge (e.g. "Top 1 customer = 22% — concentrated")

**Deferred to Revenue Reality Phase 2:**
- Customer-by-bucket table (requires filter architecture)
- Largest returns / discounts detail tables
- Lost / new customer alerts

**Conditional (pending data inventory — NOT committed to M2.x):**
- Country breakdown (Eastern Europe / ME / Caucasus / RU / UA) — push to M3 enrichment if not reliably present in current Nebim layer
- Export status (domestic vs export — physical shipment direction, not FX) — same condition
- Knit vs woven product split — same condition

#### M2.4 — Cost Structure Phase 1 *(third)*

**Goal:** Move Cost Structure from "stacked area only" to diagnostic.

**Adds:**
- Cost share % chart over time (alongside absolute TL)
- Top supplier per cost bucket table (utilities → AKSA + MARMARA, fason → ?, factory overhead → ?)
- Bucket-as-%-of-total context line in each KPI
- Top change drivers strip (biggest movers this month with reason hint)
- Volatility flag — when single-month YoY exceeds threshold (e.g. Maintenance YoY -75.6% should show ⚠ volatile-line marker)
- Convert "logistics_distribution provisional" note from passive disclaimer to active local toggle: *Include provisional logistics: on/off* — this is the only Phase-1-acceptable filter (special case justified by data quality, not scope)

**Deferred to Cost Structure Phase 2:**
- Utilities sub-detail (electricity / gas / fuel / water) — depends on account-level breakdown availability
- Fason sub-detail (boyama / baskı / laminasyon / kaplama) — depends on text/account mapping
- Bucket drilldown panel

#### M2.5 — Overview Refinement *(fourth)*

**Goal:** Promote Overview from KPI wall to executive intelligence summary. Done last because it summarizes the deeper sections.

**Adds:**
- Top change drivers strip (3 biggest procurement movers, 3 biggest revenue movers, 3 biggest cost movers — last completed month)
- Anomaly strip (elevated contra, unusual concentration, unusual maintenance dip/spike, review-heavy parties)
- Narrative insight block (rule-based, no LLM required initially) — example: *"Latest complete month: 2026-03. Procurement remained concentrated in greige fabric and yarn. Net revenue softened mainly due to elevated contra revenue. Utilities stayed elevated but within recent range."*
- 2-3 mini sparkline trends embedded in KPI cards
- Trim KPI count — keep only the most signal-bearing ones (executive summary, not data dump)
- Cross-link KPI cards to corresponding sections

**Overview principle:** stay sparse. No local controls. No tables. Global filters apply but no in-section filters.

#### M2.6 — Phase 2 deepening pass *(after Phase 1 complete across all sections)*

Second-pass deepening of all four sections, picking up the deferred items above. Order matches Phase 1 order.

#### M2.7 — Filter architecture *(deliberately last)*

**Why last:** filter architecture is cross-cutting. Building it before sections stabilize causes endpoint contract churn. Sections must reach diagnostic maturity first; their query shape must be clear before global+local filtering layers around them.

**Phase 1 exception:** trivial local interactions (row click, in-table search) are acceptable, but the actual filter system (global state, URL-bound filters, backend filter parameter standardization) is built here as one coordinated piece.

**Architecture:**

*Global filters (apply to all sections):*
- Date range
- Currency basis (TL / USD / EUR / all)
- Side scope (purchase / sales / all)
- Counterparty verification (verified / no-tax / all)
- Review flag (all / review only)
- Core relevance (all / core-business / cost-model)

*Local filters per section:*
- Procurement: bucket, subtype, supplier, account prefix
- Cost: bucket, supplier, account code, provisional logistics toggle (already added in Phase 1)
- Revenue: customer, revenue bucket, subtype, contra-only toggle, include/exclude secondary service revenue
- Counterparty: mode (supplier/customer), search, verified-only, min spend threshold

**Discipline rule:** every dropdown that exists in the UI must affect the backend query. No cosmetic controls.

---

## Visualization principles (apply to every section)

1. **Pattern per section:** KPI strip → trend chart → mix/share chart → ranked table → row-click drill drawer
2. **Absolute AND relative:** every section shows both absolute TL and share % views — totals can grow while mix shifts
3. **"Why" layer mandatory:** every panel must answer not just "what" but "why" — top movers / driver strips / volatility flags
4. **Alerts only for real anomalies:** contra anomaly is a true alert; routine KPIs are not. Avoid alert fatigue.
5. **Drilldown is real:** clicking a row opens detail with backend-fetched data. No static expandable rows. No fake interactivity.

---

## Quick Wins (low-effort, high-leverage — do opportunistically)

| Task | Effort | When |
|---|---|---|
| Add `build_price_signals.py` to GitHub Actions daily workflow | 15 min | Today/this week |
| Add `ice_cotton.py` to GitHub Actions | 10 min | Today/this week |
| Add `REFRESH MATERIALIZED VIEW dim_counterparty_mv` to GitHub Actions (after build_price_metrics step) | 15 min | Today/this week |
| profile_detail.py to find Counterparty detail endpoint bottleneck | 15 min | Today |
| Fix detail endpoint bottleneck (likely single index or query rewrite) | 15-60 min | Today |

---

## Out of scope for M2.x

These are **explicitly deferred** to keep M2.x focused:

- **Account Explorer** (M3) — was originally floated as M2.2, now deferred until Counterparty Explorer accumulates 1+ week of real usage
- **Country / region breakdown** (M3 enrichment) — conditional on data inventory
- **Knit vs woven product split** (M3 enrichment) — conditional on data inventory
- **Forecast / projection** (M3) — historical-only for now
- **Print / PDF export** (M3) — no executive-print flow yet
- **CSV / Excel export from tables** (M3) — assess demand from real usage
- **Annotations / event markers** (M3) — manual notation layer over time-series
- **Cross-tenant / multi-entity** (out of scope) — single company use case only
- **Platform cloud deployment** — local until M2.x stabilizes; deploy after Phase 2 complete

---

## Discipline rules (anti-scope-creep)

These rules govern future scope decisions. When in doubt, refer here.

1. **Breadth before depth.** Phase 1 across all sections before any Phase 2 work.
2. **Filter architecture is one coordinated piece** — built last, not piecemeal.
3. **Conditional features stay conditional** until data inventory proves the field exists and is reliable.
4. **No new sections** before the existing four reach diagnostic maturity.
5. **Every UI control must be backend-effective.** No cosmetic dropdowns.
6. **Decision points get logged** in this ROADMAP.md as a one-line update (e.g. "2026-04-28: revised CE-NS-3 — promoted dim_counterparty to MV based on 4.9s+ usage data").
7. **Performance bottlenecks block feature work** — fix the slow path before adding features that depend on it. (Example: detail endpoint 28s blocks any drill-down work.)

---

## Decision log (running)

- **2026-04-27** — M2.1 v1.1 bug-confidence pass complete. 4 fixes (loading title, tax id `.0` strip, currency labels, mode badge).
- **2026-04-28** — Migration 013 (view query refactor): 24s → 4.9s. Insufficient.
- **2026-04-28** — Migration 014 (MV + indexes): list <1s ✓. CE-NS-3 plain-VIEW decision revised to MV based on usage evidence.
- **2026-04-28** — Detail endpoint TRIM fix corrected a data correctness bug but did not resolve 28s latency. Bottleneck pending teşhis.
- **2026-04-28** — ROADMAP.md established. Diagnostic uplift order: Procurement → Revenue Reality → Cost Structure → Overview. Filter architecture deferred to M2.7. Country/knit-woven marked conditional.
- **2026-04-28** — Migration 015: `v_top_suppliers_overall` enriched with share_pct, trend_direction, vergi_numarasi, is_verified, name_variants_count.
- **2026-04-28** — M2.2.1 Top Suppliers table enrichment shipped. EKİN DOKUMA share visible at 17.47% with ▲ trend; top 3 concentration ~33%. Diagnostic seviyeye ilk geçiş.
- **2026-04-28** — Procurement Phase 1 broken into M2.2.1–M2.2.7 micro-iterations. M2.2.7 (drawer) gated on M2.2.6 (detail endpoint bottleneck fix) per discipline rule #7.

---

## Today's plan (2026-04-28)

**Block 1 (30 min) — Quick wins:**
- profile_detail.py + diagnose Counterparty detail endpoint bottleneck
- Fix the slow query (likely 1-2 line index or rewrite)

**Block 2 (60 min) — Infrastructure:**
- Add `build_price_signals.py` to GitHub Actions
- Add `ice_cotton.py` to GitHub Actions
- Add `REFRESH MATERIALIZED VIEW dim_counterparty_mv` to GitHub Actions
- Commit ROADMAP.md to repo

**Block 3 (rest of day) — M2.2 Procurement Phase 1 (in progress):**
- ✅ M2.2.1 Top Suppliers table enrichment (Migration 015 + endpoint + UI)
- ▢ M2.2.2 KPI strip
- ▢ M2.2.3 Chart 2 — Mix % over time
- ▢ M2.2.4 Chart 3 — Concentration trend
- ▢ M2.2.5 Chart 4 — Currency composition
- ▢ M2.2.6 Detail endpoint bottleneck fix (prerequisite for drawer)
- ▢ M2.2.7 Row-click drawer

**Stop criterion for today:** as much of M2.2.2 → M2.2.5 (KPIs + 3 charts) as energy allows, then M2.2.6 bottleneck fix, then M2.2.7 drawer if time permits. Breadth over depth — tomorrow Revenue Phase 1 if Procurement Phase 1 complete.

---

*End of ROADMAP.md — update this file whenever scope, priority, or decision changes.*
