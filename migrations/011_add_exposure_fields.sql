-- Migration 011: Add 6 exposure layer fields to market_signals
-- Phase E P1 step 2
-- Status: APPLY MANUALLY in next session (after LLM prompt + validation updates)
-- This file is committed for review; do NOT auto-apply

BEGIN;

-- Add 6 new columns (NULL allowed; backfilled later via heuristic SQL or LLM reanalysis)
ALTER TABLE market_signals ADD COLUMN IF NOT EXISTS rayon_why_it_matters TEXT;
ALTER TABLE market_signals ADD COLUMN IF NOT EXISTS affected_business_line JSONB;
ALTER TABLE market_signals ADD COLUMN IF NOT EXISTS affected_material_family JSONB;
ALTER TABLE market_signals ADD COLUMN IF NOT EXISTS commercial_exposure_type VARCHAR(30);
ALTER TABLE market_signals ADD COLUMN IF NOT EXISTS entity_name TEXT;
ALTER TABLE market_signals ADD COLUMN IF NOT EXISTS entity_role VARCHAR(30);

-- CHECK constraint: commercial_exposure_type enum
ALTER TABLE market_signals
ADD CONSTRAINT chk_commercial_exposure_type
CHECK (commercial_exposure_type IS NULL OR commercial_exposure_type IN (
    'INPUT_COST', 'OUTPUT_DEMAND', 'EXPORT_TRADE',
    'REGULATORY_COMPLIANCE', 'COMPETITIVE_POSITION',
    'TECH_INNOVATION', 'OTHER'
));

-- CHECK constraint: entity_role enum
ALTER TABLE market_signals
ADD CONSTRAINT chk_entity_role
CHECK (entity_role IS NULL OR entity_role IN (
    'subject', 'competitor', 'supplier', 'customer',
    'regulator', 'partner', 'other'
));

-- CHECK constraint: affected_business_line must be JSONB array
ALTER TABLE market_signals
ADD CONSTRAINT chk_affected_business_line_array
CHECK (
    affected_business_line IS NULL
    OR jsonb_typeof(affected_business_line) = 'array'
);

-- CHECK constraint: affected_material_family must be JSONB array
ALTER TABLE market_signals
ADD CONSTRAINT chk_affected_material_family_array
CHECK (
    affected_material_family IS NULL
    OR jsonb_typeof(affected_material_family) = 'array'
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_market_signals_commercial_exposure
    ON market_signals(commercial_exposure_type)
    WHERE commercial_exposure_type IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_market_signals_entity_role
    ON market_signals(entity_role)
    WHERE entity_role IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_market_signals_business_line_gin
    ON market_signals USING GIN (affected_business_line);

CREATE INDEX IF NOT EXISTS idx_market_signals_material_family_gin
    ON market_signals USING GIN (affected_material_family);

COMMIT;

-- Verification queries (run after apply):
-- SELECT column_name, data_type FROM information_schema.columns
--   WHERE table_name='market_signals'
--     AND column_name IN ('rayon_why_it_matters','affected_business_line','affected_material_family',
--                         'commercial_exposure_type','entity_name','entity_role');
-- SELECT conname FROM pg_constraint WHERE conrelid='market_signals'::regclass
--   AND conname IN ('chk_commercial_exposure_type','chk_entity_role',
--                   'chk_affected_business_line_array','chk_affected_material_family_array');
-- SELECT indexname FROM pg_indexes WHERE tablename='market_signals'
--   AND indexname LIKE 'idx_market_signals_%exposure%' OR indexname LIKE 'idx_market_signals_%gin%';