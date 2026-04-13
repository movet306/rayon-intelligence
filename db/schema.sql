-- =============================================================================
-- Rayon Intelligence Platform — PostgreSQL Schema
-- Phase 1A: Market Intelligence
--
-- Design principles:
--   • Deduplication enforced by url_hash UNIQUE (SHA-256, computed column)
--   • LLM cost tracked per row: model, tokens_in, tokens_out, cost_usd
--   • All pipeline errors land in failed_jobs (dead-letter queue)
--   • Records in failed_jobs are never auto-deleted
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- provides digest() for SHA-256

-- ---------------------------------------------------------------------------
-- ENUM types
-- ---------------------------------------------------------------------------
CREATE TYPE signal_severity AS ENUM ('info', 'warning', 'alert');
CREATE TYPE trade_flow_direction AS ENUM ('import', 'export');
CREATE TYPE period_granularity AS ENUM ('monthly', 'quarterly', 'annual');
CREATE TYPE company_category AS ENUM ('competitor', 'customer', 'supplier', 'association', 'other');

-- =============================================================================
-- TABLE: companies
-- Tracked competitor and market entities.
-- =============================================================================
CREATE TABLE companies (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    country         CHAR(2),                        -- ISO 3166-1 alpha-2
    category        company_category,
    website         TEXT,
    tags            TEXT[]      NOT NULL DEFAULT '{}',
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT companies_name_country_unique UNIQUE (name, country)
);

COMMENT ON TABLE  companies               IS 'Tracked competitor and market entities.';
COMMENT ON COLUMN companies.country       IS 'ISO 3166-1 alpha-2 country code.';
COMMENT ON COLUMN companies.tags          IS 'Free-form product/segment tags, e.g. {knit, woven, denim}.';

CREATE INDEX companies_category_idx ON companies (category);
CREATE INDEX companies_country_idx  ON companies (country);
CREATE INDEX companies_tags_idx     ON companies USING GIN (tags);

-- ---------------------------------------------------------------------------
-- Trigger: auto-update updated_at on companies
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER companies_set_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =============================================================================
-- TABLE: news_items
-- Scraped articles and press items from external sources.
-- Deduplication: url_hash UNIQUE constraint (SHA-256 of url).
-- =============================================================================
CREATE TABLE news_items (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source identification
    url             TEXT        NOT NULL,
    url_hash        TEXT        NOT NULL UNIQUE
                                GENERATED ALWAYS AS (encode(digest(url, 'sha256'), 'hex')) STORED,
    source          TEXT        NOT NULL,            -- scraper ID, e.g. 'tekstil_magazin'
    language        CHAR(2),                         -- ISO 639-1, e.g. 'tr', 'en', 'ru'

    -- Content
    title           TEXT,
    body_raw        TEXT,                            -- raw scraped text
    body_summary    TEXT,                            -- LLM-generated summary

    -- Timestamps
    published_at    TIMESTAMPTZ,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Relations
    company_id      UUID        REFERENCES companies(id) ON DELETE SET NULL,

    -- LLM cost tracking
    llm_model       TEXT,                            -- e.g. 'gpt-4o-mini'
    llm_tokens_in   INT,
    llm_tokens_out  INT,
    llm_cost_usd    NUMERIC(10, 6),

    -- Scoring
    tags            TEXT[]      NOT NULL DEFAULT '{}',
    relevance_score NUMERIC(4, 3),                   -- 0.000–1.000, LLM-assigned

    CONSTRAINT news_items_relevance_range  CHECK (relevance_score IS NULL OR relevance_score BETWEEN 0 AND 1),
    CONSTRAINT news_items_tokens_positive  CHECK (llm_tokens_in  IS NULL OR llm_tokens_in  >= 0),
    CONSTRAINT news_items_tokens_positive2 CHECK (llm_tokens_out IS NULL OR llm_tokens_out >= 0),
    CONSTRAINT news_items_cost_positive    CHECK (llm_cost_usd   IS NULL OR llm_cost_usd   >= 0)
);

COMMENT ON TABLE  news_items             IS 'Scraped news articles and press items. Deduplicated via url_hash.';
COMMENT ON COLUMN news_items.url_hash    IS 'SHA-256 hex of url. UNIQUE constraint is the sole dedup mechanism.';
COMMENT ON COLUMN news_items.source      IS 'Scraper source identifier, e.g. tekstil_magazin, fibre2fashion.';
COMMENT ON COLUMN news_items.body_raw    IS 'Raw scraped text before any LLM processing.';
COMMENT ON COLUMN news_items.body_summary IS 'LLM-generated summary of body_raw.';

CREATE INDEX news_items_source_idx       ON news_items (source);
CREATE INDEX news_items_published_at_idx ON news_items (published_at DESC NULLS LAST);
CREATE INDEX news_items_scraped_at_idx   ON news_items (scraped_at   DESC);
CREATE INDEX news_items_company_id_idx   ON news_items (company_id);
CREATE INDEX news_items_language_idx     ON news_items (language);
CREATE INDEX news_items_tags_idx         ON news_items USING GIN (tags);
CREATE INDEX news_items_relevance_idx    ON news_items (relevance_score DESC NULLS LAST)
    WHERE relevance_score IS NOT NULL;

-- =============================================================================
-- TABLE: trade_flows
-- Import/export trade statistics from external data sources.
-- Deduplication: url_hash UNIQUE when url is present.
-- =============================================================================
CREATE TABLE trade_flows (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source identification
    url              TEXT,
    url_hash         TEXT        UNIQUE
                                 GENERATED ALWAYS AS (
                                     CASE WHEN url IS NOT NULL
                                     THEN encode(digest(url, 'sha256'), 'hex')
                                     END
                                 ) STORED,
    source           TEXT        NOT NULL,           -- e.g. 'tuik', 'trademap', 'zauba'

    -- Trade dimensions
    reporter_country CHAR(2)     NOT NULL,           -- ISO 3166-1 alpha-2
    partner_country  CHAR(2),                        -- NULL = world aggregate
    hs_code          TEXT        NOT NULL,           -- HS chapter or heading, e.g. '5208', '6006'
    flow_direction   trade_flow_direction NOT NULL,

    -- Period
    period           DATE        NOT NULL,           -- first day of the reported period
    period_type      period_granularity NOT NULL,

    -- Values
    value_usd        NUMERIC(18, 2),
    quantity_kg      NUMERIC(18, 3),

    -- Metadata
    scraped_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes            TEXT,

    -- LLM cost tracking (for sources requiring LLM extraction)
    llm_model        TEXT,
    llm_tokens_in    INT,
    llm_tokens_out   INT,
    llm_cost_usd     NUMERIC(10, 6),

    CONSTRAINT trade_flows_value_positive    CHECK (value_usd    IS NULL OR value_usd    >= 0),
    CONSTRAINT trade_flows_quantity_positive CHECK (quantity_kg  IS NULL OR quantity_kg  >= 0),
    CONSTRAINT trade_flows_cost_positive     CHECK (llm_cost_usd IS NULL OR llm_cost_usd >= 0),
    -- Prevent duplicate data rows for sources without URLs
    CONSTRAINT trade_flows_natural_unique UNIQUE NULLS NOT DISTINCT
        (source, reporter_country, partner_country, hs_code, flow_direction, period, period_type)
);

COMMENT ON TABLE  trade_flows                IS 'Import/export trade statistics from external data sources.';
COMMENT ON COLUMN trade_flows.reporter_country IS 'The country reporting the trade flow. ISO 3166-1 alpha-2.';
COMMENT ON COLUMN trade_flows.partner_country  IS 'Counterpart country. NULL means world aggregate.';
COMMENT ON COLUMN trade_flows.hs_code          IS 'Harmonized System chapter or heading, e.g. 5208 for woven cotton.';
COMMENT ON COLUMN trade_flows.period           IS 'First day of the reported period (month/quarter/year).';

CREATE INDEX trade_flows_hs_code_idx      ON trade_flows (hs_code);
CREATE INDEX trade_flows_period_idx       ON trade_flows (period DESC);
CREATE INDEX trade_flows_reporter_idx     ON trade_flows (reporter_country);
CREATE INDEX trade_flows_partner_idx      ON trade_flows (partner_country);
CREATE INDEX trade_flows_source_idx       ON trade_flows (source);
CREATE INDEX trade_flows_flow_idx         ON trade_flows (flow_direction);

-- =============================================================================
-- TABLE: market_signals
-- Processed intelligence signals derived from news_items or trade_flows
-- after LLM analysis. Drives Telegram/email notifications.
-- =============================================================================
CREATE TABLE market_signals (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Signal classification
    signal_type     TEXT            NOT NULL,        -- e.g. 'price_move', 'capacity_change', 'new_entrant'
    severity        signal_severity NOT NULL DEFAULT 'info',

    -- Content
    title           TEXT            NOT NULL,
    body            TEXT,

    -- Source traceability (polymorphic reference)
    source_table    TEXT,                            -- 'news_items' | 'trade_flows'
    source_id       UUID,                            -- row id in source_table

    -- Relations
    company_id      UUID            REFERENCES companies(id) ON DELETE SET NULL,

    -- Timestamps
    detected_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    notified_at     TIMESTAMPTZ,                     -- set when Telegram/email notification sent

    -- LLM cost tracking
    llm_model       TEXT,
    llm_tokens_in   INT,
    llm_tokens_out  INT,
    llm_cost_usd    NUMERIC(10, 6),

    -- Tags
    tags            TEXT[]          NOT NULL DEFAULT '{}',

    CONSTRAINT market_signals_source_table_values
        CHECK (source_table IS NULL OR source_table IN ('news_items', 'trade_flows')),
    CONSTRAINT market_signals_cost_positive
        CHECK (llm_cost_usd IS NULL OR llm_cost_usd >= 0)
);

COMMENT ON TABLE  market_signals             IS 'Processed intelligence signals. Drives Telegram/email notifications.';
COMMENT ON COLUMN market_signals.signal_type IS 'Signal category: price_move, capacity_change, new_entrant, tariff, etc.';
COMMENT ON COLUMN market_signals.source_table IS 'The table the signal was derived from: news_items or trade_flows.';
COMMENT ON COLUMN market_signals.source_id    IS 'UUID of the row in source_table (by convention, no FK constraint).';
COMMENT ON COLUMN market_signals.notified_at  IS 'NULL until Telegram/email notification is sent.';

CREATE INDEX market_signals_type_idx      ON market_signals (signal_type);
CREATE INDEX market_signals_severity_idx  ON market_signals (severity);
CREATE INDEX market_signals_detected_idx  ON market_signals (detected_at DESC);
CREATE INDEX market_signals_company_idx   ON market_signals (company_id);
CREATE INDEX market_signals_tags_idx      ON market_signals USING GIN (tags);
-- Partial index for the notification dispatch queue
CREATE INDEX market_signals_pending_notify_idx ON market_signals (detected_at)
    WHERE notified_at IS NULL;

-- =============================================================================
-- TABLE: failed_jobs
-- Dead-letter queue for all pipeline errors.
-- Records are NEVER auto-deleted; resolved_at marks manual review/replay.
-- =============================================================================
CREATE TABLE failed_jobs (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Job identification
    pipeline        TEXT        NOT NULL,            -- e.g. 'tekstil_magazin_scraper'
    job_type        TEXT        NOT NULL,            -- e.g. 'scrape', 'llm_summarise', 'db_insert'
    url             TEXT,                            -- if the job was URL-based

    -- Failure details
    error_message   TEXT        NOT NULL,
    error_detail    TEXT,                            -- full stack trace or raw API response
    http_status     INT,                             -- HTTP status code if applicable

    -- Payload for replay
    payload         JSONB,                           -- original job input, sufficient to retry

    -- Timestamps & retry tracking
    failed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retry_count     INT         NOT NULL DEFAULT 0,
    last_retried_at TIMESTAMPTZ,

    -- Resolution
    resolved_at     TIMESTAMPTZ,                     -- set when reviewed or successfully replayed
    resolved_by     TEXT,                            -- operator name or 'auto_replay'
    resolution_note TEXT,

    CONSTRAINT failed_jobs_retry_count_positive CHECK (retry_count >= 0),
    CONSTRAINT failed_jobs_http_status_range    CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599)
);

COMMENT ON TABLE  failed_jobs              IS 'Dead-letter queue for all pipeline errors. Never auto-deleted.';
COMMENT ON COLUMN failed_jobs.pipeline     IS 'Pipeline/scraper name that produced the error.';
COMMENT ON COLUMN failed_jobs.job_type     IS 'Stage that failed: scrape, llm_summarise, db_insert, etc.';
COMMENT ON COLUMN failed_jobs.payload      IS 'Original job input as JSONB, sufficient to replay the job.';
COMMENT ON COLUMN failed_jobs.resolved_at  IS 'NULL = unresolved. Set after manual review or successful replay.';

CREATE INDEX failed_jobs_pipeline_idx     ON failed_jobs (pipeline);
CREATE INDEX failed_jobs_failed_at_idx    ON failed_jobs (failed_at DESC);
-- Partial index for the unresolved queue (most common query)
CREATE INDEX failed_jobs_unresolved_idx   ON failed_jobs (failed_at DESC)
    WHERE resolved_at IS NULL;
CREATE INDEX failed_jobs_payload_idx      ON failed_jobs USING GIN (payload);

-- =============================================================================
-- TABLE: competitor_snapshots
-- Stores a SHA-256 hash of each competitor homepage fetch.
-- A hash change since the last check triggers a market_signals row.
-- First-time checks store the snapshot only (no signal).
-- =============================================================================
CREATE TABLE competitor_snapshots (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID        NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    url             TEXT        NOT NULL,
    content_hash    TEXT        NOT NULL,   -- SHA-256 hex of normalised page text
    content_summary TEXT,                   -- extracted keywords/sentences
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT competitor_snapshots_hash_len CHECK (length(content_hash) = 64)
);

COMMENT ON TABLE  competitor_snapshots              IS 'Homepage content snapshots for change detection.';
COMMENT ON COLUMN competitor_snapshots.content_hash IS 'SHA-256 hex of normalised page text. Change triggers market_signals.';
COMMENT ON COLUMN competitor_snapshots.content_summary IS 'Sentences/fragments containing monitored keywords.';

-- Latest snapshot per company (most common query)
CREATE INDEX competitor_snapshots_company_checked_idx
    ON competitor_snapshots (company_id, checked_at DESC);

-- =============================================================================
-- VIEW: llm_cost_summary
-- Per-table, per-model cost rollup for monitoring token spend.
-- =============================================================================
CREATE VIEW llm_cost_summary AS
    SELECT 'news_items'    AS source_table,
           llm_model,
           COUNT(*)        AS row_count,
           SUM(llm_tokens_in)  AS total_tokens_in,
           SUM(llm_tokens_out) AS total_tokens_out,
           SUM(llm_cost_usd)   AS total_cost_usd
    FROM news_items
    WHERE llm_model IS NOT NULL
    GROUP BY llm_model
UNION ALL
    SELECT 'trade_flows',
           llm_model,
           COUNT(*),
           SUM(llm_tokens_in),
           SUM(llm_tokens_out),
           SUM(llm_cost_usd)
    FROM trade_flows
    WHERE llm_model IS NOT NULL
    GROUP BY llm_model
UNION ALL
    SELECT 'market_signals',
           llm_model,
           COUNT(*),
           SUM(llm_tokens_in),
           SUM(llm_tokens_out),
           SUM(llm_cost_usd)
    FROM market_signals
    WHERE llm_model IS NOT NULL
    GROUP BY llm_model;

COMMENT ON VIEW llm_cost_summary IS 'Per-table, per-model LLM token and cost rollup.';

-- ---------------------------------------------------------------------------
-- lescon_sales — internal Lescon account-statement sales data
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lescon_sales (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    evrak_no        TEXT        NOT NULL,
    tarih           DATE,
    urun_aciklamasi TEXT,
    unit_price_usd  NUMERIC(10,2),
    miktar          NUMERIC(12,3),
    miktar_unit     TEXT,
    fabric_type     TEXT,
    fabric_subtype  TEXT,
    is_return       BOOLEAN     DEFAULT FALSE,
    source_file     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS lescon_sales_tarih_idx   ON lescon_sales (tarih);
CREATE INDEX IF NOT EXISTS lescon_sales_fabric_idx  ON lescon_sales (fabric_type);

-- ---------------------------------------------------------------------------
-- price_signals — scraped fiber/yarn/commodity price data
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS price_signals (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    material   TEXT        NOT NULL,          -- e.g. 'cotton', 'coarse_wool'
    price_usd  NUMERIC(14,4),                 -- price in source unit (see unit col)
    unit       TEXT        NOT NULL,          -- e.g. 'USD/kg', 'USc/kg'
    source     TEXT        NOT NULL,          -- e.g. 'indexmundi'
    period     DATE        NOT NULL,          -- first day of the price month
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (material, source, period)
);

CREATE INDEX IF NOT EXISTS price_signals_period_idx   ON price_signals (period);
CREATE INDEX IF NOT EXISTS price_signals_material_idx ON price_signals (material);

-- ---------------------------------------------------------------------------
-- fair_exhibitors — exhibitor directory from trade fairs (Texhibition etc.)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fair_exhibitors (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    fair_name       TEXT        NOT NULL,          -- e.g. 'Texhibition Istanbul'
    fair_year       INTEGER     NOT NULL,
    name            TEXT        NOT NULL,          -- brand/display name
    full_name       TEXT,                          -- full legal company name
    slug            TEXT        NOT NULL,          -- URL slug from fair website
    country         TEXT        NOT NULL DEFAULT 'TR',
    categories      TEXT[]      NOT NULL DEFAULT '{}',
    booth           TEXT,
    website         TEXT,
    certificates    TEXT[]      NOT NULL DEFAULT '{}',
    export_markets  TEXT,
    detail_url      TEXT,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (fair_name, fair_year, slug)
);

CREATE INDEX IF NOT EXISTS fair_exhibitors_fair_idx
    ON fair_exhibitors (fair_name, fair_year);
CREATE INDEX IF NOT EXISTS fair_exhibitors_name_idx
    ON fair_exhibitors USING GIN (to_tsvector('simple', name));

COMMIT;
