-- ============================================================================
-- Migration 029 — Phase C: Fix dim_material Slug Typos
-- ============================================================================
-- Purpose:
--   Align dim_material.slug values with price_metrics_daily.material naming
--   convention. Three legacy typos prevent direct join in pricing engine.
--
--   Discovered during Phase C driver mapping work (May 2026):
--
--   dim_material.slug          | price_metrics_daily.material  | Issue
--   ---------------------------|-------------------------------|---------
--   apidic_acid                | adipic_acid                   | typo: "apidic" -> "adipic"
--   _cotton_lint_features      | cotton_lint_futures           | typo: prefix + "features" -> "futures"
--   _polyester_staple_fiber    | polyester_staple_fiber        | spurious underscore prefix
--
--   After this migration, all 11 dim_material upstream commodity drivers
--   match price_metrics_daily.material 1:1, enabling clean JOIN in pricing
--   engine without a mapping layer.
--
-- Scope:
--   Three UPDATEs on dim_material.slug. No DROP, no ALTER.
--   Idempotent: WHERE clause guards. Safe to re-run.
--
-- Pre-flight verification (run before migration):
--   - Confirm no foreign references to typo slugs in dim_material.upstream_benchmark_slug:
--     SELECT COUNT(*) FROM dim_material WHERE upstream_benchmark_slug IN
--       ('apidic_acid','_cotton_lint_features','_polyester_staple_fiber');
--     Expected: 0 (Migration 028 used correct names already).
-- ============================================================================

UPDATE dim_material SET slug = 'adipic_acid'
WHERE slug = 'apidic_acid';

UPDATE dim_material SET slug = 'cotton_lint_futures'
WHERE slug = '_cotton_lint_features';

UPDATE dim_material SET slug = 'polyester_staple_fiber'
WHERE slug = '_polyester_staple_fiber';

-- Combined verification:
SELECT slug, family, commodity_name
FROM dim_material
WHERE slug IN ('adipic_acid','cotton_lint_futures','polyester_staple_fiber')
ORDER BY slug;
-- Expected: 3 rows.
