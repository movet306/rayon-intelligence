-- migrations/013_create_tenders.sql
-- Phase F0: Tender Intelligence — canonical tenders table
-- Idempotent: safe to re-run

BEGIN;

CREATE TABLE IF NOT EXISTS tenders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source identification
    source TEXT NOT NULL,
    ekap_id TEXT NOT NULL,
    source_url TEXT,

    -- Core fields
    title TEXT NOT NULL,
    description TEXT,
    institution TEXT NOT NULL,
    institution_city TEXT,
    procurement_type TEXT,
    procurement_method TEXT,
    cpv_code TEXT,
    cpv_description TEXT,

    -- Financial
    estimated_value_try NUMERIC(18, 2),
    estimated_value_disclosed BOOLEAN DEFAULT FALSE,
    currency TEXT DEFAULT 'TRY',

    -- Timestamps
    published_at TIMESTAMP WITH TIME ZONE,
    deadline_at TIMESTAMP WITH TIME ZONE,
    discovered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Status
    tender_status TEXT NOT NULL,
    status_last_checked_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Raw payload (preserved for replay / audit)
    raw_text TEXT,
    raw_payload JSONB,

    -- Relevance assessment (filled by Gold layer)
    relevance_level TEXT,
    relevance_score INTEGER,
    matched_keywords TEXT[],
    rejection_reason TEXT,

    -- Rayon-specific scoring (filled by LLM in F3+)
    fit_technical_textile INTEGER,
    fit_protective_clothing INTEGER,
    fit_military INTEGER,
    fit_waterproof INTEGER,
    fit_fr INTEGER,
    estimated_competition TEXT,
    likely_buyer_type TEXT,

    -- LLM trace
    llm_model TEXT,
    llm_tokens_in INTEGER,
    llm_tokens_out INTEGER,
    llm_cost_usd NUMERIC(10, 6),
    llm_processed_at TIMESTAMP WITH TIME ZONE,

    -- Exposure layer (mirrors Mig 011 on market_signals)
    rayon_why_it_matters TEXT,
    affected_business_line JSONB,
    affected_material_family JSONB,
    category TEXT,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT tenders_source_ekap_id_uq UNIQUE (source, ekap_id),
    CONSTRAINT chk_tender_status CHECK (tender_status IN ('open','closed','cancelled','evaluating','awarded','unknown')),
    CONSTRAINT chk_relevance_level CHECK (relevance_level IS NULL OR relevance_level IN ('HIGH','MEDIUM','LOW','REJECTED')),
    CONSTRAINT chk_relevance_score CHECK (relevance_score IS NULL OR (relevance_score BETWEEN 0 AND 100)),
    CONSTRAINT chk_procurement_type CHECK (procurement_type IS NULL OR procurement_type IN ('Mal','Hizmet','Yapım','Danışmanlık'))
);

-- Active tenders convenience view (replaces non-immutable GENERATED column idea)
CREATE OR REPLACE VIEW v_active_tenders AS
SELECT *
FROM tenders
WHERE tender_status = 'open'
  AND deadline_at > NOW();

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tenders_status        ON tenders(tender_status);
CREATE INDEX IF NOT EXISTS idx_tenders_deadline      ON tenders(deadline_at) WHERE tender_status = 'open';
CREATE INDEX IF NOT EXISTS idx_tenders_relevance     ON tenders(relevance_level);
CREATE INDEX IF NOT EXISTS idx_tenders_published     ON tenders(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenders_kw_gin        ON tenders USING GIN(matched_keywords);
CREATE INDEX IF NOT EXISTS idx_tenders_bizline_gin   ON tenders USING GIN(affected_business_line);
CREATE INDEX IF NOT EXISTS idx_tenders_matfam_gin    ON tenders USING GIN(affected_material_family);

COMMIT;
