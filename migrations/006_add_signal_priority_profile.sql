-- Migration 006: Add signal_priority_profile column to market_signals
-- Phase E P0-B (ChatGPT gap #1 integration)
-- Enum stored as VARCHAR with CHECK constraint (more flexible than Postgres ENUM type)

ALTER TABLE market_signals
ADD COLUMN IF NOT EXISTS signal_priority_profile VARCHAR(20);

-- CHECK constraint added separately so it can be modified without recreation
ALTER TABLE market_signals
DROP CONSTRAINT IF EXISTS check_signal_priority_profile;

ALTER TABLE market_signals
ADD CONSTRAINT check_signal_priority_profile
CHECK (signal_priority_profile IS NULL OR signal_priority_profile IN
    ('COST', 'DEMAND', 'REGULATION', 'SUSTAINABILITY', 'EXPORT', 'OTHER'));