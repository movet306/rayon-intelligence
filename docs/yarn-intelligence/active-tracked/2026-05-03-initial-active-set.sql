-- ============================================================================
-- Initial is_active_tracked Set — 2026-05-03
-- ============================================================================
-- Type:        Versioned operational decision artifact (NOT a schema migration)
-- Companion:   2026-05-03-initial-active-set.md (decision rationale)
-- Methodology: docs/yarn-intelligence/phase-b-methodology.md
-- Schema:      migrations/009_yarn_universe_tier.sql
--
-- Purpose:
--   Mark the first 8 yarn specs as is_active_tracked = true. These are the
--   default-visible watchlist on the Yarn Intelligence dashboard.
--
-- Idempotency:
--   This script is idempotent. Running it twice produces the same final state.
--   It does NOT touch other rows; pre-existing FALSE values for non-listed
--   yarn_ids remain FALSE.
--
-- Pre-flight constraints (already verified before original execution):
--   * All 8 yarn_ids exist in dim_yarn_master
--   * All 8 have is_rayon_confirmed = TRUE        (from migration 009 backfill)
--   * All 8 have pricing_basis = 'estimate'        (from migration 009 backfill)
--   * None of the 8 are placeholders
--   * Constraints chk_active_requires_confirmed and
--     chk_active_requires_pricing_basis would otherwise reject the UPDATE.
-- ============================================================================

BEGIN;

-- Activate the 8 selected specs
UPDATE dim_yarn_master
SET is_active_tracked = TRUE
WHERE yarn_id IN (
    1,    -- PES_100D_144F
    11,   -- PES_75D_72F
    19,   -- PA6_70D_68F_DTY_S
    26,   -- PA66_470D_140F_HT
    34,   -- PES_100D_96F_ECRU
    45,   -- PES_50D_72F_ECRU
    49,   -- PES_75D_72F_DTY_ECRU_RECYCLE
    51    -- PES_75D_72F_ECRU_RECYCLE
);

-- Verify exactly 8 rows are now active_tracked
DO $$
DECLARE
  active_count INT;
BEGIN
  SELECT COUNT(*) INTO active_count
  FROM dim_yarn_master
  WHERE is_active_tracked = TRUE;

  IF active_count <> 8 THEN
    RAISE EXCEPTION 'Expected 8 active_tracked specs after this script, got %', active_count;
  END IF;
END $$;

COMMIT;

-- ============================================================================
-- Verification query (run separately):
--
--   SELECT yarn_id, yarn_code, is_active_tracked
--   FROM dim_yarn_master
--   WHERE is_active_tracked = TRUE
--   ORDER BY yarn_id;
--
-- Expected: 8 rows with yarn_ids 1, 11, 19, 26, 34, 45, 49, 51.
-- ============================================================================
