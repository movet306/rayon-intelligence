# Phase B3 — Lessons Learned

Reference document for future yarn intelligence pilots (viscose, modal, blend, polyamide apparel, polyester staple, etc.). Captures methodology decisions, tooling patterns, and schema clarifications established during the polyester filament + polyamide HT pilots (May 2026).

---

## 1. Strict spec-direct discipline (Senaryo A)

**Rule:** Spec-direct evidence requires **exact** denier + filament count match. "Very close" does not count.

| Comparison | Verdict |
|---|---|
| 470D/144F vs 470D/136F | family-support (NOT spec-direct) |
| 470D/144F vs 470D/140F | family-support (NOT spec-direct) |
| 100D/96F vs 100D/144F | family-support |

Same denier class without filament grid published = family-support. Loosening this destroys the credibility of the polyester tier counters where the discipline is enforced strictly.

**Implication for tier counters:** Family-support evidence does NOT increment `tier_1_turkish` or `tier_2_global`. It goes in claude_notes only, prefixed `[family-support]`.

---

## 2. Form-level and market-level family separation

A "family" is not just the polymer. Separate pilots are required per:

- **Form:** filament ≠ staple ≠ tow
- **Market segment:** HT industrial ≠ apparel ≠ technical
- **Subfamily:** FDY ≠ DTY ≠ POY (when verifiable)

Polyamide example: PA6.6 470D HT industrial (tire reinforcement, CORDURA) and PA6.6 78D apparel are different markets with different supplier sets, different price drivers (chip cost vs fashion cycle), and different Tier 4 benchmark availability. They get separate pilot tracks.

---

## 3. Tier 0 + Tier 2 double-counting prevention

When the internal supplier of record (Tier 0) is also a public catalog source (Tier 2), do NOT count it twice.

**Pattern:** Use `[context]` flag in claude_notes, keep Tier 2 counter at 0.

Example — Row 5 (PA66_470D_140F_HT):
- Tier 0: Invista (4 records, 2025-01)
- Invista CORDURA Lite catalog Product ID 749 explicitly lists 470/140 PA6.6 FDY
- Counter: `tier_2_global = 0` (not 1)
- Note: `[context] exact public spec confirmed, but not counted in Tier 2 to avoid double-counting against Tier 0 supplier-of-record`
- Manual decision: `market_common_candidate = yes` (public evidence exists, just excluded from formula counter)

This is different from RECYCLED specs where public exact spec evidence was genuinely thin. The distinction matters for `market_common_candidate`.

---

## 4. Multi-supplier sourcing as a niche-but-repeatable signal

If a spec is sourced across multiple suppliers in `yarn_costs` despite **no public catalog visibility**, that is a strong signal for `niche-but-repeatable` subtype.

Example — PES_75D_72F_CHANNEL:
- 14 records / 362K kg / 3 suppliers (Fujian Billion 11 + PT. Indorama 2 + Jiangsu Guowang 1)
- Zero public catalog hits across Korteks, Kocer, TPC, SASA, Indorama, Reliance, Toray, Hyosung
- Conclusion: widely producible across Asia, sales-driven, not publicly catalogued

This pattern justifies `niche-but-repeatable` over `niche-specialty` (which is not a valid enum value, see §7).

---

## 5. Producer-pass workflow

When researching tier evidence, **open each producer once and check all pilot specs against their grid** rather than going spec-by-spec.

Bad workflow (spec-pass): for each spec, search "Korteks 75D/72F", "Korteks 100D/144F", etc. — wastes searches, no holistic view.

Good workflow (producer-pass): open Korteks TAÇ Polyester FDY filter grid once, note all (denier, filament) combinations available, mark each pilot spec accordingly.

Same for Kocer, TPC, etc. Faster, fewer redundant searches, consistent evidence.

---

## 6. ChatGPT filter — every meta task

Apply this filter before any non-pilot work:

> **"Does this change the decision for any of the 5 (or N) specs we are currently working on?"**

- Yes → do it now
- No → backlog, do not interrupt the pilot

Examples that passed: Senaryo A vs B decision (changes 5 polyamide specs), claude_notes completeness fix (changes interpretation of 4 specs).

Examples that failed: schema column proposal (`tier_0_supplier_names`), formula audit (`meets_2_of_5_rule` inconsistency), grade naming verification (Toray A < B < SUPER_B). All went to backlog.

---

## 7. Schema enums — reference

| Field | Valid values |
|---|---|
| `market_common_subtype` | `mainstream`, `technical`, `niche-but-repeatable` |
| `pricing_basis_candidate` | `direct`, `proxy`, `estimate` |
| `tier_4_benchmark` | `direct`, `estimate`, `none` |

**Trap encountered:** Wrote `niche-specialty` initially. CHECK constraint rejected it. The valid value is `niche-but-repeatable`.

---

## 8. Subfamily=FDY assumption flag

The workbook (`yarn_costs`) does not consistently tag FDY/DTY/POY. For pilot purposes, FDY is assumed. This is documented in every claude_notes entry as:

```
[assumption] Subfamily=FDY assumed for pilot purposes; workbook raw labels do not consistently tag FDY/DTY/POY. To be confirmed later against supplier/product context.
```

**Carry-forward:** Phase 2 should verify this assumption against supplier-side product data before any pricing decision uses subfamily as a driver.

---

## 9. Apps Script discipline — defensive write pattern

**The bug:** A script that writes to hardcoded row numbers (e.g., `getRange(4, ...).setValue(...)`) silently corrupts data when the sheet's row layout has shifted from prior manual edits. The script reports success even though it wrote to wrong rows. We hit this 3+ times in one session.

**The fix:** Always pre-check `canonical_code` BEFORE writing, verify signatures AFTER writing.

### Template

```javascript
function safeWrite() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName('polyester');
  const CANONICAL_COL = 4;
  const NOTES_COL = 42;

  // 1. Pre-check: each target row must match expected canonical_code
  const expectedAtRow = {
    3: 'PES_100D_144F',
    4: 'PES_75D_72F_CHANNEL',
    // ...
  };

  Object.keys(expectedAtRow).forEach(r => {
    const actual = sheet.getRange(parseInt(r, 10), CANONICAL_COL).getValue();
    if (actual !== expectedAtRow[r]) {
      throw new Error('Row ' + r + ' has "' + actual +
        '" but expected "' + expectedAtRow[r] + '". ABORTING.');
    }
  });

  // 2. Write only after pre-check passes
  // ...

  // 3. Verify: read back and check signature presence
  const expectedSig = {
    3: '24 records 2015 to 2025',
    // ...
  };
  // log OK / FAIL per row
}
```

This pattern prevented further corruption once adopted (see `master-polyester-fix.gs`).

---

## 10. Sheet row layout — current state (May 2026)

For reference; this WILL drift over time. Always verify before writing.

### Polyester tab
| Row | canonical_code |
|---|---|
| 2 | PES_75D_72F (anchor) |
| 3 | PES_100D_144F |
| 4 | PES_75D_72F_CHANNEL |
| 5 | PES_75D_72F_RECYCLED |
| 6 | PES_50D_72F |
| 7 | PES_150D_48F |
| 8 | PES_150D_96F |
| 9 | PES_100D_96F |
| 10 | PES_75D_48F_CHANNEL |
| 11 | PES_75D_72F_CATIONIC |
| 12 | PES_100D_96F_RECYCLED |

### Polyamide tab
| Row | canonical_code |
|---|---|
| 2 | PA66_470D_136F_HT_SUPER_B |
| 3 | PA66_470D_136F_HT_B |
| 4 | PA66_470D_136F_HT_A |
| 5 | PA66_470D_140F_HT |

---

## 11. Tier 4 benchmark availability differs by segment

Not all yarn families have public price benchmarks. Pricing_basis must reflect this:

| Segment | Benchmark | pricing_basis default |
|---|---|---|
| Polyester FDY mainstream | SunSirs Polyester FDY weekly | direct |
| Polyester FDY recycled | none (RPET indices exist but spotty) | proxy / estimate |
| Polyester FDY specialty (CHANNEL, CATIONIC) | none | estimate |
| Polyamide HT industrial | none (Indorama Mobility datasheets are reference, not index) | estimate |
| Polyamide apparel | SunSirs Polyamide FDY (apparel-side) | direct (when verified) |

Do not default `tier_4_benchmark = direct` without verifying a real index exists.

---

## 12. Open questions carried forward

1. Toray grade naming verification — A < B < SUPER_B counter-intuitive ordering needs supplier engagement
2. Polyester subfamily=FDY assumption — verify against supplier product context before pricing model
3. Color variant schema decision — separate canonical rows vs `color_state` column (currently storing all as ECRU)
4. Recycled `market_common = pending` — upgrade to yes/no after Tier 3/4 deeper evidence
5. Structural column `tier_0_supplier_names` — Phase B6 candidate, not now
6. Formula audit — `meets_2_of_5_rule` inconsistency (Row 5 polyester TRUE vs Row 11/12 FALSE for same pattern); `evidence_strength` returns moderate where strong expected. Advisory only, decisions are manual.
---

## 13. Market-Only Seed Pilot Lessons (Faz 1 Viscose, May 2026)

The viscose pilot was the first **market-only seed pilot** on the platform — no workbook-side Tier 0 evidence, all rows seeded from market research. This forced a new methodology branch parallel to the polyester/polyamide workbook-first approach. Seven patterns were locked during this pilot.

### 13.1 Market-First vs Workbook-First Methodology

When the workbook contains zero records for a yarn family (verified, not assumed), the polyester/polyamide methodology of "start from yarn_costs Tier 0, expand to market evidence" cannot apply. Instead, open the pilot **market-first**: build the market map (fiber anchors, yarn-level spinners, traders, benchmarks) and seed canonical_codes from there.

Critical pre-check before opening any market-first pilot: **verify the workbook gap is real**, not a naming convention difference. For viscose this was confirmed via Python pandas inspection of `material_key` / `polymer` / `yarn_raw` columns — 245 records all PES/PA6.6/PA6, zero VIS/MOD/RAYON/LYO matches.

**Operational rule (one-line):** "market-seed pilot opens with all rows pending + proxy + rayon_confirmed=unsure; producer-pass research hardens decisions over time."

### 13.2 [market-only] Prefix Flag Standard

All claude_notes for market-seed rows must begin with the standardized prefix:

```
[market-only] No Tier 0 internal workbook evidence. Seeded from market-first viscose research.
```

This prefix replaces the need for a new schema enum (`status = market_seed` was rejected to keep schema clean). The flag plus `rayon_confirmed_candidate = unsure` is sufficient to identify and filter these rows downstream. Future families opening as market-seed should use the same prefix structure with the family name swapped.

### 13.3 Three-Field Default State for Market-Seed Rows

Market-seed rows differ from workbook-anchored rows in three boolean/enum fields. Lock these as the **default initial state** before any decision sharpening:

| Field | Workbook-anchored | Market-seed |
|---|---|---|
| `tier_0_internal` | TRUE | **FALSE** |
| `rayon_confirmed_candidate` | (typically blank or specific) | **unsure** |
| `active_tracked_candidate` | TRUE/yes | **pending** |
| `has_commercial_use_case` | TRUE | **FALSE** |
| `market_common_candidate` | yes/no/pending (research-decided) | **pending** (locked initial) |

Critical rule from Mert: even if evidence supports `yes` (e.g. Ne 30/1 viscose ring is obviously commodity-mainstream globally), market_common_candidate must start as `pending`. Sharpening to `yes/mainstream` happens only after producer-pass research is fully done. "Looks like commodity" is not the same as "market_common confirmed."

### 13.4 Fiber Anchor vs Yarn Anchor Distinction

Critical distinction not relevant for synthetic filament (where the same producer makes the chip → fiber → yarn, e.g. Toray, Indorama). For staple-fiber natural/regenerated families:

- **Fiber anchor** = raw fiber producer (e.g. Birla Cellulose 824 KTPA VSF, Sateri 1.9M tonnes/yr, Lenzing premium MMCF). Family-support level evidence only.
- **Yarn anchor** = independent spinner/converter who buys raw fiber and produces the actual yarn-level product (e.g. Aditya Birla Yarn 150K MT, Rajaguru Spinning Mills, Shijiazhuang Fibersyarn). Spec-direct evidence comes from this layer.

For market-first pilots, **producer-pass research must explicitly cover both layers**. A pilot that only documents fiber anchors will have zero spec-direct Tier 2 evidence and the rows will incorrectly stay weak. Yarn-level traders (e.g. Texvin International) are also valid spec-direct evidence when they publish concrete price quotes for specific Ne counts and spinning technologies.

### 13.5 Tier 4 Proxy Logic at Different Resolution Levels

`tier_4_benchmark` enum has three tiers: `direct`, `proxy`, `estimate`. The choice depends on the **resolution match between the benchmark and the spec**:

- **direct** — benchmark covers the exact spec at exact resolution (e.g. ICE Cotton No.2 for cotton lint price, SunSirs Polyester FDY 75D for PES_75D yarn at chip-fiber level).
- **proxy** — benchmark covers a related quantity at a different resolution; conversion model needed (e.g. SunSirs VSF fiber index → yarn cost via spinning markup ~$0.80-1.45/kg).
- **estimate** — no usable benchmark, qualitative only.

Important: when the benchmark exists but at a different price-level (e.g. SunSirs Polyamide FDY ~$2.07/kg SE Asia commodity vs our Italian premium PA6.6 78/68 at $8.37/kg), `tier_4_benchmark = estimate` is correct, not `proxy`. Proxy means "use it via a conversion model"; if the conversion model itself fails (price-level mismatch too large), fall back to estimate. Document the reason in claude_notes.

### 13.6 _NEW: Driver Slug Prefix Convention

When `primary_driver_candidate` references a slug that does not yet exist in `dim_material`, prefix it with `_NEW:` (e.g. `_NEW:viscose_staple`). The prefix:

1. Flags to Phase B5 migration script that this slug must be registered before the row can be activated.
2. Prevents accidental joins in dashboard queries (a `_NEW:` slug will not match any real `dim_material.slug`).
3. Carries semantic intent forward — the slug name (`viscose_staple`) is the proposed final name, not a placeholder.

Existing scaffold rows from Migration 009 already used this convention (`_NEW:viscose_staple` was pre-flagged). Any new family pilot should follow the same pattern when the driver slug isn't yet in `dim_material`.

### 13.7 Schema Enum Runtime Discovery (Defensive Script Pattern)

Schema enum constraints in the evidence sheet are not visible from code without inspection. Subfamily enum was discovered at runtime when v2 script wrote `subfamily = "spun"` and Apps Script returned:

```
Exception: Allowed: filament, staple_ring, staple_vortex, staple_oe
```

Pre-check passed (canonical_code matched), but enum write failed mid-execution. Row 2 was left in an inconsistent partial-write state.

**Defensive pattern locked:** the existing pre-check verifies row identity; add a **post-write verification phase** that checks every enum-bound field, not just signatures. The viscose v3 verification expanded from 7 checks to 13 checks per row including `subfamily`, `count_type`, `tier_4_benchmark`, `has_commercial_use_case`, `market_common_candidate`, `pricing_basis_candidate`, `rayon_confirmed_candidate`, `primary_driver_candidate`, `status`. When any check fails, the script logs the actual vs expected value, making the enum mismatch visible immediately.

**Code template:**

```javascript
// Per-row verify with full enum coverage
const checks = [
  { name: 'subfamily',     actual: actualSf,   expected: expected.sf },
  { name: 'count_type',    actual: actualCt,   expected: 'Ne' },
  { name: 'tier_4',        actual: actualT4,   expected: 'proxy' },
  { name: 'market_common', actual: actualMc,   expected: 'pending' },
  { name: 'pricing_basis', actual: actualPb,   expected: 'proxy' },
  // ... etc
];
checks.forEach(c => {
  if (c.actual !== c.expected) {
    Logger.log('  ' + c.name + ' FAIL: got "' + c.actual + '" expected "' + c.expected + '"');
    rowOk = false;
  }
});
```

Known schema enums discovered as of Faz 1 viscose:
- `subfamily`: filament | staple_ring | staple_vortex | staple_oe
- `count_type`: Ne (capital N), denier (others not yet probed)
- `tier_4_benchmark`: direct | proxy | estimate
- `market_common_candidate`: yes | no | pending
- `pricing_basis_candidate`: direct | proxy | estimate
- `rayon_confirmed_candidate`: unsure | yes | no (string enum, not boolean)
- `active_tracked_candidate`: pending | yes | no (string enum, not boolean)
- `status`: research_filled | (others not yet probed)
- `evidence_strength`: weak | moderate | strong | insufficient (computed by sheet formula)

Add to this list as future pilots discover new enum values.

---

## 14. Methodology Branches Summary

After Phase B3 + Faz 1 viscose, the platform has two parallel pilot methodologies:

| Aspect | Workbook-anchored | Market-only seed |
|---|---|---|
| Starting point | yarn_costs Tier 0 records | Producer-pass market research |
| Tier 0 | TRUE | FALSE |
| Initial market_common state | research-decided (yes/no/pending) | pending (locked) |
| Default rayon_confirmed | (not set) | unsure |
| claude_notes prefix | none | [market-only] |
| Use case | Active procurement family with workbook records | Family with structural workbook gap (procurement may exist but not digitized) |
| Examples | Polyester filament FDY (11), Polyamide HT (4), Polyamide apparel (3) | Viscose staple/spun (5) |

Future families to be opened: Modal staple/spun (market-only seed, similar to viscose), Lyocell (market-only seed, deferred), Viscose filament (waiting on Mert's spec list, methodology TBD), PV/PM blends (workbook-anchored if blend records exist, otherwise market-only seed).

---
