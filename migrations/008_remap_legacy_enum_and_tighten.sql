-- Migration 008: Remap legacy signal_category enum values + tighten constraint
-- Phase E P0-B follow-up: now that all legacy values have been mapped to
-- new equivalents via LEGACY_SIGNAL_CAT_MAP (in scrapers/llm_analyzer.py),
-- this migration brings the DB into final new-only state.

-- Part 1: Remap remaining legacy enum values in market_signals
UPDATE market_signals
SET signal_category = CASE signal_category
    WHEN 'COST_IMPACT'  THEN 'RAW_MATERIAL'
    WHEN 'DEMAND_SHIFT' THEN 'MARKET_DEMAND'
    WHEN 'SUPPLY_RISK'  THEN 'SUPPLY_CHAIN'
    ELSE signal_category
END
WHERE signal_category IN ('COST_IMPACT', 'DEMAND_SHIFT', 'SUPPLY_RISK');

-- Part 2: Tighten constraint - drop legacy values from allowed set
ALTER TABLE market_signals DROP CONSTRAINT IF EXISTS chk_signal_category;

ALTER TABLE market_signals
ADD CONSTRAINT chk_signal_category
CHECK (signal_category IS NULL OR signal_category IN (
    'REGULATORY', 'TRADE_POLICY', 'RAW_MATERIAL', 'TECHNOLOGY',
    'MARKET_DEMAND', 'COMPETITOR_MOVE', 'SUPPLY_CHAIN',
    'SUSTAINABILITY', 'OTHER'
));