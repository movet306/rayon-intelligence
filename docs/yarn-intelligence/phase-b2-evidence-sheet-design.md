# Yarn Intelligence Phase B2.1 — Evidence Sheet Design

**Status:** `FINAL`
**Date:** 2026-05-04
**Author:** Mert Ovet
**Module:** Yarn Intelligence (Rayon Intelligence Platform)
**Predecessor:** `docs/yarn-intelligence/phase-b-methodology.md`
**Successor:** Phase B2.2 (physical Google Sheet creation + Apps Script automation)

---

## One-line purpose

Bu doküman, Phase B research sırasında kullanılacak evidence sheet'in tam yapısal tasarımıdır: 6 tab, 45 kolon, validasyon kuralları, derived field formülleri, ve Phase B2.2 implementasyonu için spec.

---

## 1. Sheet Structure

Methodology'deki "family-by-family research order" kararı doğrultusunda evidence sheet **6 tab**'a bölünür:

```
_summary       (cross-family overview, formula-fed from family tabs)
polyester      (family-specific evidence)
polyamide      (family-specific evidence)
viscose        (family-specific evidence)
modal          (family-specific evidence)
blend          (family-specific evidence)
```

### Granularite kuralı
**1 spec = 1 row.** Spec başına bir satır, kanıtlar agrega field'larda korunur (`source_names`, `source_types`, `evidence_urls`). Bu karar methodology'de alındı; spec-level summary research/library üretmek için yeterli, evidence-per-row modeli Phase D/E'de quote validation gelirse değerlendirilir.

### Doldurma sorumluluğu
- **Claude:** research, normalize, parse, suggestion, evidence collection
- **Mert:** review, override, approval, advisory judgment (rayon_confirmed, active_tracked)
- **Sheets formula:** derived fields (denier_class, evidence_strength, meets_2_of_5_rule, repeat_count, source_count_total)
- **Apps Script (Phase B2.2):** timestamp automation (last_updated_at, created_at, last_updated_by)

---

## 2. Family Tab Schema — 45 Columns

Kolonlar 5 kategoride gruplanmıştır. Visual grouping (renk) ve frozen columns Section 3'te.

### Category 1: Identification (5 columns)

| # | Column | Type | Filled by | Validation | Example |
|---|---|---|---|---|---|
| 1 | `family` | enum | auto (tab) | one of: polyester / polyamide / viscose / modal / blend | `polyester` |
| 2 | `subfamily` | enum (family-specific) | Claude | see Subfamily enum table below | `FDY` |
| 3 | `raw_label_examples` | text (newline-separated) | Claude | min 1 example, max ~10 | `%100 POLYESTER 75D/72F SD\nPES 75/72 FDY ECRU` |
| 4 | `canonical_code` | text | Claude | regex `^[A-Z0-9_]+$`, max 60 char, family prefix required, unique per sheet | `PES_75D_72F_SD` |
| 5 | `display_name` | text | Claude | human-readable, max 40 char | `PES 75D/72F SD` |

#### Subfamily enum (family-specific)
| Family | Allowed values |
|---|---|
| polyester | `FDY`, `POY`, `DTY`, `ATY`, `staple` |
| polyamide | `FDY`, `POY`, `DTY`, `ATY`, `staple` |
| viscose | `filament`, `staple_ring`, `staple_vortex`, `staple_oe` |
| modal | `filament`, `staple_ring`, `staple_vortex`, `staple_oe` |
| blend | `filament_blend`, `staple_ring`, `staple_vortex`, `staple_oe` |

**Note:** "chip" is intentionally NOT a yarn subfamily. Chip is a driver/input concept, kept out of the yarn-spec layer.

#### Canonical code pattern
```
{FAMILY_PREFIX}_{SPEC_PARTS}[_{ATTRIBUTES}]

FAMILY_PREFIX:  PES, PA6, PA66, VIS, MOD, PV, PM, PC
SPEC_PARTS:     {DENIER}D_{FILAMENTS}F   (filament)
                NE{COUNT}_{PLY}          (spun, e.g., NE30_1, NE30_2)
ATTRIBUTES:     HT, SD, FD, BR, CD, FR, ECRU, BLACK, NAVY, RED, ANTH,
                RECYCLE, CATIONIC, CHANNEL, RING, VORTEX, OE
                Blend ratio: _{primary}_{secondary}, e.g., _65_35
```

**Code-design rule:** keep minimal but collision-free. Suffix attributes are added only when they create commercial price difference and prevent code collision with the same base spec. Avoid suffix inflation.

**Blend rule:** ratio is stored both in `canonical_code` and in `blend_ratio_json`. Intentional redundancy — the code keeps row uniqueness, the JSON enables structured logic.

Examples:
- `PES_75D_72F_SD` — polyester FDY 75D/72F semi-dull
- `VIS_NE30_1_RING` — viscose Ne 30/1 ring spun
- `PV_NE30_1_65_35` — PV blend Ne 30/1, 65/35 ratio
- `MOD_NE40_1_VORTEX` — modal Ne 40/1 vortex

---

### Category 2: Spec Attributes (13 columns)

| # | Column | Type | Filled by | Validation | Example |
|---|---|---|---|---|---|
| 6 | `form` | enum | Claude | one of: `filament`, `spun`, `blend` | `filament` |
| 7 | `count_type` | enum | Claude | one of: `denier`, `Ne` | `denier` |
| 8 | `denier` | int / NULL | Claude | range 10–4000; NOT NULL if count_type=denier | `75` |
| 9 | `filament_count` | int / NULL | Claude | range 1–500; NOT NULL if count_type=denier | `72` |
| 10 | `denier_class` | enum / NULL | **Sheets formula** | derived from denier (see formula below) | `fine` |
| 11 | `ne_count` | decimal / NULL | Claude | range 5–80; NOT NULL if count_type=Ne | `30.0` |
| 12 | `ply` | int | Claude | range 1–4; default 1 | `1` |
| 13 | `twist_direction` | enum / NULL | Claude | one of: `Z`, `S`, NULL (NULL = unspecified) | `Z` |
| 14 | `luster` | enum / NULL | Claude | one of: `SD`, `FD`, `BR`, `CD`, `HT`, `FR`, NULL | `SD` |
| 15 | `recycle_flag` | bool | Claude | default false | `false` |
| 16 | `color_state` | enum | Claude | one of: `ECRU`, `BLACK`, `NAVY`, `RED`, `ANTHRACITE`, `OTHER`, NULL | `ECRU` |
| 17 | `specialty_flags` | text (comma-sep enum) | Claude | controlled vocabulary; atomic flags only | `CHANNEL` |
| 18 | `blend_ratio_json` | json / NULL | Claude | NOT NULL if family=blend; sum=100 | `{"PES":65,"VIS":35}` |

#### `denier_class` derivation rule (Sheets formula)
```
<= 30   → micro
31–80   → fine
81–150  → medium
> 150   → heavy
NULL    → if denier is NULL (e.g., spun specs)
```

#### `specialty_flags` allowed values (atomic)
`CATIONIC, CHANNEL, HT, FR, DOPE_DYED, TWISTED, AIR_TEXTURED, MICRO, BRIGHT, FULL_DULL`

**Rule:** specialty_flags should only hold commercial differences NOT already captured cleanly by `luster`, `color_state`, or `count_type` fields. Avoid duplication.

---

### Category 3: Source Evidence (11 columns)

| # | Column | Type | Filled by | Validation | Example |
|---|---|---|---|---|---|
| 19 | `tier_0_internal` | bool | Claude/Mert | true if Rayon yarn_costs / quote / sales record exists | `false` |
| 20 | `tier_1_turkish` | int | Claude | count of distinct Turkish producer catalogs containing the spec | `2` |
| 21 | `tier_2_global` | int | Claude | count of distinct global producer/seller sources | `4` |
| 22 | `tier_3_b2b` | int | Claude | count of distinct B2B listings with this canonical spec | `7` |
| 23 | `tier_4_benchmark` | enum | Claude | one of: `direct`, `benchmark`, `proxy`, `estimate`, `none` | `estimate` |
| 24 | `source_names` | text (pipe-separated) | Claude | positionally matched with source_types | `Sanko \| Lenzing \| Indorama \| Alibaba` |
| 25 | `source_types` | text (pipe-separated) | Claude | controlled vocabulary; positionally matched with source_names | `turkish_catalog \| global_catalog \| global_catalog \| b2b_listing` |
| 26 | `evidence_urls` | text (newline-separated) | Claude | soft cap (see rule below) | `https://sanko.com/...\nhttps://lenzing.com/...` |
| 27 | `repeat_count` | int | **Sheets formula** | = tier_1 + tier_2 + tier_3 | `13` |
| 28 | `evidence_strength` | enum | **Sheets formula** | derived (see rule below) | `moderate` |
| 29 | `source_count_total` | int | **Sheets formula** | full evidence density score | `14` |

#### `source_types` controlled vocabulary (9 values)
`internal_purchase, internal_quote, internal_sales, turkish_catalog, global_catalog, industry_report, trade_article, b2b_listing, benchmark_index`

#### `source_names` / `source_types` validation rule
`count(source_names split on |) == count(source_types split on |)`. Manuel review checks alignment.

#### `evidence_urls` soft cap rule
- Tier 1 Turkish: keep all meaningful URLs
- Tier 2 Global: keep all meaningful URLs
- Tier 3 B2B: max 3 representative URLs; if more, append note in `claude_notes` like "+N additional listings reviewed"
- Tier 0 / Tier 4: 0–1 reference URL

#### `evidence_strength` derivation rule (Sheets formula)
```
strong       = tier_0_internal = true
              OR (tier_1_turkish > 0 AND tier_2_global >= 2)
moderate     = tier_1_turkish > 0
              OR tier_2_global >= 2
weak         = tier_2_global = 1
              OR tier_3_b2b >= 3
insufficient = otherwise
```

**Important:** `evidence_strength` is a **quality signal**, NOT a market_common decision. Decision logic (2-of-5 rule) is computed separately in Decision Support.

#### `source_count_total` derivation rule (Sheets formula)
```
= tier_1_turkish + tier_2_global + tier_3_b2b
  + IF(tier_0_internal, 1, 0)
  + IF(tier_4_benchmark <> 'none', 1, 0)
```

---

### Category 4: Decision Support (10 columns)

| # | Column | Type | Filled by | Validation | Example |
|---|---|---|---|---|---|
| 30 | `has_commercial_use_case` | bool | Mert | true if family has mainstream commercial OR technical mainstream use-case for this spec | `true` |
| 31 | `meets_2_of_5_rule` | bool | **Sheets formula** | derived from 5 criteria (see below) | `true` |
| 32 | `market_common_candidate` | enum | formula + Mert override | one of: `yes`, `no`, `pending` | `yes` |
| 33 | `market_common_subtype` | enum / NULL | Mert | one of: `mainstream`, `technical`, `niche-but-repeatable`, NULL | `mainstream` |
| 34 | `override_reason` | text / NULL | Mert | NOT NULL when final differs from formula suggestion | NULL |
| 35 | `pricing_basis_candidate` | enum | Claude suggest + Mert confirm | one of: `direct`, `benchmark`, `proxy`, `estimate`, `none` | `estimate` |
| 36 | `primary_driver_candidate` | text | Claude suggest + Mert confirm | dropdown of dim_material slugs + `_NEW:` prefix allowed | `polyester_fdy` |
| 37 | `secondary_driver_candidate` | text / NULL | Claude suggest + Mert confirm | same vocabulary as primary; NULL OK | `pta` |
| 38 | `rayon_confirmed_candidate` | enum | Mert (advisory only) | one of: `yes`, `no`, `unsure`, `pending` | `yes` |
| 39 | `active_tracked_candidate` | enum | Mert (advisory only) | one of: `yes`, `no`, `second-wave`, `pending` | `no` |

#### `meets_2_of_5_rule` derivation (Sheets formula)
A spec qualifies if at least 2 of these 5 criteria are true:
1. `tier_1_turkish > 0`
2. `tier_2_global >= 2`
3. `tier_3_b2b >= 3`
4. `tier_4_benchmark <> 'none'`
5. `has_commercial_use_case = true`

#### `market_common_candidate` workflow
1. Sheets formula calculates a suggested value: `yes` if `meets_2_of_5_rule`, else `no`.
2. Mert reviews. If confirming, leaves the suggested value; if overriding, manually changes the cell value.
3. Whenever the final value differs from the formula suggestion, `override_reason` becomes a required field.
4. Until reviewed, value is `pending`.

#### Driver vocabulary
Initial dropdown values (from current `dim_material` slugs):
```
polyester_fdy, polyester_dty, polyester_poy, polyester_staple,
pa6_chip, pa66_chip, polyamide_fdy,
cotton_lint, cotton_lint_futures, cotton_yarn,
rayon_yarn, pta, adipic_acid
```

For specs requiring a driver not yet in `dim_material`, use `_NEW:` prefix:
- `_NEW:viscose_staple`
- `_NEW:modal_staple`

End-of-Phase-B3 consolidation step: review all `_NEW:` entries, decide which to add to `dim_material`, update vocabulary.

#### Advisory fields rule
`rayon_confirmed_candidate` and `active_tracked_candidate` are **advisory only**. They capture Mert's research-time observations but are NOT applied during Phase B seed. They feed Phase D (rayon_confirmed enrichment) and Phase E (UI) later.

---

### Category 5: Review (6 columns)

| # | Column | Type | Filled by | Validation | Example |
|---|---|---|---|---|---|
| 40 | `status` | enum | Claude/Mert | 6 values, person-neutral (see below) | `under_review` |
| 41 | `reviewer_notes` | text | Mert | free text, max 500 char | `Bu spec'i biz kullanmıyoruz, ama markette yaygın` |
| 42 | `claude_notes` | text | Claude | free text, soft cap 500 char | `Tier 2 only — needs Turkish catalog confirmation` |
| 43 | `last_updated_by` | enum | **Apps Script (B2.2)** | one of: `claude`, `mert` (or extensible) | `claude` |
| 44 | `last_updated_at` | datetime | **Apps Script (B2.2)** | ISO 8601 timestamp | `2026-05-04T14:30:00` |
| 45 | `created_at` | datetime | **Apps Script (B2.2)** | ISO 8601 timestamp, frozen on first write | `2026-05-04T10:15:00` |

#### `status` enum (person-neutral)
```
draft           — not yet researched
research_filled — research completed, awaiting review
under_review    — actively being reviewed
approved        — final, ready for seed
rejected        — excluded from seed
on_hold         — needs more evidence; B3 follow-up queue
```

**Important:** Status values are role-neutral. `claude_filled` or `mert_review` are NOT used — schemas should not hardcode person names.

#### Timestamp automation (Phase B2.2)
- `last_updated_at`: set on every cell edit via Apps Script `onEdit` trigger. Do NOT use `=NOW()` — it recalculates on every change.
- `created_at`: set once on first row write, then frozen. Apps Script handles the freeze.
- `last_updated_by`: editor email mapped to `claude` or `mert` via lookup.
- For Phase B2.1 documentation phase: these columns exist but stay blank until B2.2 automation is added.

---

## 3. Visual Design

### Frozen columns (6)
Sheet should freeze the first **6 columns** to keep core identity + decision anchor visible during scroll:
```
family | subfamily | canonical_code | display_name | market_common_candidate | status
```

Fallback if performance/screen constraints force 5: drop `subfamily`, NOT `market_common_candidate`.

### Color grouping by category
| Category | Header color (suggested) |
|---|---|
| Identification | light blue |
| Spec Attributes | light green |
| Source Evidence | light yellow |
| Decision Support | light orange |
| Review | light gray |

### Derived field visual treatment
Sheets formula columns (`denier_class`, `repeat_count`, `evidence_strength`, `source_count_total`, `meets_2_of_5_rule`) should use a slightly muted/lighter cell background within their category color, to signal "this is computed, do not manually edit."

---

## 4. `_summary` Tab Design

Cross-family overview tab. **10 columns**, fed via `QUERY` or `IMPORTRANGE` formulas from the 5 family tabs.

| # | Column | Source column letter (in family tab) | Source |
|---|---|---|---|
| 1 | `family` | A | from family tab |
| 2 | `canonical_code` | D | from family tab |
| 3 | `display_name` | E | from family tab |
| 4 | `evidence_strength` | AB | from family tab |
| 5 | `meets_2_of_5_rule` | AE | from family tab |
| 6 | `market_common_candidate` | AF | from family tab |
| 7 | `pricing_basis_candidate` | AI | from family tab |
| 8 | `rayon_confirmed_candidate` | AL | from family tab |
| 9 | `active_tracked_candidate` | AM | from family tab |
| 10 | `status` | AN | from family tab |

**Implementation note:** the source column letters above were verified against the live deployed sheet. The `QUERY` formula in `apps-script/setup-evidence-sheet.gs` uses these letters. If the family-tab schema is reordered, this table and the script must be updated together.

### Purpose
- Cross-family review of decisions
- Quick scan of progress (`status` distribution per family)
- Forward-looking view: which specs are flagged for Phase D/E
- Override audit: spot specs where `market_common_candidate` differs from `meets_2_of_5_rule`

The summary tab is read-only by convention; edits should be made on the family tab and propagate via formula.

---

## 5. Phase B2.2 Implementation Notes

This section is a forward reference for the next session.

### Tasks for Phase B2.2
1. Create the actual Google Sheet with all 6 tabs
2. Add 45 columns to each family tab with header formatting
3. Apply data validation rules per the column tables above
4. Add Sheets formulas for derived fields:
   - `denier_class`
   - `repeat_count`
   - `evidence_strength`
   - `source_count_total`
   - `meets_2_of_5_rule`
   - `market_common_candidate` (suggested value before override)
5. Set up `_summary` tab with `QUERY` or `IMPORTRANGE` formulas
6. Apps Script for timestamp automation (`last_updated_at`, `created_at`, `last_updated_by`)
7. Frozen columns (6)
8. Color grouping per category
9. Test with 2–3 sample rows per family to verify formulas
10. Decide on access permissions and shared link

### Snapshot workflow
- Active research happens in Google Sheets
- Periodic exports to CSV in `docs/yarn-intelligence/evidence/{family}-{YYYY-MM-DD}.csv`
- Snapshots are committed to repo at family completion milestones and final review

---

## 6. Cross-references

- **Phase A migration:** `migrations/009_yarn_universe_tier.sql` (commit `3559211`)
- **Methodology:** `docs/yarn-intelligence/phase-b-methodology.md` (commit `7b7fa3f`)
- **Initial active set:** `docs/yarn-intelligence/active-tracked/2026-05-03-initial-active-set.md` (commit `b51057d`)
- **Schema CSV:** `docs/yarn-intelligence/phase-b2-evidence-sheet-schema.csv` (machine-readable companion to this document)
- **Deployment scripts:** `apps-script/setup-evidence-sheet.gs` and `apps-script/triggers.gs` (commit `f66ed14`)

---

## 7. Revision History

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-05-04 | Initial FINAL — 5 categories, 45 columns, 6 tabs designed and locked |
| 1.1 | 2026-05-04 | Section 4: added source column letters to `_summary` mapping table (A, D, E, AB, AE, AF, AI, AL, AM, AN) — verified against live deployed sheet. Section 6: added deployment-scripts cross-reference. |

---

*Bu doküman Phase B2.2'nin ana spec'idir. B2.2 implementation bu doc'a referansla yapılmalıdır. Yapısal değişiklikler ayrı revizyon notu ile.*
