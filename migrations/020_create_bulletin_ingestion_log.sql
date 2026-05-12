-- migrations/020_create_bulletin_ingestion_log.sql
-- Phase F1 Step 9b: Track every download/parse attempt for "Did we ingest today?" KPI.
-- Per ChatGPT critique: ingestion health is the single most important KPI right now.
-- Empty data > bad classification.

BEGIN;

CREATE TABLE IF NOT EXISTS bulletin_ingestion_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL DEFAULT 'ekap',
    bulletin_date DATE NOT NULL,
    procurement_type TEXT NOT NULL,
    file_path TEXT,
    file_size_bytes BIGINT,
    file_sha256 TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    tender_count INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_seconds NUMERIC,
    CONSTRAINT chk_bil_status CHECK (status IN (
        'downloaded', 'parsed', 'failed_download', 'failed_parse', 'skipped'
    )),
    CONSTRAINT chk_bil_type CHECK (procurement_type IN (
        'MAL','HIZMET','YAPIM','DANISMANLIK'
    )),
    CONSTRAINT uq_bil_source_date_type UNIQUE (source, bulletin_date, procurement_type)
);

CREATE INDEX IF NOT EXISTS idx_bil_date_desc ON bulletin_ingestion_log(bulletin_date DESC);
CREATE INDEX IF NOT EXISTS idx_bil_status ON bulletin_ingestion_log(status);

COMMENT ON TABLE bulletin_ingestion_log IS
    'Phase F1 Step 9b. Ingestion health log: every bulletin download + parse attempt.';

COMMIT;
