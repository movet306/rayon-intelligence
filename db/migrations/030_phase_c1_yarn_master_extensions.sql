-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 030: Phase C+1 — dim_yarn_master extensions for spun yarn + sheet sync
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Background: dim_yarn_master was originally designed for filament yarns
-- (denier + filament_count, e.g., PES_75D_72F). Phase C+1 brings 67+ yarn
-- specs from the evidence sheet, including:
--   - Spun yarns (viscose, modal, cotton, blends): Ne count + ply + twist
--   - Subfamily classification (staple_ring, staple_vortex, etc.)
--   - Color states (ECRU, BLACK, COLORED)
--   - Specialty flags (recycled blend ratios, etc.)
--   - Primary/secondary driver slugs for blend pricing logic
--
-- Pricing impact: yarn-level pricing engine (Phase C) will automatically
-- include new yarns once dim_yarn_master is populated. driver_inference
-- module already handles all spun yarn driver slugs (Phase B5).
--
-- Idempotent: uses ADD COLUMN IF NOT EXISTS, safe to re-run.
-- ═══════════════════════════════════════════════════════════════════════════


-- ─── 1. Yarn count system discriminator ────────────────────────────────────
-- 'denier' for filament yarns (PES, PA66), 'Ne' for spun yarns (viscose, cotton)
ALTER TABLE dim_yarn_master
  ADD COLUMN IF NOT EXISTS count_type TEXT
    CHECK (count_type IN ('denier', 'Ne', 'tex', 'dtex') OR count_type IS NULL);


-- ─── 2. Spun yarn properties ───────────────────────────────────────────────
-- Ne count: cotton count system (e.g., 30 = Ne 30/1)
ALTER TABLE dim_yarn_master
  ADD COLUMN IF NOT EXISTS ne_count NUMERIC(6,2);

-- Ply: 1, 2, 3 (single, two-fold, three-fold)
ALTER TABLE dim_yarn_master
  ADD COLUMN IF NOT EXISTS ply SMALLINT
    CHECK (ply IS NULL OR (ply >= 1 AND ply <= 12));

-- Twist direction: S or Z
ALTER TABLE dim_yarn_master
  ADD COLUMN IF NOT EXISTS twist_direction TEXT
    CHECK (twist_direction IN ('S', 'Z') OR twist_direction IS NULL);


-- ─── 3. Subfamily (taxonomy detail) ────────────────────────────────────────
-- Examples: staple_ring, staple_vortex, staple_oe, multi_filament_textured,
--           multi_filament_flat, mono_filament, corespun, melange
ALTER TABLE dim_yarn_master
  ADD COLUMN IF NOT EXISTS subfamily TEXT;


-- ─── 4. Color state ────────────────────────────────────────────────────────
-- ECRU (raw white), BLACK, NAVY, COLORED, MELANGE
ALTER TABLE dim_yarn_master
  ADD COLUMN IF NOT EXISTS color_state TEXT;


-- ─── 5. Specialty flags (free-form) ────────────────────────────────────────
-- Examples: 'GOTS_certified', 'GRS_certified', 'EcoVero', 'antimicrobial'
-- Stored as text for now; may convert to TEXT[] in Phase D if needed.
ALTER TABLE dim_yarn_master
  ADD COLUMN IF NOT EXISTS specialty_flags TEXT;


-- ─── 6. Primary driver slug (FK to dim_material) ───────────────────────────
-- Replaces dependency on dim_yarn_price_driver for new yarns. Existing 21
-- yarns will be back-filled from dim_yarn_price_driver in seed step below.
ALTER TABLE dim_yarn_master
  ADD COLUMN IF NOT EXISTS primary_driver_slug TEXT
    REFERENCES dim_material(slug) ON DELETE SET NULL;


-- ─── 7. Secondary driver slug (for blend yarns) ────────────────────────────
-- Examples: PV blend → primary=viscose_staple, secondary=polyester_staple
ALTER TABLE dim_yarn_master
  ADD COLUMN IF NOT EXISTS secondary_driver_slug TEXT
    REFERENCES dim_material(slug) ON DELETE SET NULL;


-- ─── 8. Sheet sync metadata ────────────────────────────────────────────────
-- sheet_row_id: '{tab}_{row_number}' e.g., 'viscose_2', 'cotton_5'
-- sheet_synced_at: last sync timestamp for this row
ALTER TABLE dim_yarn_master
  ADD COLUMN IF NOT EXISTS sheet_row_id TEXT;

ALTER TABLE dim_yarn_master
  ADD COLUMN IF NOT EXISTS sheet_synced_at TIMESTAMPTZ;


-- ─── 9. Indexes ────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_dim_yarn_master_sheet_row_id
  ON dim_yarn_master(sheet_row_id);

CREATE INDEX IF NOT EXISTS idx_dim_yarn_master_primary_driver_slug
  ON dim_yarn_master(primary_driver_slug);

CREATE INDEX IF NOT EXISTS idx_dim_yarn_master_count_type
  ON dim_yarn_master(count_type);


-- ─── 10. Seed primary_driver_slug for existing 21 yarns ────────────────────
-- Pull from dim_yarn_price_driver where ym.primary_driver_slug is still NULL.
-- This unifies driver lookup so endpoint can read from dim_yarn_master
-- alone going forward (dim_yarn_price_driver remains for legacy compat).
UPDATE dim_yarn_master ym
SET primary_driver_slug = yd.primary_driver_slug
FROM dim_yarn_price_driver yd
WHERE ym.yarn_id = yd.yarn_id
  AND ym.primary_driver_slug IS NULL
  AND yd.primary_driver_slug IS NOT NULL;


-- ─── 11. Verification queries ──────────────────────────────────────────────
-- Run these manually after migration to confirm:
--
--   SELECT COUNT(*) FROM dim_yarn_master WHERE primary_driver_slug IS NOT NULL;
--   -- Expected: 21 (all existing yarns seeded)
--
--   SELECT column_name, data_type
--   FROM information_schema.columns
--   WHERE table_name = 'dim_yarn_master'
--     AND column_name IN (
--       'count_type', 'ne_count', 'ply', 'twist_direction', 'subfamily',
--       'color_state', 'specialty_flags', 'primary_driver_slug',
--       'secondary_driver_slug', 'sheet_row_id', 'sheet_synced_at'
--     );
--   -- Expected: 11 rows
