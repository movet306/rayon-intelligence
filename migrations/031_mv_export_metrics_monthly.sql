-- ============================================================================
-- Migration 031 - Phase X1 Step 3: mv_export_metrics_monthly
-- ============================================================================
-- Purpose:
--   Pre-compute monthly export metrics (HS x period granularity) so dashboard
--   queries don't re-aggregate trade_flows on every request. Embeds mapping
--   from dim_hs_rayon_mapping for direct rendering.
--
--   Granularity: hs_code x period (1st of month).
--   Partner detail dropped from this MV; partner-level drilldown is served
--   directly from trade_flows via a dedicated query in /api/exports.
--
--   Metrics computed:
--     - total_value_usd
--     - total_quantity_kg
--     - implied_usd_per_kg     (value / quantity)
--     - active_partners        (distinct partner_country count)
--     - rolling_3m_usd         (3-month rolling average of total_value_usd)
--     - yoy_baseline_usd       (12-month lag value)
--     - yoy_pct_change         ((current - baseline) / baseline * 100)
--
--   Filters applied to source:
--     - source         = 'comtrade'
--     - flow_direction = 'export'
--     - period_type    = 'monthly'
--     - partner_country IS NOT NULL    (excludes World aggregates, M49 code 0)
--
-- Data state at migration time (15 May 2026):
--   - 13 months coverage (Dec 2024 -> Dec 2025)
--   - 9 HS codes mapped (3 primary + 6 secondary)
--   - Expected rows: up to 9 * 13 = 117
--     (sparse hs/month combos with no exports are omitted)
--   - yoy_pct_change populated only for Dec 2025 (only month with full
--     12-month baseline in current data window)
--   - rolling_3m_usd: NULL for Dec 2024 (no preceding rows),
--                     partial avg for Jan 2025
--
-- Refresh strategy:
--   - Initial population: WITH DATA (CREATE MATERIALIZED VIEW default)
--   - Subsequent refreshes: REFRESH MATERIALIZED VIEW CONCURRENTLY
--                           mv_export_metrics_monthly
--     (zero-downtime, requires unique index defined below)
--   - Automation hook lands in Phase X1 Step 4 (scraper post-hook or
--     daily cron task).
--
-- Logical FK:
--   trade_flows.hs_code -> dim_hs_rayon_mapping.hs_code  (LEFT JOIN, not enforced)
--   trade_flows.* aggregated by hs_code + period         (source rows)
--
-- Scope:
--   DROP MATERIALIZED VIEW IF EXISTS              (idempotent)
--   CREATE MATERIALIZED VIEW ... WITH DATA
--   CREATE UNIQUE INDEX (hs_code, period)         (REQUIRED for CONCURRENTLY)
--   CREATE INDEX on period DESC, importance_tier, business_line
--
-- Idempotent: DROP ... IF EXISTS + CREATE = safe to re-run.
-- ============================================================================

DROP MATERIALIZED VIEW IF EXISTS mv_export_metrics_monthly;

CREATE MATERIALIZED VIEW mv_export_metrics_monthly AS
WITH base_monthly AS (
    -- Aggregate per HS x month, excluding World aggregates and non-export flows
    SELECT
        t.hs_code,
        t.period,
        SUM(t.value_usd)::numeric(18, 2)       AS total_value_usd,
        SUM(t.quantity_kg)::numeric(18, 3)     AS total_quantity_kg,
        COUNT(DISTINCT t.partner_country)::int AS active_partners
    FROM trade_flows t
    WHERE t.source           = 'comtrade'
      AND t.flow_direction   = 'export'
      AND t.period_type      = 'monthly'
      AND t.partner_country IS NOT NULL
    GROUP BY t.hs_code, t.period
)
SELECT
    bm.hs_code,
    bm.period,
    bm.total_value_usd,
    bm.total_quantity_kg,

    -- Implied $/kg (NULL when quantity is zero or null)
    CASE
      WHEN bm.total_quantity_kg > 0
      THEN (bm.total_value_usd / bm.total_quantity_kg)::numeric(10, 4)
      ELSE NULL
    END                                                  AS implied_usd_per_kg,

    bm.active_partners,

    -- 3-month rolling average (current + up to 2 preceding rows)
    AVG(bm.total_value_usd) OVER (
        PARTITION BY bm.hs_code
        ORDER BY bm.period
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    )::numeric(18, 2)                                    AS rolling_3m_usd,

    -- YoY baseline: same month 12 periods ago
    LAG(bm.total_value_usd, 12) OVER (
        PARTITION BY bm.hs_code
        ORDER BY bm.period
    )::numeric(18, 2)                                    AS yoy_baseline_usd,

    -- YoY % change: (current - baseline) / baseline * 100
    CASE
      WHEN LAG(bm.total_value_usd, 12) OVER (
             PARTITION BY bm.hs_code ORDER BY bm.period
           ) > 0
      THEN ROUND(
        ((bm.total_value_usd
          - LAG(bm.total_value_usd, 12) OVER (
              PARTITION BY bm.hs_code ORDER BY bm.period
            )
         ) * 100.0
         / LAG(bm.total_value_usd, 12) OVER (
              PARTITION BY bm.hs_code ORDER BY bm.period
           )
        )::numeric, 2
      )
      ELSE NULL
    END                                                  AS yoy_pct_change,

    -- Mapping enrichment (LEFT JOIN; unmapped HS codes still kept)
    m.business_line,
    m.material_family,
    m.importance_tier,
    m.relevance_note
FROM base_monthly bm
LEFT JOIN dim_hs_rayon_mapping m ON m.hs_code = bm.hs_code;

-- ---------------------------------------------------------------------------
-- Indexes
--
-- Unique (hs_code, period) is REQUIRED for REFRESH MATERIALIZED VIEW
-- CONCURRENTLY (zero-downtime refresh in production).
-- ---------------------------------------------------------------------------

CREATE UNIQUE INDEX mv_export_metrics_monthly_pkey
    ON mv_export_metrics_monthly (hs_code, period);

CREATE INDEX mv_export_metrics_monthly_period_idx
    ON mv_export_metrics_monthly (period DESC);

CREATE INDEX mv_export_metrics_monthly_tier_idx
    ON mv_export_metrics_monthly (importance_tier);

CREATE INDEX mv_export_metrics_monthly_business_line_idx
    ON mv_export_metrics_monthly (business_line);

-- ---------------------------------------------------------------------------
-- Post-migration verification (run manually after apply)
-- ---------------------------------------------------------------------------
-- Row count + period range:
--   SELECT COUNT(*), MIN(period), MAX(period) FROM mv_export_metrics_monthly;
--
-- YoY for Dec 2025 (only month with full 12-month baseline):
--   SELECT hs_code, total_value_usd, yoy_baseline_usd, yoy_pct_change
--   FROM mv_export_metrics_monthly
--   WHERE period = '2025-12-01'
--   ORDER BY hs_code;
--
-- 3M rolling smoothing (HS 5407 example):
--   SELECT period, total_value_usd, rolling_3m_usd
--   FROM mv_export_metrics_monthly
--   WHERE hs_code = '5407'
--   ORDER BY period;
--
-- Mapping completeness check (should return 0 rows):
--   SELECT hs_code FROM mv_export_metrics_monthly
--   WHERE business_line IS NULL;
--
-- Refresh syntax for future runs (after scraper):
--   REFRESH MATERIALIZED VIEW CONCURRENTLY mv_export_metrics_monthly;
-- ---------------------------------------------------------------------------
