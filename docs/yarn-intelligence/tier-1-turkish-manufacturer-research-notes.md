# Tier 1 Turkish Manufacturer Research Notes — Polyester FDY

**Status:** `LIVING NOTE`
**Created:** 2026-05-04
**Scope:** This note applies to **polyester FDY Tier 1 research only**. Other yarn families (polyamide, viscose, modal, blend) require their own research-derived market maps.

---

## 1. Purpose

During PES_75D_72F Phase B3 evidence research, the initial Turkish-manufacturer hypothesis (Sanko, İskur, Korteks, Kıvanç, Kordsa) was falsified for polyester FDY. Web research revealed that only Korteks operates in the polyester FDY apparel space; the others belong to different yarn universes.

This note records the corrected Tier 1 producer set for polyester FDY so the same market-map error is not repeated for the remaining four pilot specs (PES_100D_144F, PES_75D_72F_CHANNEL, PES_75D_72F_RECYCLED, PES_50D_72F) or for any future polyester research.

The four scoped-out players are documented here (not in `claude_notes`) so the family tab cell stays clean while the research trail remains visible at the repo level.

---

## 2. Included players (polyester FDY Tier 1 candidates)

| Manufacturer | Location | Scope match | Notes |
|---|---|---|---|
| **Korteks** | Bursa, Zorlu Group | ✅ apparel polyester FDY | Europe & Middle East largest integrated polyester yarn producer. Catalog filter grid lists explicit denier/filament/brightness/colour selectable values. Strongest single Tier 1 source. URL: https://www.korteks.com.tr/en/products/standard-yarns/tac-polyester-fdy |
| **Kocer Tekstil** | Bursa | ✅ apparel polyester FDY | Polyester DTY/FDY/POY/ATY/SDY exporter since 1976. Catalog publishes explicit denier/filament configurations (e.g. `FDY 75/72 SD RW`). URL: https://kocertekstil.com/polyester-fdy-iplik/ |
| **SASA** | Adana | ⚠️ family-support only | Major polyester polymer + filament producer (Erdemoğlu Holding subsidiary). Public catalog mentions FDY production in generic terms ("with different filament numbers, deniers, brightness and colors") but does not publish a spec list. Family-support evidence only; cannot be counted as spec-direct without supplier engagement. URL: https://www.sasa.com.tr/en/products/filament-yarn-and-poy |

**Kept-as-candidate but verified scoped-out:** Erdem Soft Tekstil — see section 3.

---

## 3. Scoped-out players

These players were either in the original hypothesis or surfaced during research. After verification, none belong to the polyester FDY apparel Tier 1 universe.

| Manufacturer | Reason scoped out | Source |
|---|---|---|
| **Sanko** | Cotton/blend yarn universe (denim, mainstream apparel cotton); not a polyester FDY producer for apparel filament. | Industry knowledge; absence from polyester FDY producer search results |
| **İskur** | Spun/cotton-oriented yarn universe; not a polyester FDY filament producer. | Industry knowledge; absence from polyester FDY producer lists |
| **Kıvanç** | Integrated **woven fabric** producer (Adana, since 1950); uses polyester/cotton/viscose as input but does not sell yarn — they are a downstream consumer, not a Tier 1 yarn supplier. | https://www.kivanctekstil.com.tr/corporate |
| **Kordsa** | Industrial/technical yarn focus (tire cord, composites, reinforcement); not relevant for apparel polyester FDY. | Industry knowledge |
| **Erdem Soft Tekstil** | Polyester yarn producer but **carpet/upholstery scope** — POY range 150–1000D, DTY range 600–1800D, ATY range 900–4500D. No 75D apparel filament line. Segment mismatch (carpet vs apparel filament). | https://www.erdemsofttextile.com/en/teksturize-iplik and https://www.erdemsofttextile.com/en/pet-poy |

**Operational rule:** scoped-out players do NOT count toward `tier_1_turkish` in the evidence sheet. They are recorded here for research-trail transparency.

---

## 4. Lessons learned

1. **Yarn-family-specific market maps required.** A single "Turkish yarn manufacturer" list does not exist; the population differs by fiber family (polyester FDY vs cotton spun vs polyamide HT industrial vs viscose) and by application segment (apparel vs carpet/upholstery vs technical/industrial).

2. **Apparel-grade vs carpet/upholstery-grade is a critical sub-distinction.** Erdem Soft is a legitimate polyester yarn producer but only at heavy denier (≥150D POY, ≥600D DTY) for carpet/upholstery. Lightweight apparel filament (75D class) is outside their range.

3. **Catalog form factor matters.** Korteks publishes a filter-grid catalog (denier × filament × luster × colour as selectable axes) — strong spec-direct evidence when the queried combination appears as available values. Kocer Tekstil publishes a flat list of named SKUs (e.g. `FDY 75/72 SD RW`) — strongest possible spec-direct evidence (named in catalog). SASA publishes only generic capability statements — family-support only.

---

## 5. Pending future expansion

When Phase B3 reaches polyamide or viscose families, this file pattern should be cloned:

- `docs/yarn-intelligence/tier-1-turkish-manufacturer-research-notes-polyamide.md`
- `docs/yarn-intelligence/tier-1-turkish-manufacturer-research-notes-viscose.md`
- etc.

Each family will have its own Tier 1 producer map. Cotton spun (Sanko, İskur) and industrial polyamide (Kordsa) will likely re-enter scope in their respective family files.

---

## 6. Revision history

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-05-04 | Initial — polyester FDY scope, derived from PES_75D_72F Phase B3 Tier 1 research. Korteks + Kocer Tekstil confirmed spec-direct; SASA family-support; Erdem Soft + Sanko + İskur + Kıvanç + Kordsa scoped out. |
