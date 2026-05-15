-- ============================================================================
-- Migration 030 - Phase X1 Step 2: dim_hs_rayon_mapping
-- ============================================================================
-- Purpose:
--   Map 9 Comtrade HS codes (used by Export Intelligence Phase X1) to
--   Rayon-specific business context: business line, material family,
--   importance tier, and a human-readable relevance note.
--
--   This table is the join key that lets Export Intelligence display HS
--   codes with Rayon-meaningful labels (e.g. "core knit", "high-end
--   technical", "upstream yarn benchmark") instead of raw HS descriptions.
--
--   Mapping decisions are based on planning answers (15 May 2026 Q1-Q8):
--     - Q1: HS 5516 viscose woven       -> deferred to X2 (Rayon imports
--           grey + finishes; secondary tier when added).
--     - Q2: HS 6005 warp knit           -> excluded (Rayon weft/circular only).
--     - Q3: HS 5903 coating             -> PRIMARY tier (core finishing
--           capacity, "orders are substantial").
--     - Q7: ATS Group (technical fabric) -> HS 5512 + HS 5515 strategic
--           focus (high-end fabric, $/kg = $19 and $10.78 respectively).
--
-- Scope:
--   CREATE TABLE dim_hs_rayon_mapping
--   CREATE INDEX on importance_tier and business_line
--   INSERT 9 rows for current HS coverage
--
-- Logical foreign key (NOT enforced):
--   trade_flows.hs_code -> dim_hs_rayon_mapping.hs_code
--   FK NOT enforced because trade_flows may carry legacy HS codes outside
--   the mapping. JOINs use LEFT JOIN so unmapped codes still render.
--
-- Idempotent:
--   CREATE TABLE IF NOT EXISTS
--   CREATE INDEX IF NOT EXISTS
--   INSERT ... ON CONFLICT (hs_code) DO UPDATE
--   Safe to re-run for schema or row corrections.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Table definition
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dim_hs_rayon_mapping (
    hs_code         TEXT        PRIMARY KEY,
    business_line   TEXT        NOT NULL,
    material_family TEXT        NOT NULL,
    importance_tier TEXT        NOT NULL
                                CHECK (importance_tier IN ('primary','secondary','context')),
    relevance_note  TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS dim_hs_rayon_mapping_tier_idx
    ON dim_hs_rayon_mapping (importance_tier);

CREATE INDEX IF NOT EXISTS dim_hs_rayon_mapping_business_line_idx
    ON dim_hs_rayon_mapping (business_line);

-- ---------------------------------------------------------------------------
-- Seed data: 9 HS codes
--
-- business_line values:   'knit' | 'woven' | 'yarn' | 'finishing'
-- material_family values: 'synthetic_filament' | 'synthetic_staple' |
--                         'synthetic_staple_blend' | 'artificial_staple' |
--                         'pile' | 'coated_textile'
-- importance_tier values: 'primary' | 'secondary' | 'context'
-- ---------------------------------------------------------------------------

INSERT INTO dim_hs_rayon_mapping
    (hs_code, business_line, material_family, importance_tier, relevance_note)
VALUES
    ('5407', 'woven',     'synthetic_filament',     'primary',
     'Main woven product - PES filament fabric, backbone of Rayon woven line'),

    ('6006', 'knit',      'synthetic_staple',       'primary',
     'Main knit product - synthetic staple circular knit, backbone of Rayon knit line'),

    ('5512', 'woven',     'synthetic_staple',       'secondary',
     'High-end technical fabric (>=85% synthetic staple, ~$19/kg) - ATS Group / technical textile sweet spot'),

    ('5515', 'woven',     'synthetic_staple_blend', 'secondary',
     'Blended technical fabric (synthetic staple mixes, ~$10.78/kg) - technical textile market'),

    ('6001', 'knit',      'pile',                   'secondary',
     'Pile / velour knit - specialty knit category (terry, fleece, velour)'),

    ('5402', 'yarn',      'synthetic_filament',     'secondary',
     'Upstream PES filament yarn - commodity benchmark, fabric cost base'),

    ('5509', 'yarn',      'synthetic_staple',       'secondary',
     'Upstream synthetic staple yarn - raw material for HS 5512 / HS 5515'),

    ('5510', 'yarn',      'artificial_staple',      'secondary',
     'Viscose / modal / lyocell yarn - upstream cost in Rayon import-finish model'),

    ('5903', 'finishing', 'coated_textile',         'primary',
     'Coating / lamination - core finishing capacity, substantial order volume')

ON CONFLICT (hs_code) DO UPDATE SET
    business_line   = EXCLUDED.business_line,
    material_family = EXCLUDED.material_family,
    importance_tier = EXCLUDED.importance_tier,
    relevance_note  = EXCLUDED.relevance_note,
    updated_at      = NOW();

COMMIT;

-- ---------------------------------------------------------------------------
-- Post-migration verification (run manually after apply)
-- ---------------------------------------------------------------------------
-- SELECT hs_code, business_line, material_family, importance_tier,
--        substr(relevance_note, 1, 60) AS note_preview
-- FROM dim_hs_rayon_mapping
-- ORDER BY
--   CASE importance_tier
--     WHEN 'primary'   THEN 1
--     WHEN 'secondary' THEN 2
--     ELSE 3
--   END,
--   hs_code;
--
-- Expected: 9 rows total.
--   Primary   (3): 5407, 6006, 5903
--   Secondary (6): 5402, 5509, 5510, 5512, 5515, 6001
-- ---------------------------------------------------------------------------
