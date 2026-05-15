-- migrations/032_hs_5516_viscose_woven.sql
-- Phase X2 Step 2.1: Add HS 5516 (woven viscose/modal) to dim_hs_rayon_mapping
--
-- Rationale: Rayon's woven business line imports viscose/modal grey fabric
-- from Far East and applies dyeing/coating/lamination finishing locally.
-- HS 5510 (artificial staple yarn) already in mapping; HS 5516 is the woven
-- downstream of the same material family - import-finish model relevant.
--
-- Idempotent: ON CONFLICT updates the row to reflect latest classification.

INSERT INTO dim_hs_rayon_mapping (
    hs_code,
    business_line,
    material_family,
    importance_tier,
    relevance_note
) VALUES (
    '5516',
    'woven',
    'artificial_staple',
    'secondary',
    'Viscose/modal woven fabric - import-finish model relevant, complements HS 5510 artificial staple yarn import. Growing artificial fiber product line in Rayon woven business.'
)
ON CONFLICT (hs_code) DO UPDATE SET
    business_line   = EXCLUDED.business_line,
    material_family = EXCLUDED.material_family,
    importance_tier = EXCLUDED.importance_tier,
    relevance_note  = EXCLUDED.relevance_note,
    updated_at      = NOW();

-- Verify
SELECT
    hs_code,
    business_line,
    material_family,
    importance_tier,
    relevance_note,
    updated_at
FROM dim_hs_rayon_mapping
WHERE hs_code = '5516';