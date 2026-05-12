-- migrations/017_drop_overengineered_tender_columns.sql
-- Phase F1 cleanup (per ChatGPT critique synthesis):
-- Drop columns that represent "fake intelligence" -- not populated, no labeled
-- data, no feedback loop. They created false impressions of system capability.
-- Reintroduce later (Phase G/F3) only when LLM enrichment ships with validated
-- review data and a real classification taxonomy.
--
-- Note: v_active_tenders depends on these columns and must be recreated.

BEGIN;

DROP VIEW IF EXISTS v_active_tenders;

ALTER TABLE tenders
    DROP COLUMN IF EXISTS fit_technical_textile,
    DROP COLUMN IF EXISTS fit_protective_clothing,
    DROP COLUMN IF EXISTS fit_military,
    DROP COLUMN IF EXISTS fit_waterproof,
    DROP COLUMN IF EXISTS fit_fr,
    DROP COLUMN IF EXISTS estimated_competition,
    DROP COLUMN IF EXISTS likely_buyer_type;

-- Recreate v_active_tenders WITHOUT the dropped columns.
-- This view surfaces tenders that are still open and have a future deadline,
-- with the core relevance fields. fit_*/estimated_*/likely_* fields are gone.
CREATE VIEW v_active_tenders AS
SELECT
    id,
    source,
    ekap_id,
    source_url,
    title,
    description,
    institution,
    procurement_type,
    tender_status,
    published_at,
    deadline_at,
    relevance_level,
    relevance_score,
    matched_keywords,
    rejection_reason,
    created_at,
    updated_at,
    status_last_checked_at
FROM tenders
WHERE tender_status = 'open'
  AND (deadline_at IS NULL OR deadline_at > NOW())
  AND relevance_level IN ('HIGH', 'MEDIUM', 'LOW');

COMMIT;
