-- Migration 007: Relax chk_signal_category to accept new 9-value enum
-- Phase E P0-B hotfix: old constraint only allowed legacy 5 values, blocked
-- all new schema writes including OTHER fallback and new categories like
-- RAW_MATERIAL, TRADE_POLICY, SUSTAINABILITY, etc.

ALTER TABLE market_signals DROP CONSTRAINT IF EXISTS chk_signal_category;

ALTER TABLE market_signals
ADD CONSTRAINT chk_signal_category
CHECK (signal_category IS NULL OR signal_category IN (
    -- New 9-value enum (from ChatGPT analysis + roadmap v1.2)
    'REGULATORY', 'TRADE_POLICY', 'RAW_MATERIAL', 'TECHNOLOGY',
    'MARKET_DEMAND', 'COMPETITOR_MOVE', 'SUPPLY_CHAIN',
    'SUSTAINABILITY', 'OTHER',
    -- Legacy values kept temporarily for backwards compat with existing rows
    'COST_IMPACT', 'DEMAND_SHIFT', 'SUPPLY_RISK'
));

-- Legacy values can be removed once reanalyze_last_30d.py is run to convert
-- all old enum values to the new enum equivalents via LEGACY_SIGNAL_CAT_MAP
-- in scrapers/llm_analyzer.py