-- =============================================================================
-- Migration 025 — v_cost_movers
-- =============================================================================
-- M2.4.4 Cost Structure Phase 1 — Movers strip data source.
--
-- Returns up to 3 rows, one per slot, ordered by display_order:
--   1 = biggest_increase  : largest +% bucket, latest complete month vs prior
--   2 = biggest_decrease  : largest -% bucket
--   3 = highest_volatility: highest CV (stdev/mean) over last 12 months
--
-- Thresholds:
--   - increase / decrease: |pct_change| >= 5%, otherwise NULL row (frontend
--     renders "no significant change")
--   - volatility:          CV >= 0.20 to qualify
--
-- Cost scope: 6 cost buckets (same as v_monthly_cost_structure).
-- Window: 12 months for volatility. Latest complete + prior complete month
--         for movers (incomplete trailing month excluded).
-- =============================================================================

DROP VIEW IF EXISTS v_cost_movers CASCADE;

CREATE VIEW v_cost_movers AS
WITH
purchase_bounds AS (
    SELECT
        MAX(fatura_tarihi) AS max_date,
        DATE_TRUNC('month', MAX(fatura_tarihi))::date                       AS current_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '1 month')::date  AS latest_complete_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '2 months')::date AS prior_complete_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '12 months')::date AS volatility_window_start
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

cost_buckets(b) AS (
    VALUES
      ('utilities'),
      ('maintenance_factory'),
      ('packaging'),
      ('factory_overhead'),
      ('outsourced_processing'),
      ('logistics_distribution')
),

-- Latest complete month per bucket
mover_data AS (
    SELECT
        business_bucket,
        SUM(net_tutar_y) FILTER (
            WHERE fatura_tarihi >= (SELECT latest_complete_month_start FROM purchase_bounds)
              AND fatura_tarihi <  (SELECT current_month_start FROM purchase_bounds)
        )::numeric AS latest_tl,
        SUM(net_tutar_y) FILTER (
            WHERE fatura_tarihi >= (SELECT prior_complete_month_start FROM purchase_bounds)
              AND fatura_tarihi <  (SELECT latest_complete_month_start FROM purchase_bounds)
        )::numeric AS prior_tl
    FROM fact_purchase_lines_clean
    WHERE business_bucket IN (SELECT b FROM cost_buckets)
    GROUP BY business_bucket
),
mover_pct AS (
    SELECT
        business_bucket,
        latest_tl, prior_tl,
        CASE
            WHEN prior_tl IS NULL OR prior_tl = 0 THEN NULL
            ELSE 100.0 * (latest_tl - prior_tl) / prior_tl
        END AS pct_change
    FROM mover_data
    WHERE prior_tl IS NOT NULL AND prior_tl > 0
),

biggest_increase AS (
    SELECT
        1 AS display_order,
        'biggest_increase' AS slot,
        business_bucket    AS bucket,
        ROUND(pct_change::numeric, 1) AS pct_change,
        (latest_tl - prior_tl)::numeric(20, 2) AS abs_change_tl,
        latest_tl::numeric(20, 2) AS latest_tl,
        prior_tl::numeric(20, 2)  AS prior_tl,
        NULL::numeric AS cv,
        NULL::numeric AS stdev_tl,
        NULL::numeric AS mean_tl
    FROM mover_pct
    WHERE pct_change IS NOT NULL AND pct_change >= 5
    ORDER BY pct_change DESC
    LIMIT 1
),

biggest_decrease AS (
    SELECT
        2 AS display_order,
        'biggest_decrease' AS slot,
        business_bucket    AS bucket,
        ROUND(pct_change::numeric, 1) AS pct_change,
        (latest_tl - prior_tl)::numeric(20, 2) AS abs_change_tl,
        latest_tl::numeric(20, 2) AS latest_tl,
        prior_tl::numeric(20, 2)  AS prior_tl,
        NULL::numeric AS cv,
        NULL::numeric AS stdev_tl,
        NULL::numeric AS mean_tl
    FROM mover_pct
    WHERE pct_change IS NOT NULL AND pct_change <= -5
    ORDER BY pct_change ASC
    LIMIT 1
),

-- Volatility: 12 monthly buckets per bucket-key, CV = stdev / mean
monthly_per_bucket AS (
    SELECT
        DATE_TRUNC('month', fatura_tarihi)::date AS month,
        business_bucket,
        SUM(net_tutar_y)::numeric AS amount_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN purchase_bounds pb
    WHERE p.business_bucket IN (SELECT b FROM cost_buckets)
      AND p.fatura_tarihi >= pb.volatility_window_start
      AND p.fatura_tarihi <  pb.current_month_start
    GROUP BY 1, 2
),
volatility_per_bucket AS (
    SELECT
        business_bucket,
        AVG(amount_tl)        AS mean_tl,
        STDDEV(amount_tl)     AS stdev_tl,
        CASE
            WHEN AVG(amount_tl) IS NULL OR AVG(amount_tl) = 0 THEN NULL
            ELSE STDDEV(amount_tl) / AVG(amount_tl)
        END                   AS cv,
        COUNT(*)              AS month_count
    FROM monthly_per_bucket
    GROUP BY business_bucket
    HAVING COUNT(*) >= 6  -- need at least 6 monthly observations
),

highest_volatility AS (
    SELECT
        3 AS display_order,
        'highest_volatility' AS slot,
        business_bucket      AS bucket,
        NULL::numeric        AS pct_change,
        NULL::numeric        AS abs_change_tl,
        NULL::numeric        AS latest_tl,
        NULL::numeric        AS prior_tl,
        ROUND(cv::numeric, 2)       AS cv,
        ROUND(stdev_tl::numeric, 2) AS stdev_tl,
        ROUND(mean_tl::numeric, 2)  AS mean_tl
    FROM volatility_per_bucket
    WHERE cv IS NOT NULL AND cv >= 0.20
    ORDER BY cv DESC
    LIMIT 1
)

SELECT * FROM biggest_increase
UNION ALL
SELECT * FROM biggest_decrease
UNION ALL
SELECT * FROM highest_volatility
ORDER BY display_order;


COMMENT ON VIEW v_cost_movers IS
'M2.4.4 — Cost Structure Phase 1 movers strip. Up to 3 rows: biggest_increase
(latest complete month vs prior, |Δ|>=5%), biggest_decrease (same, <=-5%),
highest_volatility (CV=stdev/mean over last 12m, CV>=0.20). Slots return
no row when threshold not met (frontend shows "no significant change").';
