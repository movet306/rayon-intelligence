# Price Intelligence — Roadmap & Data Safety Map

**Owner:** Mert Ovet
**Created:** 2026-04-29
**Last updated:** 2026-04-29
**Status:** Active — locked after collaborative review with Claude + ChatGPT

---

## Purpose

The Price Intelligence section of the Rayon Intelligence platform is currently a strong **early-warning radar** for Chinese upstream commodity movements that propagate to Turkish supplier offers with a 4–12 week lag. This document is the locked roadmap to evolve it from a *radar* into a **Rayon-specific procurement cockpit** — adding signal discipline, Rayon relevance scoring, supplier quote linkage, and lag calibration on top of the existing benchmark feed.

**Guiding principle:** Do not turn this into a broader news page. Keep it a procurement and cost-pressure intelligence tool.

---

## PI-0 — Data Safety Map (Read Before Any Refactor)

We deliberately waited weeks for daily price observations to accumulate. The historical time-series is now the platform's most valuable asset — **827 rows across 251 days** in `price_metrics_daily` alone. Losing it during a refactor would destroy signal quality, trend meaning, and lag analysis value.

### Protected (never DROP, TRUNCATE, overwrite, or recreate)

These tables hold accumulated daily observations. **Append-only.** Schema changes must be backward-compatible (add columns, do not remove).

| Table | Rows | Date span | Why protected |
|---|---|---|---|
| `price_metrics_daily` | 827 | 2024-10-28 → 2026-04-29 (251 days) | Core daily price series — 18 months of history |
| `price_signals` | 827 | (date column TBD) | Daily signal output, full history needed for backtesting |
| `price_intelligence_signals` | 38 | 2026-04-21 → 2026-04-29 (9 days) | New signal layer, but already accumulating |
| `price_chain_spreads` | 275 | (date column TBD) | Chain spread time series |
| `fact_purchase_lines_clean` | 60,768 | (audit data) | Cleaned purchase invoice history — irreplaceable |
| `fact_sales_lines_clean` | 50,589 | (audit data) | Cleaned sales invoice history — irreplaceable |

### Append-only scripts (must remain idempotent)

These scripts write into protected tables. Any change must preserve append-safety: re-running the same day must not duplicate rows.

- `scrapers/sunsirs_prices.py` → `price_metrics_daily`
- `scrapers/ice_cotton.py` → `price_metrics_daily`
- `scripts/build_price_signals.py` → `price_signals`
- `scripts/price_signals.py` (or successor) → `price_intelligence_signals`
- (planned) `scrapers/usda_ams_cotton.py` → `price_metrics_daily`

### Rebuildable (safe to recreate)

These are derived. Drop and rebuild from protected sources whenever needed.

- All `v_*` views (29 currently): `v_contra_anomaly_detail`, `v_cost_kpis`, `v_cost_movers`, `v_customer_concentration_trend`, `v_kpi_latest_month`, `v_monthly_cost_structure`, `v_monthly_procurement_by_bucket`, `v_monthly_procurement_by_currency`, `v_monthly_revenue_core`, `v_overview_signals`, `v_procurement_concentration_trend`, `v_procurement_kpis`, `v_revenue_kpis`, `v_top_cost_suppliers_overall`, `v_top_customers_by_bucket`, `v_top_customers_overall`, `v_top_suppliers_by_bucket`, `v_top_suppliers_overall`, `dim_counterparty` (view)
- Any `mv_*` materialized views (refresh, do not destroy underlying tables)

### To be populated (currently 0 rows — not protected, not rebuildable yet)

These tables have schema but no data. Populating them is part of PI-2 / PI-3 / PI-4 / PI-5.

- `dim_material` (0) — populated in PI-2 (Rayon relevance scoring)
- `dim_price_source` (0) — populated in PI-3.2 (source tier kolonu)
- `dim_yarn_master` (0) — Yarn Master Phase 1 (separate track)
- `dim_yarn_price_driver` (0) — Yarn Master Phase 1
- `dim_yarn_label_alias` (0) — Yarn Master Phase 1
- `lkp_yarn_taxonomy` (0) — needs (re)load
- `dim_business_bucket` (29) — populated, supplier classification
- `dim_classification_version` (1) — populated
- `fact_supplier_quotes` (0) — populated in PI-4 (supplier crosswalk)
- `fact_yarn_price_pressure` (0) — Yarn Master Phase 1 output

### Migration rules (non-negotiable)

1. **Schema changes must be additive.** Add columns; do not remove. If a column must be retired, mark deprecated and stop writing to it, but do not drop until at least 90 days have passed.
2. **No `TRUNCATE`, no `DROP TABLE`** on any Protected table. Period.
3. **No `DELETE FROM <protected>`** without explicit row-level WHERE clause and pre-delete row count check.
4. **All transforms run on copies.** If a refactor needs to reshape data, write the new shape to a new table or view, then cut over reads, then keep old table as backup for 30 days minimum before considering removal.
5. **Backups before risk.** Before any structural change, run `pg_dump` of affected tables. Backup file path documented in commit message.
6. **Idempotent writes.** Scrapers and signal builders must use `INSERT ... ON CONFLICT DO NOTHING` or equivalent so re-running a day's job never duplicates data.

---

## Roadmap Phases

### PI-1 — Cleanup & Signal Discipline (1 week)

Goal: make the existing feed legible and consistent. No new data sources, no new logic — just discipline.

| # | Task | Status |
|---|---|---|
| 1.1 | **Signal deduplication.** Same (material_key, signal_type) within 7-day window collapses to a single card. UI uses `DISTINCT ON` on most recent. | TODO |
| 1.2 | **HIGH IMPACT KPI bug.** Top-strip "HIGH IMPACT (7D): 0" contradicts feed showing YÜKSEK signals. Fix severity terminology mapping (Türkçe ↔ English). | TODO |
| 1.3 | **Action / Watch / All three-tier feed.** Action: max **3** cards. Watch: max **5**. All: rest, collapsible. Near-duplicate clustering mandatory. | TODO |
| 1.4 | **Signal card evolution.** Add three elements per card: timestamp, "why this matters to Rayon" one-liner, source hierarchy badge (🟢 Benchmark / 🟡 Directional / 🟠 Weak Proxy — hardcoded mapping in this phase). | TODO |
| 1.5 | **Polyester chain chart fix (visual stabilization).** Added PTA line (teal, distinct from DTY). Aligned all series x-axis to common start. Removed MA7 dashed ghost traces. Moved sigma into chain-flow node footers. Hid redundant detail cards (HTML preserved, display:none). Hid rangeslider strip. **Topology correction (linear chain misrepresents staple/filament branches) split out as PI-1.5b.** | DONE |
| 1.6 | **Cotton panel split.** SunSirs Çin Spot and ICE Vadeli into two separate cards with independent y-axes. The "different markets" warning must match the visual layout. | TODO |
| 1.7 | **Nylon panel.** Extend date range to match other panels (currently only Apr 9–27). Highlight active signals (e.g. Adipic Acid -6.5%) with chart annotation. | TODO |
| 1.8 | **Materials summary table.** Category groups (POLYESTER ZİNCİRİ / PAMUK / NAYLON / DİĞER) with sub-headers. Sortable columns. Replace empty "30G%" / "Trend" cells with "(insufficient history)" placeholder. | TODO |
| 1.9 | **Section title rename.** "Price Intelligence" → "Raw Material Price Intelligence" (more accurate scope). | TODO |


### PI-1.5b — Polyester Chain Topology Correction (1 day)

**Why this is a separate phase:** the current chain visualization (PTA → PSF → FDY → POY → DTY in a single line) is technically incorrect. PSF is the staple branch; POY/FDY/DTY are filament branches. PSF is not the upstream of FDY, and POY does not feed FDY. Forcing all five into a fake linear chain misrepresents the underlying chemistry to anyone who reads the dashboard.

**Industrially correct topology:**
```
                ┌─→ PSF                           (staple branch)
PTA → polymer ──┤
                └─→ POY → DTY  (filament branch, with FDY as parallel filament product)
```

**Scope:**

| # | Task | Status |
|---|---|---|
| 1.5b.1 | Replace linear `POLY_CHAIN` array with a branched structure that the renderer understands. | TODO |
| 1.5b.2 | Update `_renderChainFlow` to draw two branches under PTA: staple (PSF) and filament (POY → DTY). FDY rendered as a parallel reference node alongside the filament branch, not as a downstream step. | TODO |
| 1.5b.3 | Update section title from "Polyester Zinciri — PTA → PSF → FDY → POY → DTY" to a topology-accurate string (e.g. "Polyester Chain — Staple & Filament"). | TODO |
| 1.5b.4 | Update legend ordering in chart so it reflects branch grouping rather than the false linear sequence. | TODO |
| 1.5b.5 | Update `CHAIN_UPSTREAM` mapping to match the corrected topology (PSF and POY both point to PTA; DTY points to POY; FDY points to PTA as a parallel filament product). | TODO |

**Out of scope:**
- Adding a "polymer/melt" intermediate node. We don't have data for it; inserting a dummy node would introduce a different kind of misrepresentation.
- Changing the underlying spread / divergence calculations. Those are already pair-based (FDY−PSF, DTY−POY) and remain valid.

**Reversal:** revert `POLY_CHAIN` and `CHAIN_UPSTREAM` to their pre-1.5b state; revert `_renderChainFlow` to the linear loop.

### PI-2 — Rayon Relevance Engine (1–2 weeks)

Goal: turn a generic commodity dashboard into a Rayon-specific one. After this phase, the page no longer wastes attention on materials Rayon does not buy.

| # | Task | Status |
|---|---|---|
| 2.1 | **`dim_material.rayon_relevance` column.** Values: `direct` (Rayon ordered in last 12 months) / `indirect` (upstream of direct) / `low` (not used). Source: derived from `fact_purchase_lines_clean` + manual seed file. | TODO |
| 2.2 | **Signal card extension.** Each card gains: affected Rayon category, likely Turkish supplier(s) impacted, action verb (BUY NOW / NEGOTIATE / MONITOR / WAIT), confidence. | TODO |
| 2.3 | **KPI strip.** "HIGH IMPACT (7D)" → "HIGH IMPACT FOR RAYON (7D)" — relevance-filtered. | TODO |
| 2.4 | **Default sort in summary table:** rayon_relevance → severity → recency. | TODO |
| 2.5 | **Action verb dictionary.** Map signal type → recommended verb. Cost decrease → NEGOTIATE. Cost increase + chain mismatch → BUY NOW / LOCK PRICING. Cost increase, not yet reflected → MONITOR + REQUEST QUOTES. Spread compression → STRATEGIC WATCH. | TODO |

### PI-4-skeleton — Supplier Crosswalk Minimum (2–3 days)

Goal: pulled forward from full PI-4. Enough linkage to make every signal Rayon-aware, without building full pass-through analytics yet.

| # | Task | Status |
|---|---|---|
| 4s.1 | **`v_supplier_material_index` view.** JOIN `fact_purchase_lines_clean` × `dim_material` × `dim_counterparty`. Output: per-material → list of suppliers with last purchase date, last unit price, last currency. | TODO |
| 4s.2 | **Signal card supplier reference line.** "Senin son alımın: KORTEKS @ $2,450/ton, 11 hafta önce." One line, no analytics — just context. | TODO |

**Explicitly out of scope for skeleton (deferred to PI-4-full):**
- Pass-through analytics view
- Negotiation opportunity flag
- Lag backtest computation
- Full recommendation engine

### PI-3 — Source Stack Upgrade (1 week)

Goal: harden the data layer with a free public validation source for cotton and a formal source hierarchy.

| # | Task | Status |
|---|---|---|
| 3.1 | **USDA AMS Cotton Market News scraper.** Free, official, daily. Validates ICE futures with physical market data. Writes to `price_metrics_daily` with source tag. | TODO |
| 3.2 | **`dim_price_source.tier` column** (formal). Values: `benchmark` / `directional` / `weak_proxy`. Replaces the hardcoded mapping from PI-1.4. | TODO |
| 3.3 | **ICIS evaluation note** (in this doc): ICIS premium source, ~$10K+/year estimated. Not justified at current platform maturity. **Re-evaluate after 6 months** — only if all of: (a) platform is in active daily use, (b) procurement decisions are demonstrably shaped by it, (c) supplier benchmark debates would benefit from premium third-party reference. | TODO |
| 3.4 | **Frankfurter FX** (already used) documented as Tier-1 in source hierarchy. | TODO |

### PI-4-full — Supplier Pass-through Intelligence (1–2 weeks)

Goal: this is the highest-value phase. The page becomes prescriptive — telling Rayon when to negotiate, not just what is moving.

| # | Task | Status |
|---|---|---|
| 4f.1 | **`v_supplier_passthrough` view.** Joins China benchmark moves with Turkish supplier quote/invoice changes. Computes realized lag in weeks. Compares to historical norm. | TODO |
| 4f.2 | **`v_negotiation_opportunities` view.** Daily flag: signals where benchmark moved, lag exceeded, but supplier quote unchanged → negotiation candidate. | TODO |
| 4f.3 | **Signal card pass-through context.** "China DTY -3.2% (7d). Your last KORTEKS quote: Feb 14. Historical lag: 6–8 weeks. This move should already be reflected. NEGOTIATE." | TODO |

### PI-5A — Calibration (2 weeks)

| # | Task | Status |
|---|---|---|
| 5A.1 | **TR lag backtesting.** Use `fact_purchase_lines_clean` (60,768 rows) to compute per-material actual lag distribution. Replace hardcoded "4–8 hf" with calibrated bands. | TODO |
| 5A.2 | **PA6 / PA66 sub-chain split.** Separate visual + signal logic for the two nylon families (currently mixed). | TODO |
| 5A.3 | **Viscose / rayon coverage strengthening.** Mismatch with company name. Add SunSirs viscose staple (if available), expand viscose-yarn coverage. | TODO |

### PI-5B — Expansion (1 month)

| # | Task | Status |
|---|---|---|
| 5B.1 | **Blend cost models.** PV (PE/Visc), PE/Cotton, Elastane blends. Weighted-average driver costs. New material types in UI. | TODO |
| 5B.2 | **`fact_action_log` table + UI.** Log: which signal seen, what action taken, what outcome. Closes the learning loop. | TODO |
| 5B.3 | **Historical percentile context.** Per signal: "this move is in the 87th percentile of last 2 years." | TODO |
| 5B.4 | **Forecast layer.** Simple pass-through coefficient model: PTA → DTY 4–8 week projection. | TODO |

---

## Sequencing

```
PI-0  Data Safety Map        ── DONE
   ↓
PI-1  Cleanup                ── in progress
       1.1 Signal dedup           ── DONE
       1.2 KPI strip               ── DONE
       1.5 Polyester chart visual  ── DONE
       1.5b Polyester topology     ── ~1 day (new)
       1.3, 1.4, 1.6–1.9          ── ~3-4 days
   ↓
PI-2  Rayon Relevance        ── 1–2 weeks
   ↓
PI-4-skeleton                ── 2–3 days  (high leverage, pulled forward)
   ↓
PI-3  Source Stack           ── 1 week
   ↓
PI-4-full Pass-through       ── 1–2 weeks (highest value)
   ↓
PI-5A Calibration            ── 2 weeks
   ↓
PI-5B Expansion              ── ~1 month
```

**Estimated total:** 8–10 weeks linear, 6–7 weeks with parallel work where possible.

**Value inflection point:** PI-4-skeleton. After ~4–5 weeks the platform stops being a generic commodity dashboard and starts being a Rayon-specific procurement cockpit. Everything after PI-4-skeleton is depth and refinement.

---

## Decision Log

- **2026-04-29:** ICIS deferred. Internal supplier quote bank prioritized over premium external benchmark. Re-evaluate in 6 months.
- **2026-04-29:** PI-4-skeleton pulled forward (originally planned as part of PI-4-full). Reason: supplier crosswalk is the single highest-leverage feature; even a thin version transforms every signal card.
- **2026-04-29:** PI-5 split into 5A (calibration) and 5B (expansion). Original PI-5 was too broad to be a single phase.
- **2026-04-29:** Action / Watch / All caps locked at 3 / 5 / unlimited. Near-duplicate clustering mandatory.
- **2026-04-29:** PI-1.2 (KPI strip) and PI-1.1 (signal dedup) shipped (commits `6ccc00b`, `dbb5794`). Feed reduced from 30+ duplicate cards to 9 distinct patterns; KPI strip now scoped to Price Intelligence with correct data source.
- **2026-04-29:** PI-1.5 closed as **visual stabilization** only. Topology correction split out into new sub-phase PI-1.5b. Reason: the chart-order issue (linear chain misrepresents staple vs filament branches) is a modeling problem, not a polish problem, and trying to fold it into PI-1.5 would have been scope creep.
