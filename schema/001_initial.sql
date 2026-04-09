-- Rayon Intelligence Platform — Initial Schema
-- Phase 1A: Market Intelligence

BEGIN;

-- ─────────────────────────────────────────────
-- Extensions
-- ─────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

-- ─────────────────────────────────────────────
-- companies
-- Tracked competitor and market entities.
-- ─────────────────────────────────────────────
CREATE TABLE companies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    country         TEXT,
    category        TEXT,                   -- e.g. 'competitor', 'customer', 'supplier'
    tags            TEXT[],                 -- e.g. '{knit, woven, denim}'
    website         TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- news_items
-- Scraped articles and press items.
-- Deduplication: url_hash UNIQUE.
-- ─────────────────────────────────────────────
CREATE TABLE news_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url             TEXT NOT NULL,
    url_hash        TEXT NOT NULL UNIQUE GENERATED ALWAYS AS (encode(digest(url, 'sha256'), 'hex')) STORED,
    source          TEXT NOT NULL,          -- scraper source identifier, e.g. 'tekstil_magazin'
    title           TEXT,
    body_raw        TEXT,                   -- raw scraped text before LLM processing
    body_summary    TEXT,                   -- LLM-generated summary
    published_at    TIMESTAMPTZ,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    language        TEXT,                   -- 'tr', 'en', 'ru', etc.
    company_id      UUID REFERENCES companies(id) ON DELETE SET NULL,
    llm_model       TEXT,                   -- e.g. 'gpt-4o-mini'
    llm_tokens_in   INT,
    llm_tokens_out  INT,
    llm_cost_usd    NUMERIC(10, 6),
    tags            TEXT[],
    relevance_score NUMERIC(4, 3),          -- 0.000–1.000, LLM-assigned
    CONSTRAINT relevance_range CHECK (relevance_score IS NULL OR relevance_score BETWEEN 0 AND 1)
);

CREATE INDEX news_items_source_idx        ON news_items (source);
CREATE INDEX news_items_published_at_idx  ON news_items (published_at DESC);
CREATE INDEX news_items_company_id_idx    ON news_items (company_id);
CREATE INDEX news_items_scraped_at_idx    ON news_items (scraped_at DESC);

-- ─────────────────────────────────────────────
-- trade_flows
-- Import/export trade data from external sources.
-- ─────────────────────────────────────────────
CREATE TABLE trade_flows (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url             TEXT,
    url_hash        TEXT UNIQUE GENERATED ALWAYS AS (
                        CASE WHEN url IS NOT NULL THEN encode(digest(url, 'sha256'), 'hex') END
                    ) STORED,
    source          TEXT NOT NULL,          -- e.g. 'tuik', 'trademap', 'zauba'
    reporter_country TEXT,
    partner_country  TEXT,
    hs_code         TEXT,                   -- HS chapter/heading, e.g. '5208', '6006'
    trade_flow      TEXT,                   -- 'import' | 'export'
    period          DATE,                   -- first day of the reported period
    period_type     TEXT,                   -- 'monthly' | 'quarterly' | 'annual'
    value_usd       NUMERIC(18, 2),
    quantity_kg     NUMERIC(18, 3),
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    llm_model       TEXT,
    llm_tokens_in   INT,
    llm_tokens_out  INT,
    llm_cost_usd    NUMERIC(10, 6),
    notes           TEXT
);

CREATE INDEX trade_flows_hs_code_idx      ON trade_flows (hs_code);
CREATE INDEX trade_flows_period_idx       ON trade_flows (period DESC);
CREATE INDEX trade_flows_reporter_idx     ON trade_flows (reporter_country);

-- ─────────────────────────────────────────────
-- market_signals
-- Processed intelligence signals derived from
-- news_items or trade_flows after LLM analysis.
-- ─────────────────────────────────────────────
CREATE TABLE market_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_type     TEXT NOT NULL,          -- e.g. 'price_move', 'capacity_change', 'new_entrant'
    severity        TEXT NOT NULL DEFAULT 'info',  -- 'info' | 'warning' | 'alert'
    title           TEXT NOT NULL,
    body            TEXT,
    source_table    TEXT,                   -- 'news_items' | 'trade_flows'
    source_id       UUID,                   -- FK-by-convention to source_table row
    company_id      UUID REFERENCES companies(id) ON DELETE SET NULL,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notified_at     TIMESTAMPTZ,            -- set when Telegram/email notification sent
    llm_model       TEXT,
    llm_tokens_in   INT,
    llm_tokens_out  INT,
    llm_cost_usd    NUMERIC(10, 6),
    tags            TEXT[],
    CONSTRAINT severity_values CHECK (severity IN ('info', 'warning', 'alert'))
);

CREATE INDEX market_signals_type_idx      ON market_signals (signal_type);
CREATE INDEX market_signals_severity_idx  ON market_signals (severity);
CREATE INDEX market_signals_detected_idx  ON market_signals (detected_at DESC);
CREATE INDEX market_signals_notified_idx  ON market_signals (notified_at) WHERE notified_at IS NULL;

-- ─────────────────────────────────────────────
-- failed_jobs
-- Dead-letter queue for all pipeline errors.
-- Records are never deleted automatically.
-- ─────────────────────────────────────────────
CREATE TABLE failed_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline        TEXT NOT NULL,          -- e.g. 'tekstil_magazin_scraper'
    job_type        TEXT NOT NULL,          -- e.g. 'scrape', 'llm_summarise', 'insert'
    payload         JSONB,                  -- original job payload for replay
    error_message   TEXT,
    error_detail    TEXT,                   -- full stack trace or raw response
    url             TEXT,                   -- if job was URL-based
    failed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retry_count     INT NOT NULL DEFAULT 0,
    resolved_at     TIMESTAMPTZ,            -- set when manually reviewed/replayed
    resolved_by     TEXT
);

CREATE INDEX failed_jobs_pipeline_idx     ON failed_jobs (pipeline);
CREATE INDEX failed_jobs_failed_at_idx    ON failed_jobs (failed_at DESC);
CREATE INDEX failed_jobs_unresolved_idx   ON failed_jobs (failed_at DESC) WHERE resolved_at IS NULL;

-- ─────────────────────────────────────────────
-- Trigger: keep updated_at current on companies
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
