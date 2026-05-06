-- ============================================================================
-- Migration 028 — Phase C: Driver Mapping (upstream_benchmark_slug)
-- ============================================================================
-- Purpose:
--   Add upstream_benchmark_slug column to dim_material so the pricing engine
--   (build_yarn_pricing.py) can map granular yarn drivers (polyester_staple)
--   to upstream commodity benchmarks (polyester_yarn from SunSirs).
--
--   Final yarn pricing falls back to:
--     yarn_price = upstream_benchmark_price + spinning_markup_for_spec
--   when no Tier 0/1 (direct quote) evidence is available.
--
-- Design philosophy (per architectural review):
--   * upstream_benchmark_slug is a PRIMARY ANCHOR only.
--   * Multi-component blend/recycled pricing is computed in CODE, not DB.
--     This column does NOT capture secondary benchmarks. Premature
--     abstraction (secondary_benchmark_slug, blend_weights_json, etc.)
--     was deliberately avoided. Refactor candidate for Phase C+1 if needed.
--   * Mevcut 14 upstream commodity drivers (cotton_yarn, polyester_yarn,
--     pa66_chip, etc.) keep upstream_benchmark_slug = NULL — they ARE
--     upstream benchmarks themselves.
--
-- KNOWN PROXY FALLBACKS (intentional, not bugs):
--
--   modal_staple -> rayon_yarn:
--     Modal is technically distinct from viscose (different production process,
--     better wet strength, longer fiber). NO dedicated modal benchmark exists
--     in our scraper coverage. Rayon (= viscose) is the closest proxy.
--     Pricing engine implications:
--       - Set confidence to 'medium' (not 'high') for modal_staple specs.
--       - Apply +15-25% premium to viscose price via spinning_markups.json
--         (modal_staple-specific markup bucket).
--       - Document this in dashboard tooltips so end users understand the
--         pricing source.
--
--   pa6.6 staple -> polyamide_fdy:
--     Filament-based benchmark used as proxy for staple. PA6.6 staple market
--     is small in our scope; no dedicated benchmark. Confidence 'low'.
--
-- BLEND / RECYCLED ROW SEMANTICS:
--
--   upstream_benchmark_slug stores ONLY the primary anchor fiber's benchmark.
--   It does NOT mean "this driver's price = upstream price". The actual
--   pricing computation in build_yarn_pricing.py:
--
--     pv_blend_staple_price =
--       (blend_ratio_PES * polyester_yarn_price +
--        blend_ratio_VIS * rayon_yarn_price) +
--       spinning_markup_pv_blend
--
--   The blend_ratio_json comes from dim_yarn_master (per-yarn).
--   The pricing engine looks up secondary fibers from blend_ratio_json,
--   maps each fiber to its commodity benchmark via a hard-coded fiber map
--   in code (fiber_to_benchmark_slug), and computes weighted average.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS + UPDATE WHERE IS NULL.
-- ============================================================================

ALTER TABLE dim_material
  ADD COLUMN IF NOT EXISTS upstream_benchmark_slug TEXT;

COMMENT ON COLUMN dim_material.upstream_benchmark_slug IS
  'Primary anchor benchmark for this driver. NULL for upstream commodity '
  'drivers themselves. For blend/recycled drivers, secondary fiber '
  'benchmarks are resolved in pricing engine code (not stored here).';

UPDATE dim_material dm
SET upstream_benchmark_slug = m.upstream
FROM (VALUES
  -- Single-fiber staple: direct mapping to commodity benchmark
  ('viscose_staple',           'rayon_yarn'),
  ('cotton_staple',            'cotton_yarn'),
  ('polyester_staple',         'polyester_yarn'),

  -- Single-fiber staple with PROXY FALLBACK (see header)
  ('modal_staple',             'rayon_yarn'),       -- proxy: modal ≈ viscose +15-25%
  ('polyamide_staple',         'polyamide_fdy'),    -- proxy: filament -> staple

  -- Two-fiber blends: anchor on dominant fiber; secondary computed in code
  ('pv_blend_staple',          'polyester_yarn'),   -- + rayon_yarn (in code)
  ('pm_blend_staple',          'polyester_yarn'),   -- + rayon_yarn proxy (in code)
  ('cotton_blend_staple',      'cotton_yarn'),      -- + variable secondary

  -- Multi-component / specialty blends: anchor on dominant fiber
  ('three_component_staple',   'polyester_yarn'),   -- typical PES-dominant
  ('corespun_staple',          'cotton_yarn'),      -- + elastane premium

  -- Recycled (GRS): anchor on virgin equivalent + recycled premium in code
  ('recycled_polyester_staple','polyester_yarn'),   -- + 15-30% rPET premium
  ('recycled_blend_staple',    'cotton_yarn')       -- + recycled premium
) AS m(slug, upstream)
WHERE dm.slug = m.slug
  AND dm.upstream_benchmark_slug IS NULL;

-- ============================================================================
-- Verification (run separately):
-- ============================================================================
--
--   SELECT slug, family, material_form, upstream_benchmark_slug
--   FROM dim_material
--   WHERE slug IN (
--     'viscose_staple','modal_staple','cotton_staple','polyester_staple',
--     'polyamide_staple','pv_blend_staple','pm_blend_staple',
--     'cotton_blend_staple','three_component_staple','corespun_staple',
--     'recycled_polyester_staple','recycled_blend_staple'
--   )
--   ORDER BY family, slug;
--
--   Expected: 12 rows, all with non-NULL upstream_benchmark_slug.
--
--   Existing 14 upstream commodities should still have NULL:
--   SELECT slug FROM dim_material
--   WHERE upstream_benchmark_slug IS NULL ORDER BY slug;
--   -- Expected: 14 rows (cotton_yarn, polyester_yarn, rayon_yarn, etc.)
-- ============================================================================
