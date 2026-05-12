-- migrations/019_create_v_tender_kpis.sql
-- Phase F1 (per ChatGPT critique): honest KPI view.
-- precision_estimate_pct is NULL until manual review data is collected.
-- Do NOT replace NULL with a rule-based approximation -- that would be
-- false confidence (the very thing the critique flagged).

BEGIN;

CREATE OR REPLACE VIEW v_tender_kpis AS
SELECT
    COUNT(*)                                                              AS total_tenders,
    COUNT(*) FILTER (WHERE tender_status = 'open')                        AS open_tender_count,
    COUNT(*) FILTER (WHERE relevance_level = 'HIGH')                      AS high_relevance_count,
    COUNT(*) FILTER (WHERE relevance_level = 'MEDIUM')                    AS medium_relevance_count,
    COUNT(*) FILTER (WHERE relevance_level = 'LOW')                       AS low_relevance_count,
    COUNT(*) FILTER (WHERE relevance_level = 'REJECTED')                  AS rejected_count,
    COUNT(*) FILTER (WHERE manual_reviewed_at IS NOT NULL)                AS manual_reviewed_count,
    COUNT(*) FILTER (WHERE manual_review_label = 'CONFIRMED_RELEVANT')    AS confirmed_relevant_count,
    COUNT(*) FILTER (WHERE manual_review_label = 'FALSE_POSITIVE')        AS false_positive_count,
    CASE
        WHEN COUNT(*) FILTER (
            WHERE manual_reviewed_at IS NOT NULL
              AND relevance_level IN ('HIGH','MEDIUM')
        ) = 0 THEN NULL
        ELSE ROUND(
            100.0 * COUNT(*) FILTER (
                WHERE manual_review_label = 'CONFIRMED_RELEVANT'
                  AND relevance_level IN ('HIGH','MEDIUM')
            )::NUMERIC
            / COUNT(*) FILTER (
                WHERE manual_reviewed_at IS NOT NULL
                  AND relevance_level IN ('HIGH','MEDIUM')
            ),
            1
        )
    END                                                                   AS precision_estimate_pct
FROM tenders
WHERE source = 'ekap_bulletin';

COMMENT ON VIEW v_tender_kpis IS
    'Phase F1 KPI view. precision_estimate_pct is NULL until manual_review_label is populated on HIGH/MEDIUM tenders. Do NOT replace NULL with an approximation.';

COMMIT;
