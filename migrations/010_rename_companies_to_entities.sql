-- Migration 010: Rename companies -> entities, add entity_type + geography
-- Phase E P1 step 1
-- Status: APPLY MANUALLY in next session (after server.py + scrapers code updates)
-- This file is committed for review; do NOT auto-apply

BEGIN;

-- Part 1: Rename table
ALTER TABLE companies RENAME TO entities;

-- Part 2: Add new columns (NULL allowed for now, populated by migration 012)
ALTER TABLE entities ADD COLUMN IF NOT EXISTS entity_type VARCHAR(30);
ALTER TABLE entities ADD COLUMN IF NOT EXISTS geography VARCHAR(50);

-- Part 3: Heuristic backfill entity_type from category (32 existing rows all 'competitor')
UPDATE entities SET entity_type = 'competitor_tr'
WHERE category = 'competitor' AND entity_type IS NULL;

-- Part 4: Add CHECK constraint for entity_type
ALTER TABLE entities
ADD CONSTRAINT chk_entity_type
CHECK (entity_type IS NULL OR entity_type IN (
    'supplier', 'competitor_tr', 'competitor_intl',
    'customer_segment', 'association', 'regulator', 'other'
));

-- Part 5: Rename market_signals.company_id -> entity_id
ALTER TABLE market_signals RENAME COLUMN company_id TO entity_id;

-- Part 6: Backwards-compat VIEW (existing code using "companies" keeps working via auto-updatable view)
CREATE OR REPLACE VIEW companies AS SELECT * FROM entities;

COMMIT;

-- Verification queries (run after apply):
-- SELECT COUNT(*) FROM entities;
-- SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type;
-- SELECT COUNT(*) FROM companies;
-- SELECT column_name FROM information_schema.columns WHERE table_name='market_signals' AND column_name='entity_id';
-- SELECT conname FROM pg_constraint WHERE conrelid='entities'::regclass;