# P1 — Entity Refactor + Exposure Layer

**Design Document**

> **Version:** 1.0
> **Created:** 2026-05-11
> **Phase:** P1 (Phase E)
> **Status:** Design complete, ready for implementation
> **Estimated effort:** ~14 hours across 7 sub-steps
> **Prerequisites:** P0-A, P0-B, P0-C, P0-D complete ✅

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State vs Target State](#current-state-vs-target-state)
3. [Architectural Decisions](#architectural-decisions)
4. [Migration 010 — Entity Model](#migration-010--entity-model)
5. [Migration 011 — Exposure Layer Fields](#migration-011--exposure-layer-fields)
6. [Migration 012 — Entity Seed (23 entities)](#migration-012--entity-seed-23-entities)
7. [LLM Prompt Updates](#llm-prompt-updates)
8. [Python Code Changes](#python-code-changes)
9. [Backfill Strategy](#backfill-strategy)
10. [Rollout Sequence](#rollout-sequence)
11. [Testing Strategy](#testing-strategy)
12. [Risk Analysis & Rollback](#risk-analysis--rollback)
13. [Open Questions Resolved](#open-questions-resolved)
14. [Glossary](#glossary)

---

## Executive Summary

**Problem:** The current `companies` table treats every monitored organization as a `competitor`. This is structurally wrong because:

- **SASA** (TR upstream PTA/PET producer) is a *supplier*, not a competitor — its signals affect Rayon's cost, not market share
- **EURATEX** is an *association* whose signals indicate policy direction
- **ECHA** is a *regulator* whose signals are compliance-critical
- **TR garment buyers** are *customers* whose health drives Rayon's demand

Treating all of these as `competitor` makes the LLM analyzer's prompt misleading and the dashboard's signal categorization meaningless.

**Solution:** Rename `companies` → `entities` and add an `entity_type` enum that distinguishes 7 types. Add 7 REQUIRED exposure layer fields on `market_signals` so every signal explicitly answers *"who matters and how does Rayon get exposed?"*

**Outcome:** Market Signals dashboard transforms from "news monitor" to **"exposure intelligence layer"** — the original Phase E goal stated in roadmap v1.2.

---

## Current State vs Target State

### Current state (post-P0-B, 2026-05-11)

```
companies table
  ├── 32 rows
  └── all category = 'competitor' (structurally wrong)

market_signals table
  ├── 126 rows (post-P0-B cleanup, 0% NULL on category)
  ├── signal_category: REGULATORY|TRADE_POLICY|RAW_MATERIAL|TECHNOLOGY|
  │                    MARKET_DEMAND|COMPETITOR_MOVE|SUPPLY_CHAIN|
  │                    SUSTAINABILITY|OTHER
  ├── signal_priority_profile: COST|DEMAND|REGULATION|SUSTAINABILITY|EXPORT|OTHER
  ├── material_form: free text (FDY, PSF, etc.) + OTHER fallback
  └── affected_products: array, multi-value (woven/knit/technical/laminated)

Missing:
  - rayon_why_it_matters: zero structured explanation per signal
  - commercial_exposure_type: type of business exposure (export/raw_mat/regulation/sourcing)
  - affected_material_family: which fiber family is affected
  - entity_name + entity_role: who is the signal about
```

### Target state (post-P1)

```
entities table (renamed from companies)
  ├── 32 existing + 23 newly seeded = 55 rows total
  ├── entity_type enum (7 values + customer_account deferred to P4):
  │   - competitor       (TR + intl peers)
  │   - supplier         (upstream raw material)
  │   - benchmark_brand  (international peer for benchmarking)
  │   - association      (trade body)
  │   - regulator        (gov / regulatory)
  │   - market           (geography as entity)
  │   - customer_segment (aggregate customer type)
  └── geography column (separate from country, for market entities)

market_signals table
  ├── New REQUIRED fields:
  │   - rayon_why_it_matters: TEXT (1-sentence Rayon impact, mandatory)
  │   - affected_business_line: JSONB array (multi-value: woven/knit/technical/coated)
  │   - affected_material_family: JSONB array (multi: polyester/nylon/viscose/...)
  │   - commercial_exposure_type: enum (export/raw_material/competitor/regulation/sourcing)
  │   - entity_name: TEXT (named entity in signal)
  │   - entity_role: enum (matches entity_type)
  └── company_id renamed -> entity_id (FK to entities.id)
```

---

## Architectural Decisions

### Decision 1: Rename `companies` → `entities` (not new table)

**Why rename instead of new table:**
- Preserves all existing data (32 rows, FK relationships in market_signals.company_id)
- One atomic migration vs multi-step copy
- Old `companies` name kept as VIEW for backwards compat with any external readers

**Why "entities" name:**
- Captures that we now have non-company entities (markets, associations, regulators)
- Industry-standard term in BI/intelligence platforms
- Future-proof for `customer_account`, `event`, etc.

### Decision 2: `entity_type` enum (not free text)

**Why enum:**
- Validation at DB level (CHECK constraint)
- Predictable for LLM prompt
- Dashboard filter dropdown stays bounded

**7-value enum** (NOT 8 — `customer_account` deferred to P4):

| Type | When to use |
|---|---|
| `competitor` | Direct Rayon peer (similar product, similar customers) |
| `supplier` | Upstream raw material producer (yarn, fiber, chemical, dye) |
| `benchmark_brand` | International peer worth tracking for strategy/positioning |
| `association` | Trade body / industry lobby (İHKİB, EURATEX, TGSD) |
| `regulator` | Government body or compliance regulator (ECHA, EC, T.C. Tic.Bak) |
| `market` | Geography as monitorable entity (EU, Egypt, MENA) |
| `customer_segment` | Aggregate customer type (TR garment / EU brand / MENA trader) |

**Deferred to P4:** `customer_account` (individual named clients) — has commercial sensitivity, needs separate access control.

### Decision 3: Multi-value tags as JSONB arrays (ChatGPT gap #4)

**Why multi-value:** A regulation affecting *both* woven and technical lines simultaneously, or a fiber price move hitting *both* polyester and nylon blends — single-value fields force LLM to discard information.

**Why JSONB (not separate junction table):**
- Pragmatic: 95% of signals have ≤2 tags
- Query is `WHERE 'woven' = ANY(affected_business_line::jsonb)`
- No JOIN overhead in dashboard reads
- Junction table introduces 3x the migration complexity for marginal benefit

**JSONB array shape:**
```json
["woven", "technical"]                    // affected_business_line
["polyester", "nylon"]                    // affected_material_family
```

### Decision 4: `customer_segment` granularity (not individual accounts)

**Resolved from Open Question #2 in roadmap v1.2:**

Use **segment-level** aggregation for P1:
- `TR garment manufacturer`
- `EU brand / retailer`
- `MENA trader / distributor`
- `Russia / Ukraine wholesaler`
- `Caucasus distributor`

**Defer individual account tracking to P4** because:
- PII / commercial sensitivity concerns
- Customer-specific signals are rare (most news is at segment level)
- Account-level data already lives in `orders` + `lescon_sales` tables — different access pattern

### Decision 5: `signal_priority_profile` — single value (already deployed in P0-B)

**Resolved from Open Question #1 in roadmap v1.2:**
Confirmed single value (already shipped). The "primary priority dimension" is genuinely singular for most signals.

### Decision 6: Backwards compatibility via VIEW

```sql
CREATE VIEW companies AS
SELECT id, name, website, country, category, notes, created_at, updated_at
FROM entities
WHERE entity_type = 'competitor';  -- preserves old "all rows are competitors" semantics
```

This means:
- Old code reading `companies` keeps working (gets only competitor entities)
- Dashboard and scrapers can migrate to `entities` one at a time
- After full migration, drop the VIEW

---

## Migration 010 — Entity Model

**File:** `migrations/010_rename_companies_to_entities.sql`
**Estimated time:** 3 hours (migration + verification + scraper updates)

### SQL

```sql
-- Migration 010: Rename companies -> entities, add entity_type enum, geography column
-- Phase E P1 step 1/4

BEGIN;

-- 1. Rename table
ALTER TABLE companies RENAME TO entities;

-- 2. Add new columns
ALTER TABLE entities ADD COLUMN entity_type VARCHAR(30);
ALTER TABLE entities ADD COLUMN geography VARCHAR(50);
ALTER TABLE entities ADD COLUMN signal_priority_profile_default VARCHAR(20);

-- 3. Backfill entity_type from existing category
UPDATE entities SET entity_type =
    CASE category
        WHEN 'competitor' THEN 'competitor'
        WHEN 'customer'   THEN 'customer_segment'
        ELSE 'competitor'  -- safe default for unmapped
    END;

-- 4. Drop old category column (data preserved in entity_type)
ALTER TABLE entities DROP COLUMN category;

-- 5. Add CHECK constraint on entity_type
ALTER TABLE entities
ADD CONSTRAINT chk_entity_type
CHECK (entity_type IN (
    'competitor', 'supplier', 'benchmark_brand', 'association',
    'regulator', 'market', 'customer_segment'
));

-- 6. Make entity_type required for new rows
ALTER TABLE entities ALTER COLUMN entity_type SET NOT NULL;

-- 7. Rename market_signals.company_id -> entity_id
ALTER TABLE market_signals RENAME COLUMN company_id TO entity_id;

-- 8. Create backwards-compat VIEW (drop after all callers migrated)
CREATE OR REPLACE VIEW companies AS
SELECT id, name, website, country, notes, created_at, updated_at,
       'competitor'::VARCHAR(30) AS category
FROM entities
WHERE entity_type = 'competitor';

COMMIT;
```

### Verification queries

```sql
-- Should return 32 (all existing rows preserved)
SELECT COUNT(*) FROM entities;

-- Should return 32 (backwards-compat view works)
SELECT COUNT(*) FROM companies;

-- Should return all 32 as 'competitor'
SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type;
```

### Scraper updates required

After migration, search-and-replace in `scrapers/`:
- `FROM companies` → `FROM entities` (8+ occurrences across competitor_monitor.py, llm_analyzer.py, etc.)
- `company_id` → `entity_id` in INSERT/SELECT statements
- `companies.category` → `entities.entity_type`

Files affected (estimated):
- `scrapers/competitor_monitor.py` (~5 changes)
- `scrapers/llm_analyzer.py` (~7 changes)
- `dashboard/server.py` (~10 changes — many SQL queries)
- `dashboard/static/app.v5.js` (UI labels)

---

## Migration 011 — Exposure Layer Fields

**File:** `migrations/011_add_exposure_layer_fields.sql`
**Estimated time:** 2 hours

### SQL

```sql
-- Migration 011: Add exposure layer fields to market_signals
-- Phase E P1 step 2/4

BEGIN;

-- 1. Add new fields
ALTER TABLE market_signals ADD COLUMN rayon_why_it_matters TEXT;
ALTER TABLE market_signals ADD COLUMN affected_business_line JSONB DEFAULT '[]'::jsonb;
ALTER TABLE market_signals ADD COLUMN affected_material_family JSONB DEFAULT '[]'::jsonb;
ALTER TABLE market_signals ADD COLUMN commercial_exposure_type VARCHAR(20);
ALTER TABLE market_signals ADD COLUMN entity_name TEXT;
ALTER TABLE market_signals ADD COLUMN entity_role VARCHAR(30);

-- 2. CHECK constraint on commercial_exposure_type
ALTER TABLE market_signals
ADD CONSTRAINT chk_commercial_exposure_type
CHECK (commercial_exposure_type IS NULL OR commercial_exposure_type IN (
    'export', 'raw_material', 'competitor', 'regulation', 'sourcing', 'OTHER'
));

-- 3. CHECK constraint on entity_role (matches entity_type)
ALTER TABLE market_signals
ADD CONSTRAINT chk_entity_role
CHECK (entity_role IS NULL OR entity_role IN (
    'competitor', 'supplier', 'benchmark_brand', 'association',
    'regulator', 'market', 'customer_segment'
));

-- 4. CHECK constraint on JSONB arrays (must be arrays, not objects)
ALTER TABLE market_signals
ADD CONSTRAINT chk_affected_business_line_is_array
CHECK (jsonb_typeof(affected_business_line) = 'array');

ALTER TABLE market_signals
ADD CONSTRAINT chk_affected_material_family_is_array
CHECK (jsonb_typeof(affected_material_family) = 'array');

-- 5. Indexes for dashboard queries
CREATE INDEX idx_market_signals_entity_role ON market_signals(entity_role);
CREATE INDEX idx_market_signals_commercial_exposure ON market_signals(commercial_exposure_type);
CREATE INDEX idx_market_signals_business_line ON market_signals USING GIN (affected_business_line);
CREATE INDEX idx_market_signals_material_family ON market_signals USING GIN (affected_material_family);

COMMIT;
```

### Field semantics

| Field | Required? | Allowed values | Default |
|---|---|---|---|
| `rayon_why_it_matters` | ✅ (via Python validation) | TEXT, 1 sentence | `'Impact on Rayon unclear; flagged for review.'` |
| `affected_business_line` | ✅ multi-value | `['woven', 'knit', 'technical', 'coated', 'OTHER']` | `['OTHER']` |
| `affected_material_family` | ✅ multi-value | `['polyester', 'nylon', 'viscose', 'modal', 'cotton', 'FR', 'membrane', 'mixed', 'OTHER']` | `['OTHER']` |
| `commercial_exposure_type` | ✅ single | `export / raw_material / competitor / regulation / sourcing / OTHER` | `'OTHER'` |
| `entity_name` | ✅ | Free text | `'(unspecified)'` |
| `entity_role` | ✅ | matches `entity_type` enum | `'competitor'` if entity matched, else `'market'` |

---

## Migration 012 — Entity Seed (23 entities)

**File:** `migrations/012_seed_new_entities.sql`
**Estimated time:** 1 hour

### SQL skeleton

```sql
-- Migration 012: Seed 23 new entities per ChatGPT gap #8 + roadmap v1.2
-- Phase E P1 step 3/4

BEGIN;

-- Upstream / Supplier (8 entities)
INSERT INTO entities (id, name, entity_type, country, geography, website, notes) VALUES
  (gen_random_uuid(), 'SASA', 'supplier', 'TR', 'TR', 'https://www.sasa.com.tr',
   'TR PTA/PET/POY/fiber — primary cost driver for Rayon polyester inputs'),
  (gen_random_uuid(), 'Korteks', 'supplier', 'TR', 'TR', 'https://www.korteks.com.tr',
   'TR polyester filament — direct yarn input'),
  (gen_random_uuid(), 'Indorama', 'supplier', 'TH', 'GLOBAL', 'https://www.indoramaventures.com',
   'Global PET/fiber — benchmark price'),
  (gen_random_uuid(), 'Reliance Recron', 'supplier', 'IN', 'GLOBAL', 'https://www.ril.com',
   'Global polyester capacity'),
  (gen_random_uuid(), 'Hyosung', 'supplier', 'KR', 'GLOBAL', 'https://www.hyosung.com',
   'Global filament benchmark'),
  (gen_random_uuid(), 'UNIFI REPREVE', 'benchmark_brand', 'US', 'GLOBAL', 'https://unifi.com',
   'Recycled polyester signaling'),
  (gen_random_uuid(), 'Aquafil ECONYL', 'benchmark_brand', 'IT', 'EU', 'https://www.aquafil.com',
   'Recycled nylon signaling'),
  (gen_random_uuid(), 'Toray', 'supplier', 'JP', 'GLOBAL', 'https://www.toray.com',
   'Japan technical fiber');

-- TR Benchmark Competitors (7 entities)
INSERT INTO entities (id, name, entity_type, country, geography, website, notes) VALUES
  (gen_random_uuid(), 'Yeşim Tekstil', 'competitor', 'TR', 'TR', 'https://www.yesim.com',
   'TR knit leader'),
  (gen_random_uuid(), 'Bossa', 'competitor', 'TR', 'TR', 'https://www.bossa.com.tr',
   'TR denim/woven legacy'),
  (gen_random_uuid(), 'Söktaş', 'competitor', 'TR', 'TR', 'https://www.soktas.com',
   'TR shirting benchmark'),
  (gen_random_uuid(), 'Kıvanç Tekstil', 'competitor', 'TR', 'TR', NULL,
   'TR woven export'),
  (gen_random_uuid(), 'Limonteks', 'competitor', 'TR', 'TR', NULL,
   'TR technical fabric'),
  (gen_random_uuid(), 'Hassan Tekstil', 'competitor', 'TR', 'TR', NULL,
   'TR vertical integration'),
  (gen_random_uuid(), 'Polyteks', 'competitor', 'TR', 'TR', NULL,
   'TR yarn export');

-- International Technical Benchmark (4 entities)
INSERT INTO entities (id, name, entity_type, country, geography, website, notes) VALUES
  (gen_random_uuid(), 'W.L. Gore', 'benchmark_brand', 'US', 'GLOBAL', 'https://www.gore-tex.com',
   'Premium membrane peer'),
  (gen_random_uuid(), 'INVISTA Cordura', 'benchmark_brand', 'US', 'GLOBAL', 'https://www.cordura.com',
   'Technical nylon benchmark, military market'),
  (gen_random_uuid(), 'DuPont Nomex', 'benchmark_brand', 'US', 'GLOBAL', 'https://www.dupont.com/nomex.html',
   'Flame-resistant benchmark');
-- Sympatex already in 32-list, no need to re-add

-- Associations / Regulators (4 entities)
INSERT INTO entities (id, name, entity_type, country, geography, website, notes) VALUES
  (gen_random_uuid(), 'İHKİB', 'association', 'TR', 'TR', 'https://www.ihkib.org.tr',
   'TR garment export narrative'),
  (gen_random_uuid(), 'EURATEX', 'association', 'BE', 'EU', 'https://euratex.eu',
   'EU textile lobby & policy'),
  (gen_random_uuid(), 'ECHA', 'regulator', 'FI', 'EU', 'https://echa.europa.eu',
   'EU chemical restrictions - critical for technical/military line'),
  (gen_random_uuid(), 'TGSD', 'association', 'TR', 'TR', 'https://www.tgsd.org.tr',
   'TR clothing manufacturers - labor/production');

-- Verify
-- SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type ORDER BY 2 DESC;
-- Expected: competitor=39 (32 existing + 7 new), supplier=6, benchmark_brand=6,
--           association=3, regulator=1, total=55

COMMIT;
```

### Notes
- All entities created with `entity_type` set (no nulls)
- Country = ISO 2-letter code
- Geography = market grouping (TR / EU / GLOBAL / MENA / etc.)
- `notes` field gives the "why monitor" context

---

## LLM Prompt Updates

**File modified:** `scrapers/llm_analyzer.py` `build_system_prompt()`
**Estimated time:** 3 hours

### New JSON output schema fields

Add to MANDATORY JSON OUTPUT section (after `signal_priority_profile`):

```
"rayon_why_it_matters":    <ONE specific Turkish sentence explaining the
                            concrete impact on Rayon's business — never null,
                            use "Etki belirsiz, izlemeye değer." if no clear impact>,
"affected_business_line":  <array from ["woven","knit","technical","coated","OTHER"];
                            use ["OTHER"] if unclear; multi-value allowed when relevant>,
"affected_material_family": <array from ["polyester","nylon","viscose","modal","cotton",
                             "FR","membrane","mixed","OTHER"]; multi-value allowed>,
"commercial_exposure_type": <"export"|"raw_material"|"competitor"|"regulation"|
                             "sourcing"|"OTHER">,
"entity_name":             <name of the primary entity mentioned in the article
                            (company, association, regulator, or geography); use
                            "(unspecified)" if no clear entity>,
"entity_role":             <"competitor"|"supplier"|"benchmark_brand"|"association"|
                            "regulator"|"market"|"customer_segment"|"OTHER">,
```

### New REQUIRED FIELDS section addition

Update the REQUIRED FIELDS block to include:
- `rayon_why_it_matters`: never null, use Turkish placeholder if unclear
- `affected_business_line`: at least `["OTHER"]`
- `affected_material_family`: at least `["OTHER"]`
- `commercial_exposure_type`: pick closest match
- `entity_name`: use `"(unspecified)"` if no entity
- `entity_role`: pick closest match

### Entity recognition guidance

Add a new section after current TRACKED COMPETITOR COMPANIES:

```
══ ENTITY RECOGNITION ══
The article may mention any of these entity types:
  - competitor: direct Rayon peer (e.g., Yeşim, Bossa, SANKO Textile)
  - supplier: upstream raw material producer (e.g., SASA, Korteks, Indorama)
  - benchmark_brand: international peer (e.g., Gore-Tex, INVISTA, UNIFI)
  - association: trade body (e.g., İHKİB, EURATEX, TGSD)
  - regulator: gov/regulatory body (e.g., ECHA, European Commission, T.C. Tic.Bak)
  - market: geography mentioned as actor (e.g., "EU policy", "Egypt customs")
  - customer_segment: aggregate customer type (e.g., "TR garment manufacturers",
                     "EU brands", "MENA traders")

When you encounter an entity, populate entity_name with the specific name and
entity_role with its type from the list above. If multiple entities, pick the
primary one driving the signal. If none, use entity_name="(unspecified)" and
entity_role="OTHER".
```

---

## Python Code Changes

**File modified:** `scrapers/llm_analyzer.py`
**Estimated time:** 3 hours

### New VALID_* constants

```python
VALID_ENTITY_TYPES = {
    "competitor", "supplier", "benchmark_brand", "association",
    "regulator", "market", "customer_segment"
}

VALID_COMMERCIAL_EXPOSURE = {
    "export", "raw_material", "competitor", "regulation", "sourcing", "OTHER"
}

VALID_BUSINESS_LINES = {"woven", "knit", "technical", "coated", "OTHER"}

VALID_MATERIAL_FAMILIES = {
    "polyester", "nylon", "viscose", "modal", "cotton",
    "FR", "membrane", "mixed", "OTHER"
}
```

### Validation logic additions

After existing `signal_category` and `signal_priority_profile` validation:

```python
# rayon_why_it_matters (P1: never null)
rwim = analysis.get("rayon_why_it_matters")
if not rwim or not isinstance(rwim, str) or len(rwim.strip()) < 5:
    analysis["rayon_why_it_matters"] = "Etki belirsiz, izlemeye değer."

# affected_business_line (P1: multi-value array)
abl = analysis.get("affected_business_line")
if not isinstance(abl, list) or not abl:
    analysis["affected_business_line"] = ["OTHER"]
else:
    # Filter to valid values, fallback to OTHER if all invalid
    abl_clean = [v for v in abl if v in VALID_BUSINESS_LINES]
    analysis["affected_business_line"] = abl_clean if abl_clean else ["OTHER"]

# affected_material_family (P1: multi-value array)
amf = analysis.get("affected_material_family")
if not isinstance(amf, list) or not amf:
    analysis["affected_material_family"] = ["OTHER"]
else:
    amf_clean = [v for v in amf if v in VALID_MATERIAL_FAMILIES]
    analysis["affected_material_family"] = amf_clean if amf_clean else ["OTHER"]

# commercial_exposure_type (P1: single value, OTHER fallback)
ce = analysis.get("commercial_exposure_type")
analysis["commercial_exposure_type"] = ce if ce in VALID_COMMERCIAL_EXPOSURE else "OTHER"

# entity_name (P1: never null)
en = analysis.get("entity_name")
if not en or not isinstance(en, str) or not en.strip():
    analysis["entity_name"] = "(unspecified)"

# entity_role (P1: single value, OTHER -> competitor fallback)
er = analysis.get("entity_role")
analysis["entity_role"] = er if er in VALID_ENTITY_TYPES else "competitor"
```

### INSERT statement updates

`insert_market_signal()` and `insert_competitor_signal()` both need updating:

**Column list addition:**
```python
# Add to column list after rayon_relevance, signal_priority_profile:
rayon_why_it_matters, affected_business_line,
affected_material_family, commercial_exposure_type,
entity_name, entity_role
```

**VALUES placeholder count:** 21 → 27 `%s`

**VALUES tuple additions:**
```python
analysis["rayon_why_it_matters"],
psycopg2.extras.Json(analysis["affected_business_line"]),
psycopg2.extras.Json(analysis["affected_material_family"]),
analysis["commercial_exposure_type"],
analysis["entity_name"],
analysis["entity_role"],
```

### Entity matching logic enhancement

Existing `match_companies()` function needs:
1. Renamed to `match_entities()`
2. Returns full entity dict (with `entity_type`) so caller can populate `entity_role`
3. Query updated: `SELECT id, name, entity_type FROM entities WHERE ...`

---

## Backfill Strategy

**Estimated time:** 1 hour
**Approach:** Heuristic defaults + optional LLM reanalysis

### Phase 1: Heuristic defaults (no LLM cost)

Apply SQL defaults to existing 126 signals:

```sql
UPDATE market_signals SET
    rayon_why_it_matters = COALESCE(rayon_why_it_matters,
        'Etki belirsiz, izlemeye değer. (P1 backfill default)'),
    affected_business_line = COALESCE(affected_business_line, '["OTHER"]'::jsonb),
    affected_material_family = COALESCE(affected_material_family, '["OTHER"]'::jsonb),
    commercial_exposure_type = COALESCE(commercial_exposure_type,
        CASE signal_category
            WHEN 'REGULATORY' THEN 'regulation'
            WHEN 'TRADE_POLICY' THEN 'export'
            WHEN 'RAW_MATERIAL' THEN 'raw_material'
            WHEN 'COMPETITOR_MOVE' THEN 'competitor'
            WHEN 'SUPPLY_CHAIN' THEN 'sourcing'
            ELSE 'OTHER'
        END),
    entity_name = COALESCE(entity_name, '(unspecified)'),
    entity_role = COALESCE(entity_role, 'competitor');
```

This is fast, no LLM call, gets all rows into compliance. Quality is mediocre but baseline.

### Phase 2: LLM reanalysis (optional, ~$0.20)

After P1 deploys, run `scripts/migrations/reanalyze_last_30d.py` (similar to P0-D.3) to get proper LLM-driven values for the 99 OTHER signals + recent activity. ~30 minutes, ~$0.15-0.20.

---

## Rollout Sequence

### Suggested order (sequential, each fully tested before next)

1. **Step 1 (Day 1, 3h):** Migration 010 (entity rename + enum)
   - Apply migration
   - Update scrapers (companies → entities)
   - Update dashboard server.py
   - Smoke test: dashboard loads, daily cron-style trial run works
   - Commit: `Phase E P1 step 1/4: companies -> entities rename + entity_type enum`

2. **Step 2 (Day 1, 2h):** Migration 011 (exposure fields)
   - Apply migration
   - Smoke test: schema verified, no app code yet using the new columns
   - Commit: `Phase E P1 step 2/4: exposure layer fields on market_signals`

3. **Step 3 (Day 2, 1h):** Migration 012 (seed 23 entities)
   - Apply migration
   - Verify 32 + 23 = 55 entities, correct entity_type distribution
   - Commit: `Phase E P1 step 3/4: seed 23 new entities (priority list)`

4. **Step 4 (Day 2, 3h):** LLM prompt + validation
   - Update `build_system_prompt()` with 6 new fields + entity recognition section
   - Add VALID_* constants
   - Add validation logic with fallbacks
   - Update INSERT statements
   - Smoke test: `analyze(limit=1, dry_run=True)` returns all new fields populated
   - Commit: `Phase E P1 step 4/4: LLM prompt + validation for exposure layer`

5. **Step 5 (Day 2, 1h):** Backfill existing 126 signals (heuristic defaults)
   - Run UPDATE SQL
   - Verify 0% NULL on all new REQUIRED fields
   - Commit migration script: `Phase E P1: heuristic backfill for existing signals`

6. **Step 6 (Day 2-3, 1h):** Test + verify
   - Full daily-run-style test
   - Dashboard inspection (new fields don't break UI yet — Phase 3 will add display)
   - NULL coverage verification

**Total:** ~14 hours across 2-3 sessions.

---

## Testing Strategy

### Per-migration smoke tests

After each migration:

```python
# After 010:
assert db.execute("SELECT COUNT(*) FROM entities").scalar() == 32
assert db.execute("SELECT COUNT(*) FROM companies").scalar() == 32  # backwards-compat view
assert db.execute("SELECT entity_type FROM entities LIMIT 1").scalar() in VALID_ENTITY_TYPES

# After 011:
columns = db.execute("""SELECT column_name FROM information_schema.columns
                        WHERE table_name='market_signals'""").fetchall()
assert 'rayon_why_it_matters' in [c[0] for c in columns]
assert 'affected_business_line' in [c[0] for c in columns]
# ... etc for all 6 new columns

# After 012:
assert db.execute("SELECT COUNT(*) FROM entities").scalar() == 55
type_counts = dict(db.execute("SELECT entity_type, COUNT(*) FROM entities GROUP BY 1").fetchall())
assert type_counts['supplier'] >= 5
assert type_counts['association'] >= 3
assert type_counts['regulator'] >= 1
```

### LLM smoke test (after step 4)

```python
from scrapers.llm_analyzer import analyze
result = analyze(limit=1, dry_run=True)
# Verify analysis dict contains all 6 new fields, none null
```

### NULL coverage check (after step 5)

```sql
SELECT
    COUNT(*) FILTER (WHERE rayon_why_it_matters IS NULL) AS null_rwim,
    COUNT(*) FILTER (WHERE jsonb_array_length(affected_business_line) = 0) AS empty_abl,
    COUNT(*) FILTER (WHERE jsonb_array_length(affected_material_family) = 0) AS empty_amf,
    COUNT(*) FILTER (WHERE commercial_exposure_type IS NULL) AS null_cet,
    COUNT(*) FILTER (WHERE entity_name IS NULL) AS null_en,
    COUNT(*) FILTER (WHERE entity_role IS NULL) AS null_er,
    COUNT(*) AS total
FROM market_signals;
-- All counters should be 0 after Phase 1 backfill.
```

### Dashboard regression test

After Step 1:
- `https://[deployment]/api/signals` returns same payload structure (entity_id used internally, fields unchanged in API)
- Dashboard loads without 500 errors
- Existing filter chips still work

---

## Risk Analysis & Rollback

### Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Migration 010 breaks production reads | Medium | High (dashboard down) | VIEW preserves `companies` reads; smoke test before push |
| Scraper code missed in refactor | High | Medium (cron job fails next day) | Grep `\bcompanies\b` and `\bcompany_id\b` in all scrapers/dashboard files |
| LLM doesn't reliably populate new fields | Medium | Low (OTHER fallback handles it) | Validation logic has full OTHER fallback; quality issue not failure |
| JSONB constraint violation on bad LLM output | Low | Medium | Validation forces array shape; CHECK constraint at DB level |
| Migration 012 entity name collision | Low | Low (duplicate INSERTs fail) | Use ON CONFLICT DO NOTHING in seed, or check first |

### Rollback procedure

If P1 fails after deployment:

```sql
-- Rollback step (in reverse order)

-- Undo 012: delete the 23 newly seeded entities
DELETE FROM entities WHERE id IN (...);  -- preserve list during seed

-- Undo 011: drop new columns
ALTER TABLE market_signals DROP COLUMN rayon_why_it_matters;
ALTER TABLE market_signals DROP COLUMN affected_business_line;
ALTER TABLE market_signals DROP COLUMN affected_material_family;
ALTER TABLE market_signals DROP COLUMN commercial_exposure_type;
ALTER TABLE market_signals DROP COLUMN entity_name;
ALTER TABLE market_signals DROP COLUMN entity_role;

-- Undo 010: rename back
DROP VIEW IF EXISTS companies;
ALTER TABLE entities RENAME TO companies;
ALTER TABLE companies DROP COLUMN entity_type;
ALTER TABLE companies DROP COLUMN geography;
ALTER TABLE companies ADD COLUMN category VARCHAR(30) DEFAULT 'competitor';
ALTER TABLE market_signals RENAME COLUMN entity_id TO company_id;
```

Each migration script ships with a corresponding rollback SQL in the same folder: `migrations/010_rollback_*.sql` etc.

---

## Open Questions Resolved

From roadmap v1.2 Open Questions section:

| # | Question | Resolution |
|---|---|---|
| 1 | signal_priority_profile single vs multi? | **Single** — already deployed in P0-B |
| 2 | Customer entity granularity? | **Segment-level** for P1; account-level deferred to P4 |
| 3 | Clustering algorithm? | **Deferred** to P4 |
| 4 | P0-A follow-up site-specific selectors? | **Deferred** — 87.8% fill is acceptable |
| 5 | tekstil_teknik 403? | **Deferred** to maintenance |

---

## Glossary

- **Entity:** Any organization, geography, or aggregate type Rayon monitors (replaces "company")
- **Entity type:** The role an entity plays relative to Rayon (competitor, supplier, etc.)
- **Exposure layer:** The set of fields on `market_signals` that explain *why* and *how* Rayon is affected
- **Material family:** Fiber category (polyester, nylon, etc.) — vs **material form** which is specific product (FDY, PSF, etc.)
- **Business line:** Rayon's product categories (woven, knit, technical, coated)
- **Backwards-compat VIEW:** `companies` view kept after rename so external code keeps working

---

## References

- `docs/PHASE_E_MARKET_SIGNALS_ROADMAP.md` v1.2 (parent roadmap)
- ChatGPT analysis 2026-05-11 (gap #2 customer entity, gap #3 market entity, gap #4 multi-value tags, gap #8 entity additions)
- `migrations/006_add_signal_priority_profile.sql` (P0-B step 1, precedent for adding column + constraint)
- `migrations/007_relax_signal_category_constraint.sql` (P0-B hotfix, precedent for constraint mod)
- `migrations/008_remap_legacy_enum_and_tighten.sql` (P0-B follow-up, precedent for data + schema sync)

---

*End of P1 Entity Refactor Design v1.0*

*Next design doc: P2_SOURCE_EXPANSION_DESIGN.md (after P1 implementation)*
