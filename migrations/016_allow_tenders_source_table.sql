-- migrations/016_allow_tenders_source_table.sql
-- Phase F1: extend market_signals.source_table CHECK constraint to include 'tenders'.
-- Original constraint allowed: news_items, trade_flows.
-- New constraint adds: tenders (Phase F bulletin scraper), competitor_snapshots,
-- manual, other (future-proof for upcoming sources).

BEGIN;

ALTER TABLE market_signals
    DROP CONSTRAINT IF EXISTS market_signals_source_table_values;

ALTER TABLE market_signals
    ADD CONSTRAINT market_signals_source_table_values
    CHECK (source_table IS NULL OR source_table IN (
        'news_items',
        'trade_flows',
        'tenders',
        'competitor_snapshots',
        'manual',
        'other'
    ));

COMMIT;
