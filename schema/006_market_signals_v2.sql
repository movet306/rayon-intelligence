-- Rayon Intelligence Platform — Market Signals v2
-- Adds structured signal taxonomy: impact scoring, material hierarchy,
-- action tags, signal categories, and Rayon-specific relevance fields.

BEGIN;

-- ─────────────────────────────────────────────
-- market_signals: new intelligence fields
-- ─────────────────────────────────────────────
ALTER TABLE market_signals
    ADD COLUMN IF NOT EXISTS impact_score      INTEGER      DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS time_horizon      TEXT         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS action_tag        TEXT         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS signal_category   TEXT         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS material_form     TEXT         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS theme             TEXT         DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS affected_products TEXT[]       DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS rayon_relevance   TEXT         DEFAULT NULL;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_impact_score') THEN
        ALTER TABLE market_signals ADD CONSTRAINT chk_impact_score
            CHECK (impact_score IS NULL OR (impact_score >= 0 AND impact_score <= 100));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_time_horizon') THEN
        ALTER TABLE market_signals ADD CONSTRAINT chk_time_horizon
            CHECK (time_horizon IS NULL OR time_horizon IN ('short', 'mid', 'long'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_action_tag') THEN
        ALTER TABLE market_signals ADD CONSTRAINT chk_action_tag
            CHECK (action_tag IS NULL OR action_tag IN ('MONITOR', 'RISK', 'OPPORTUNITY'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_signal_category') THEN
        ALTER TABLE market_signals ADD CONSTRAINT chk_signal_category
            CHECK (signal_category IS NULL OR signal_category IN
                   ('COST_IMPACT', 'DEMAND_SHIFT', 'SUPPLY_RISK', 'COMPETITOR_MOVE', 'REGULATORY'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_rayon_relevance') THEN
        ALTER TABLE market_signals ADD CONSTRAINT chk_rayon_relevance
            CHECK (rayon_relevance IS NULL OR rayon_relevance IN ('direct', 'indirect', 'none'));
    END IF;
END $$;

-- ─────────────────────────────────────────────
-- dim_material: Rayon-specific enrichment
-- ─────────────────────────────────────────────
ALTER TABLE dim_material
    ADD COLUMN IF NOT EXISTS rayon_relevance_score INTEGER DEFAULT 3,
    ADD COLUMN IF NOT EXISTS material_form         TEXT    DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS applications          TEXT[]  DEFAULT NULL;

-- Seed Rayon-specific context per material
UPDATE dim_material SET
    material_form = 'staple_fiber',
    applications  = ARRAY['knit', 'woven'],
    rayon_relevance_score = 4
WHERE slug = 'polyester_staple_fiber';

UPDATE dim_material SET
    material_form = 'filament',
    applications  = ARRAY['woven'],
    rayon_relevance_score = 5
WHERE slug = 'polyester_fdy';

UPDATE dim_material SET
    material_form = 'filament',
    applications  = ARRAY['woven', 'texturize_input'],
    rayon_relevance_score = 5
WHERE slug = 'polyester_poy';

UPDATE dim_material SET
    material_form = 'texturized_filament',
    applications  = ARRAY['knit'],
    rayon_relevance_score = 5
WHERE slug = 'polyester_dty';

UPDATE dim_material SET
    material_form = 'filament',
    applications  = ARRAY['technical', 'woven', 'knit'],
    rayon_relevance_score = 5
WHERE slug = 'polyamide_fdy';

UPDATE dim_material SET
    material_form = 'chip_upstream',
    applications  = ARRAY['upstream'],
    rayon_relevance_score = 3
WHERE slug = 'pa6_chip';

UPDATE dim_material SET
    material_form = 'chip_upstream',
    applications  = ARRAY['upstream'],
    rayon_relevance_score = 2
WHERE slug = 'pa66_chip';

UPDATE dim_material SET
    material_form = 'lint',
    applications  = ARRAY['yarn_input'],
    rayon_relevance_score = 2
WHERE slug = 'cotton_lint';

UPDATE dim_material SET
    material_form = 'spun_yarn',
    applications  = ARRAY['woven', 'knit'],
    rayon_relevance_score = 3
WHERE slug = 'cotton_yarn';

UPDATE dim_material SET
    material_form = 'filament_yarn',
    applications  = ARRAY['woven', 'knit'],
    rayon_relevance_score = 4
WHERE slug = 'rayon_yarn';

UPDATE dim_material SET
    material_form = 'upstream_chemical',
    applications  = ARRAY['upstream'],
    rayon_relevance_score = 3
WHERE slug = 'pta';

COMMIT;
