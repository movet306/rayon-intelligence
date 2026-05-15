-- migrations/033_mv_export_partner_concentration.sql
-- Phase X2 Step 2.2: Partner concentration metrics (HHI, CR3, CR5)
--
-- Creates materialized view computing per-HS-period concentration metrics
-- from partner-level trade_flows data. Filters out WORLD/aggregate partners
-- to avoid double-counting. Joined to dim_hs_rayon_mapping for mapped HS only.
--
-- Concentration interpretation (US DOJ guidelines):
--   HHI < 1500       : not concentrated (healthy diversification)
--   HHI 1500-2500    : moderately concentrated
--   HHI > 2500       : highly concentrated (dependency risk)
--
-- Granularity: 1 row per (hs_code, period). For 10 HS x 13 months = 130 rows.

DROP MATERIALIZED VIEW IF EXISTS mv_export_partner_concentration CASCADE;

CREATE MATERIALIZED VIEW mv_export_partner_concentration AS
WITH partner_shares AS (
    SELECT
        tf.hs_code,
        tf.period,
        tf.partner_country,
        tf.value_usd,
        SUM(tf.value_usd) OVER (PARTITION BY tf.hs_code, tf.period) AS total_period_usd,
        tf.value_usd / NULLIF(SUM(tf.value_usd) OVER (PARTITION BY tf.hs_code, tf.period), 0)
            AS partner_share,
        RANK() OVER (
            PARTITION BY tf.hs_code, tf.period
            ORDER BY tf.value_usd DESC NULLS LAST
        ) AS partner_rank
    FROM trade_flows tf
    INNER JOIN dim_hs_rayon_mapping m USING (hs_code)
    WHERE tf.flow_direction = 'export'
      AND tf.partner_country IS NOT NULL
      AND tf.partner_country NOT IN ('W00', 'WLD', 'World', 'ZZZ', '_X')
      AND tf.value_usd IS NOT NULL
      AND tf.value_usd > 0
)
SELECT
    hs_code,
    period,
    COUNT(*) AS active_partners,
    SUM(total_period_usd) / COUNT(*) AS total_value_usd,  -- same as window sum
    -- HHI: sum of (share * 100)^2, gives 0-10000 scale
    ROUND(SUM(POWER(partner_share * 100, 2))::numeric, 2) AS hhi,
    -- CR3 / CR5: cumulative share of top N partners as percentage
    ROUND((SUM(CASE WHEN partner_rank <= 3 THEN partner_share ELSE 0 END) * 100)::numeric, 2)
        AS cr3_pct,
    ROUND((SUM(CASE WHEN partner_rank <= 5 THEN partner_share ELSE 0 END) * 100)::numeric, 2)
        AS cr5_pct,
    -- Top partner identity + share
    MAX(CASE WHEN partner_rank = 1 THEN partner_country END) AS top_partner,
    ROUND((MAX(CASE WHEN partner_rank = 1 THEN partner_share END) * 100)::numeric, 2)
        AS top_partner_share_pct,
    -- Concentration category (US DOJ thresholds)
    CASE
        WHEN SUM(POWER(partner_share * 100, 2)) < 1500 THEN 'dispersed'
        WHEN SUM(POWER(partner_share * 100, 2)) < 2500 THEN 'moderate'
        ELSE 'concentrated'
    END AS concentration_category
FROM partner_shares
GROUP BY hs_code, period;

-- UNIQUE index for CONCURRENTLY refresh
CREATE UNIQUE INDEX idx_mv_concentration_pk
    ON mv_export_partner_concentration (hs_code, period);

CREATE INDEX idx_mv_concentration_period
    ON mv_export_partner_concentration (period DESC);

CREATE INDEX idx_mv_concentration_category
    ON mv_export_partner_concentration (concentration_category);

-- Verify
SELECT
    hs_code,
    period,
    active_partners,
    hhi,
    cr3_pct,
    top_partner,
    top_partner_share_pct,
    concentration_category
FROM mv_export_partner_concentration
WHERE period = (SELECT MAX(period) FROM mv_export_partner_concentration)
ORDER BY hhi DESC;