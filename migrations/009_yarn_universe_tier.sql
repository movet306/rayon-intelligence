-- ============================================================================
-- Migration 009 — Yarn Universe Tier Meta-Model
-- ============================================================================
-- Purpose:
--   Introduce 3-layer universe tagging on dim_yarn_master so that we can
--   distinguish between:
--     * specs that are common in the wider yarn market
--     * specs that Rayon has actually confirmed using
--     * specs that we are actively tracking on the live dashboard
--
--   Adds supporting metadata fields for pricing basis, confirmation source,
--   blend ratio, and spec definition confidence.
--
-- Scope:
--   This migration ONLY extends dim_yarn_master meta-model.
--   It does NOT touch dim_yarn_price_driver. Premium-rules JSON expansion
--   (color/twist/ply/grade/specialty profile) belongs to Phase C.
--
-- Backfill rules (current 21 specs):
--   * is_rayon_confirmed   = TRUE  for all 21
--   * confirmation_source  = 'legacy_seed' for all 21
--   * is_market_common     = TRUE  for poly/PA non-placeholder specs (20)
--   * pricing_basis        = 'estimate' for non-placeholder specs (20)
--   * pricing_basis        = NULL for placeholder spec (1, PA66)
--   * spec_confidence      = 'medium' for non-placeholder specs
--   * spec_confidence      = 'low'    for placeholder spec
--   * is_active_tracked    = FALSE  for all (set later by separate UPDATE)
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1) New columns
-- ----------------------------------------------------------------------------
ALTER TABLE dim_yarn_master
  ADD COLUMN is_market_common    BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN is_rayon_confirmed  BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN is_active_tracked   BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN pricing_basis       TEXT,
  ADD COLUMN confirmation_source TEXT,
  ADD COLUMN blend_ratio_json    JSONB,
  ADD COLUMN spec_confidence     TEXT;

-- ----------------------------------------------------------------------------
-- 2) Column documentation
-- ----------------------------------------------------------------------------
COMMENT ON COLUMN dim_yarn_master.is_market_common IS
  'TRUE if this spec is commonly used in the wider yarn market.';

COMMENT ON COLUMN dim_yarn_master.is_rayon_confirmed IS
  'TRUE if Rayon has confirmed using this spec (purchase, quote, sales usage, or legacy seed).';

COMMENT ON COLUMN dim_yarn_master.is_active_tracked IS
  'TRUE if this spec is actively tracked on the live dashboard. Subset of rayon_confirmed.';

COMMENT ON COLUMN dim_yarn_master.pricing_basis IS
  'How the price for this spec is sourced or modeled. Allowed values: '
  'direct = directly used purchasable material/spec; '
  'benchmark = tracked external benchmark; '
  'proxy = related upstream proxy; '
  'estimate = driver-linked modeled yarn estimate.';

COMMENT ON COLUMN dim_yarn_master.confirmation_source IS
  'How this spec was confirmed as part of Rayon usage. Allowed values: '
  'manual, purchase_history, quote, sales_usage, legacy_seed.';

COMMENT ON COLUMN dim_yarn_master.blend_ratio_json IS
  'JSON object describing fiber composition for blends. '
  'Example: {"PES":65,"VIS":35}. NULL for single-fiber specs.';

COMMENT ON COLUMN dim_yarn_master.spec_confidence IS
  'Confidence in the spec definition itself, NOT pricing confidence. '
  'Allowed values: high, medium, low.';

-- ----------------------------------------------------------------------------
-- 3) Constraints
-- ----------------------------------------------------------------------------

-- active_tracked implies rayon_confirmed
ALTER TABLE dim_yarn_master
  ADD CONSTRAINT chk_active_requires_confirmed
  CHECK (NOT is_active_tracked OR is_rayon_confirmed);

-- active_tracked requires a pricing_basis
ALTER TABLE dim_yarn_master
  ADD CONSTRAINT chk_active_requires_pricing_basis
  CHECK (NOT is_active_tracked OR pricing_basis IS NOT NULL);

-- pricing_basis enum
ALTER TABLE dim_yarn_master
  ADD CONSTRAINT chk_pricing_basis_enum
  CHECK (pricing_basis IS NULL OR pricing_basis IN
    ('direct','benchmark','proxy','estimate'));

-- confirmation_source enum
ALTER TABLE dim_yarn_master
  ADD CONSTRAINT chk_confirmation_source_enum
  CHECK (confirmation_source IS NULL OR confirmation_source IN
    ('manual','purchase_history','quote','sales_usage','legacy_seed'));

-- spec_confidence enum
ALTER TABLE dim_yarn_master
  ADD CONSTRAINT chk_spec_confidence_enum
  CHECK (spec_confidence IS NULL OR spec_confidence IN
    ('high','medium','low'));

-- ----------------------------------------------------------------------------
-- 4) Backfill — tüm 21 spec rayon_confirmed + legacy_seed
-- ----------------------------------------------------------------------------
UPDATE dim_yarn_master
SET
  is_rayon_confirmed  = TRUE,
  confirmation_source = 'legacy_seed';

-- ----------------------------------------------------------------------------
-- 5) Backfill — non-placeholder 20 spec: market_common, estimate, medium
-- ----------------------------------------------------------------------------
UPDATE dim_yarn_master
SET
  is_market_common = TRUE,
  pricing_basis    = 'estimate',
  spec_confidence  = 'medium'
WHERE fiber_family IN ('polyester','polyamide')
  AND is_placeholder = FALSE;

-- ----------------------------------------------------------------------------
-- 6) Backfill — placeholder spec (PA66): low confidence, no pricing basis
-- ----------------------------------------------------------------------------
UPDATE dim_yarn_master
SET spec_confidence = 'low'
WHERE is_placeholder = TRUE;
-- Note: pricing_basis stays NULL, is_market_common stays FALSE,
--       is_active_tracked stays FALSE (default).

COMMIT;

-- ============================================================================
-- Verification queries (run separately after migration applies)
-- ============================================================================
--
-- Check new columns exist:
--   \d dim_yarn_master
--
-- Check backfill counts:
--   SELECT
--     COUNT(*)                                            AS total,
--     COUNT(*) FILTER (WHERE is_rayon_confirmed)          AS confirmed,
--     COUNT(*) FILTER (WHERE is_market_common)            AS market_common,
--     COUNT(*) FILTER (WHERE is_active_tracked)           AS active,
--     COUNT(*) FILTER (WHERE pricing_basis = 'estimate')  AS estimate,
--     COUNT(*) FILTER (WHERE pricing_basis IS NULL)       AS no_basis,
--     COUNT(*) FILTER (WHERE spec_confidence = 'medium')  AS conf_medium,
--     COUNT(*) FILTER (WHERE spec_confidence = 'low')     AS conf_low
--   FROM dim_yarn_master;
--
-- Expected:
--   total=21, confirmed=21, market_common=20, active=0,
--   estimate=20, no_basis=1, conf_medium=20, conf_low=1
--
-- Try to violate active->confirmed constraint (should ERROR):
--   UPDATE dim_yarn_master SET is_active_tracked = TRUE, is_rayon_confirmed = FALSE
--   WHERE yarn_id = 1;
-- ============================================================================
