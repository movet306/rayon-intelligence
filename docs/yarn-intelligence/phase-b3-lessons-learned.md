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
