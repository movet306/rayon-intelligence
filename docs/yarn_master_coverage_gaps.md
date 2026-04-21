# Yarn Master Coverage Gaps — Phase 1

## Current Coverage (21 canonical specs, 31 label aliases)

| Family    | Process | Specs | Notes |
|-----------|---------|-------|-------|
| Polyester | FDY     | 15    | 50D–150D, includes SD/BR/CD/Kanalı/GRS |
| Polyester | DTY     | 1     | 75D/72F GRS; driver = polyester_dty/polyester_poy |
| PA6       | DTY     | 1     | 70D/68F; S/Z twist and doubled (x2) are aliases |
| PA6.6     | FDY     | 1     | 78D/68F standard |
| PA6.6     | FDY     | 1     | `PA66` — placeholder, no spec data (NYL66 IPLIK raw label) |
| PA6.6     | HT      | 2     | 470D/136F and 470D/140F industrial; grade A/B/SUPER_B are aliases |

### Consolidation notes
- Kanalı (channel-section) yarns are grouped with plain same-denier yarns under the current
  group key `(fiber_family, filament_process, denier, filament_count, luster, recycle_flag)`.
  If Kanalı commands a distinct price, add `is_kanalli BOOLEAN` to the group key in Phase 2.
- PA6 S/Z/X2-twist variants are currently aliases of the S-twist canonical.
  Twist direction affects DTY performance; add `twist_direction` to the group key if
  separate pricing is required.
- PA6.6 HT quality grades (A / B / SUPER_B) are currently aliases.
  Add `quality_grade` to the group key if grade-specific pricing is needed.

## Known Gaps (not in lkp_yarn_taxonomy — future phases)

- **Cotton spun** (OE / ring / compact / combed / vortex): NOT IN SOURCE
- **Viscose / Modal / Lyocell**: NOT IN SOURCE
- **Blend yarns** (PES/COT, PES/VIS): NOT IN SOURCE
- **Elastane / core-spun**: NOT IN SOURCE
- **Polypropylene**: NOT IN SOURCE
- **Acrylic**: NOT IN SOURCE

All six absent families were confirmed absent from `lkp_yarn_taxonomy` (not a parsing gap).

## Schema Readiness

All absent families can be added to the existing `dim_yarn_master` schema without DDL changes:

| Family       | Additional fields needed           |
|--------------|------------------------------------|
| Cotton spun  | `spinning_method`, `count_ne`      |
| Blend        | `blend_a_fiber`, `blend_a_ratio`, `blend_b_fiber`, `blend_b_ratio` |
| Viscose/Modal| `fiber_family = 'cellulosic'`      |
| Elastane     | `fiber_family = 'elastane'`, `blend_*` for core-spun |

## Next Steps

- **Phase 2**: Add cotton / blend families from internal sourcing data
- **Phase 2**: Resolve PA66 placeholder (enrich or remove `yarn_code = 'PA66'`)
- **Phase 3**: Add viscose / modal / lyocell when relevant to Rayon's product mix
- **Future**: Extend group key with `is_kanalli`, `twist_direction`, `quality_grade`
  if sub-spec pricing differentiation is required
