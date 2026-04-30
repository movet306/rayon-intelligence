-- =============================================================================
-- PI-1.1 — Active signals deduplication view
-- =============================================================================
-- Created:  2026-04-29
-- Purpose:  Reduce signal feed noise on the Price Intelligence sub-tab.
--
-- Problem:
--   price_intelligence_signals stores one row per (signal_pattern, signal_date).
--   Recurring conditions are recomputed daily, so a signal that's been active
--   for 9 days appears 9 times in the feed. Diagnostic (29 Apr 2026) showed
--   42 active rows but only 9 distinct patterns -> 78.6% duplicate burden.
--
-- Solution:
--   A view that returns ONE row per dedup key (the latest-dated, most-severe
--   instance of each unique signal pattern). Raw table is untouched.
--
-- Dedup key:
--   (signal_type, chain, material_slug, upstream_slug, downstream_slug)
--   NULL slugs are coalesced to '' so they participate in the key.
--
-- Tie-breaking (when multiple rows share the same dedup key):
--   1. signal_date DESC      -> most recent first
--   2. severity rank DESC    -> within the same date, prefer high > medium > low
--   3. created_at DESC       -> within all else equal, latest insert wins
--
-- Filters:
--   - suppressed = FALSE      (operator-level suppression honored)
--   - signal_date >= NOW() - INTERVAL '14 days'
--     (UI cares about recent signals; 14d gives buffer over the 7d feed window
--      so a Sunday-night cron miss doesn't blank the feed.)
--
-- Reversal:
--   DROP VIEW v_active_signals;
--   No data is lost. The endpoint can be reverted to read from the raw table.
-- =============================================================================

CREATE OR REPLACE VIEW v_active_signals AS
SELECT DISTINCT ON (
    signal_type,
    chain,
    COALESCE(material_slug,   ''),
    COALESCE(upstream_slug,   ''),
    COALESCE(downstream_slug, '')
)
    id,
    signal_date,
    signal_type,
    chain,
    material_slug,
    upstream_slug,
    downstream_slug,
    severity,
    time_horizon,
    confidence_tier,
    value_pct,
    explanation,
    business_implication,
    turkey_lag_min,
    turkey_lag_max,
    suppressed,
    created_at
FROM price_intelligence_signals
WHERE suppressed = FALSE
  AND signal_date >= NOW() - INTERVAL '14 days'
ORDER BY
    signal_type,
    chain,
    COALESCE(material_slug,   ''),
    COALESCE(upstream_slug,   ''),
    COALESCE(downstream_slug, ''),
    signal_date DESC,
    CASE severity
        WHEN 'critical' THEN 1
        WHEN 'high'     THEN 2
        WHEN 'medium'   THEN 3
        WHEN 'low'      THEN 4
        ELSE 5
    END,
    created_at DESC;

COMMENT ON VIEW v_active_signals IS
  'PI-1.1 dedup: latest, most-severe row per signal pattern. Source of truth '
  'for /api/price_intelligence_signals. Read-only. Raw price_intelligence_signals '
  'table is preserved unchanged.';
