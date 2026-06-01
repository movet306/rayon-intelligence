-- migrations/034_mv_export_country_metrics.sql
-- Phase X2 Step 2.4a: Country-level export metrics MV
--
-- Granularity: 1 row per (hs_code, period, partner_country).
-- For 10 HS x 13 months x ~55 avg countries = ~7,000 rows.
--
-- Powers /api/exports/drilldown endpoint for X2.4 Country Drilldown panel.
-- Computes country-level value, share within HS-period, implied $/kg, rank,
-- 3-month rolling smoothing, and YoY % vs same month prior year.
--
-- Filtering: same as mv_export_partner_concentration (export-only, exclude
-- WORLD/aggregate codes, positive value_usd, mapped HS only).

DROP MATERIALIZED VIEW IF EXISTS mv_export_country_metrics CASCADE;

CREATE MATERIALIZED VIEW mv_export_country_metrics AS
WITH base AS (
    SELECT
        tf.hs_code,
        tf.period,
        tf.partner_country,
        SUM(tf.value_usd) AS country_value_usd,
        SUM(tf.quantity_kg) AS country_quantity_kg
    FROM trade_flows tf
    INNER JOIN dim_hs_rayon_mapping m USING (hs_code)
    WHERE tf.flow_direction = 'export'
      AND tf.partner_country IS NOT NULL
      AND tf.partner_country NOT IN ('W00', 'WLD', 'World', 'ZZZ', '_X')
      AND tf.value_usd IS NOT NULL
      AND tf.value_usd > 0
    GROUP BY tf.hs_code, tf.period, tf.partner_country
),
with_window AS (
    SELECT
        b.*,
        SUM(country_value_usd) OVER (PARTITION BY hs_code, period) AS hs_period_total_usd,
        country_value_usd / NULLIF(SUM(country_value_usd) OVER (PARTITION BY hs_code, period), 0) * 100
            AS country_share_pct,
        country_value_usd / NULLIF(country_quantity_kg, 0) AS country_implied_usd_per_kg,
        RANK() OVER (PARTITION BY hs_code, period ORDER BY country_value_usd DESC NULLS LAST)
            AS country_rank,
        AVG(country_value_usd) OVER (
            PARTITION BY hs_code, partner_country
            ORDER BY period
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS country_3m_rolling_usd,
        LAG(country_value_usd, 12) OVER (
            PARTITION BY hs_code, partner_country
            ORDER BY period
        ) AS country_yoy_baseline_usd
    FROM base b
)
SELECT
    hs_code,
    period,
    partner_country,
    ROUND(country_value_usd::numeric, 2) AS country_value_usd,
    ROUND(country_quantity_kg::numeric, 2) AS country_quantity_kg,
    ROUND(hs_period_total_usd::numeric, 2) AS hs_period_total_usd,
    ROUND(country_share_pct::numeric, 2) AS country_share_pct,
    ROUND(country_implied_usd_per_kg::numeric, 4) AS country_implied_usd_per_kg,
    country_rank,
    ROUND(country_3m_rolling_usd::numeric, 2) AS country_3m_rolling_usd,
    CASE
        WHEN country_yoy_baseline_usd > 0
        THEN ROUND(((country_value_usd - country_yoy_baseline_usd) / country_yoy_baseline_usd * 100)::numeric, 2)
        ELSE NULL
    END AS country_yoy_pct
FROM with_window;

-- UNIQUE index for CONCURRENTLY refresh
CREATE UNIQUE INDEX idx_mv_country_pk
    ON mv_export_country_metrics (hs_code, period, partner_country);

CREATE INDEX idx_mv_country_hs_country
    ON mv_export_country_metrics (hs_code, partner_country, period DESC);

CREATE INDEX idx_mv_country_period
    ON mv_export_country_metrics (period DESC);