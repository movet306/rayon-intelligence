-- migrations/014_create_tender_keywords_history.sql
-- Phase F0: Keyword lookup table + relevance history audit log
-- Idempotent: safe to re-run

BEGIN;

CREATE TABLE IF NOT EXISTS lkp_tender_keywords (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword TEXT NOT NULL UNIQUE,
    normalized TEXT NOT NULL,
    keyword_class TEXT NOT NULL,
    weight INTEGER NOT NULL DEFAULT 10,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_kw_class CHECK (keyword_class IN ('high_priority','medium_priority','exclusion')),
    CONSTRAINT chk_kw_weight CHECK (weight BETWEEN -100 AND 100)
);

CREATE INDEX IF NOT EXISTS idx_tender_kw_class ON lkp_tender_keywords(keyword_class);
CREATE INDEX IF NOT EXISTS idx_tender_kw_norm  ON lkp_tender_keywords(normalized);

CREATE TABLE IF NOT EXISTS tender_relevance_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tender_id UUID NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    assessed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    engine_version TEXT NOT NULL,
    method TEXT NOT NULL,
    relevance_level TEXT,
    relevance_score INTEGER,
    matched_keywords TEXT[],
    rejection_reason TEXT,
    reasoning TEXT,
    llm_model TEXT,
    llm_cost_usd NUMERIC(10, 6),
    CONSTRAINT chk_trh_relevance_level CHECK (relevance_level IS NULL OR relevance_level IN ('HIGH','MEDIUM','LOW','REJECTED'))
);

CREATE INDEX IF NOT EXISTS idx_trh_tender   ON tender_relevance_history(tender_id, assessed_at DESC);
CREATE INDEX IF NOT EXISTS idx_trh_assessed ON tender_relevance_history(assessed_at DESC);

COMMIT;
