-- ============================================================================
-- Migration 011 v2 — Contra Revenue Anomaly View
-- ============================================================================
-- v1 had a SQL bug: correlated subquery referenced ungrouped s.fatura_tarihi.
-- v2 fixes by pre-aggregating ALIŞ contra by month, then JOIN-ing to SATIŞ.
-- ============================================================================

BEGIN;

DROP VIEW IF EXISTS v_contra_anomaly_detail CASCADE;


CREATE VIEW v_contra_anomaly_detail AS

WITH bounds AS (
    SELECT
        DATE_TRUNC('month', MAX(fatura_tarihi))::date                          AS current_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '1 month')::date   AS latest_complete,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '25 months')::date AS history_start
    FROM fact_sales_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

-- Latest-complete-month: SATIŞ side
latest_satis AS (
    SELECT
        SUM(CASE WHEN s.business_bucket = 'sales_return_contra'
                 THEN s.net_tutar_y ELSE 0 END) AS satis_contra_tl,
        SUM(CASE WHEN s.business_bucket = 'sales_return_contra'
                  AND COALESCE(s.subtype, '') = 'contra_revenue_return'
                 THEN s.net_tutar_y ELSE 0 END) AS sat_returns_tl,
        SUM(CASE WHEN s.business_bucket = 'sales_return_contra'
                  AND COALESCE(s.subtype, '') = 'contra_revenue_discount'
                 THEN s.net_tutar_y ELSE 0 END) AS sat_discounts_tl,
        SUM(CASE WHEN s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
                  AND COALESCE(s.subtype, '') <> 'yarn_resale'
                 THEN s.net_tutar_y ELSE 0 END) AS gross_revenue_tl
    FROM fact_sales_lines_clean s
    CROSS JOIN bounds b
    WHERE s.fatura_tarihi >= b.latest_complete
      AND s.fatura_tarihi <  b.current_month_start
),

-- Latest-complete-month: ALIŞ side
latest_alis AS (
    SELECT
        SUM(p.net_tutar_y) AS alis_contra_tl,
        SUM(CASE WHEN COALESCE(p.subtype, '') = 'contra_revenue_return'
                 THEN p.net_tutar_y ELSE 0 END) AS alis_returns_tl,
        SUM(CASE WHEN COALESCE(p.subtype, '') = 'contra_revenue_discount'
                 THEN p.net_tutar_y ELSE 0 END) AS alis_discounts_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN bounds b
    WHERE p.business_bucket = 'sales_return_contra'
      AND p.fatura_tarihi >= b.latest_complete
      AND p.fatura_tarihi <  b.current_month_start
),

-- Top counterparty (latest month, ALIŞ + SATIŞ combined)
latest_top_party AS (
    SELECT party, source, total_tl,
           ROW_NUMBER() OVER (ORDER BY total_tl DESC) AS rn
    FROM (
        SELECT
            cari_hesap_aciklamasi AS party,
            'ALIŞ' AS source,
            SUM(net_tutar_y) AS total_tl
        FROM fact_purchase_lines_clean p
        CROSS JOIN bounds b
        WHERE p.business_bucket = 'sales_return_contra'
          AND p.fatura_tarihi >= b.latest_complete
          AND p.fatura_tarihi <  b.current_month_start
          AND cari_hesap_aciklamasi IS NOT NULL
          AND cari_hesap_aciklamasi <> ''
        GROUP BY 1
        UNION ALL
        SELECT
            cari_hesap_aciklamasi,
            'SATIŞ',
            SUM(net_tutar_y)
        FROM fact_sales_lines_clean s
        CROSS JOIN bounds b
        WHERE s.business_bucket = 'sales_return_contra'
          AND s.fatura_tarihi >= b.latest_complete
          AND s.fatura_tarihi <  b.current_month_start
          AND cari_hesap_aciklamasi IS NOT NULL
          AND cari_hesap_aciklamasi <> ''
        GROUP BY 1
    ) parties
),

-- 24-month historical: pre-aggregate each side by month, then combine
monthly_satis AS (
    SELECT
        DATE_TRUNC('month', s.fatura_tarihi)::date AS month,
        SUM(CASE WHEN s.business_bucket = 'sales_return_contra'
                 THEN s.net_tutar_y ELSE 0 END) AS satis_contra,
        SUM(CASE WHEN s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
                  AND COALESCE(s.subtype, '') <> 'yarn_resale'
                 THEN s.net_tutar_y ELSE 0 END) AS gross
    FROM fact_sales_lines_clean s
    CROSS JOIN bounds b
    WHERE s.fatura_tarihi >= b.history_start
      AND s.fatura_tarihi <  b.current_month_start
    GROUP BY 1
),
monthly_alis AS (
    SELECT
        DATE_TRUNC('month', p.fatura_tarihi)::date AS month,
        SUM(p.net_tutar_y) AS alis_contra
    FROM fact_purchase_lines_clean p
    CROSS JOIN bounds b
    WHERE p.business_bucket = 'sales_return_contra'
      AND p.fatura_tarihi >= b.history_start
      AND p.fatura_tarihi <  b.current_month_start
    GROUP BY 1
),
monthly_pct AS (
    SELECT
        ms.month,
        (ms.satis_contra + COALESCE(ma.alis_contra, 0))
            / NULLIF(ms.gross, 0) * 100 AS contra_pct
    FROM monthly_satis ms
    LEFT JOIN monthly_alis ma USING (month)
),

historical_stats AS (
    SELECT
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY contra_pct) AS median_pct,
        AVG(contra_pct)                                          AS mean_pct,
        MIN(contra_pct)                                          AS min_pct,
        MAX(contra_pct)                                          AS max_pct,
        COUNT(*)                                                 AS sample_months
    FROM monthly_pct
    WHERE contra_pct IS NOT NULL
)

SELECT
    -- Period reference
    (SELECT to_char(latest_complete, 'YYYY-MM') FROM bounds)              AS month_label,
    (SELECT latest_complete FROM bounds)                                   AS month_date,

    -- Total contra
    (COALESCE((SELECT satis_contra_tl FROM latest_satis), 0)
        + COALESCE((SELECT alis_contra_tl FROM latest_alis), 0)
    )::numeric(20, 2)                                                     AS total_contra_tl,

    -- Source split
    COALESCE((SELECT alis_contra_tl  FROM latest_alis),  0)::numeric(20, 2) AS alis_contra_tl,
    COALESCE((SELECT satis_contra_tl FROM latest_satis), 0)::numeric(20, 2) AS satis_contra_tl,

    -- Subtype split (combined ALIŞ + SATIŞ)
    (COALESCE((SELECT sat_returns_tl   FROM latest_satis), 0)
        + COALESCE((SELECT alis_returns_tl   FROM latest_alis),  0)
    )::numeric(20, 2)                                                      AS returns_tl,
    (COALESCE((SELECT sat_discounts_tl FROM latest_satis), 0)
        + COALESCE((SELECT alis_discounts_tl FROM latest_alis),  0)
    )::numeric(20, 2)                                                      AS discounts_tl,

    -- Gross revenue & contra% (current month)
    COALESCE((SELECT gross_revenue_tl FROM latest_satis), 0)::numeric(20, 2)
                                                                           AS gross_revenue_tl,
    CASE
        WHEN COALESCE((SELECT gross_revenue_tl FROM latest_satis), 0) > 0
        THEN ROUND(
            ((COALESCE((SELECT satis_contra_tl FROM latest_satis), 0)
              + COALESCE((SELECT alis_contra_tl FROM latest_alis), 0)
             ) / (SELECT gross_revenue_tl FROM latest_satis) * 100)::numeric, 2)
        ELSE NULL
    END                                                                    AS contra_pct_of_gross,

    -- Historical context
    ROUND((SELECT median_pct FROM historical_stats)::numeric, 2)           AS median_24m_pct,
    ROUND((SELECT mean_pct FROM historical_stats)::numeric, 2)             AS mean_24m_pct,
    ROUND((SELECT min_pct FROM historical_stats)::numeric, 2)              AS min_24m_pct,
    ROUND((SELECT max_pct FROM historical_stats)::numeric, 2)              AS max_24m_pct,
    (SELECT sample_months FROM historical_stats)::int                      AS history_sample_months,

    -- Anomaly ratio (current contra% vs median)
    CASE
        WHEN COALESCE((SELECT gross_revenue_tl FROM latest_satis), 0) > 0
         AND (SELECT median_pct FROM historical_stats) > 0
        THEN ROUND(
            (((COALESCE((SELECT satis_contra_tl FROM latest_satis), 0)
              + COALESCE((SELECT alis_contra_tl FROM latest_alis), 0)
             ) / (SELECT gross_revenue_tl FROM latest_satis) * 100)
             / (SELECT median_pct FROM historical_stats)
            )::numeric, 2)
        ELSE NULL
    END                                                                    AS ratio_to_median,

    -- Top contributing counterparty
    (SELECT party FROM latest_top_party WHERE rn = 1)                      AS top_counterparty_name,
    (SELECT source FROM latest_top_party WHERE rn = 1)                     AS top_counterparty_source,
    (SELECT total_tl FROM latest_top_party WHERE rn = 1)::numeric(20, 2)
                                                                           AS top_counterparty_tl,
    CASE
        WHEN (COALESCE((SELECT satis_contra_tl FROM latest_satis), 0)
              + COALESCE((SELECT alis_contra_tl FROM latest_alis), 0)) > 0
         AND (SELECT total_tl FROM latest_top_party WHERE rn = 1) IS NOT NULL
        THEN ROUND(
            ((SELECT total_tl FROM latest_top_party WHERE rn = 1)::numeric
             / (COALESCE((SELECT satis_contra_tl FROM latest_satis), 0)
                + COALESCE((SELECT alis_contra_tl FROM latest_alis), 0)
               ) * 100)::numeric, 1)
        ELSE NULL
    END                                                                    AS top_counterparty_pct,

    -- Severity flag (frontend → color/icon)
    CASE
        WHEN (SELECT median_pct FROM historical_stats) > 0
         AND COALESCE((SELECT gross_revenue_tl FROM latest_satis), 0) > 0
         AND ((COALESCE((SELECT satis_contra_tl FROM latest_satis), 0)
              + COALESCE((SELECT alis_contra_tl FROM latest_alis), 0)
             ) / (SELECT gross_revenue_tl FROM latest_satis) * 100)
             / (SELECT median_pct FROM historical_stats) >= 2.5
        THEN 'high'
        WHEN (SELECT median_pct FROM historical_stats) > 0
         AND COALESCE((SELECT gross_revenue_tl FROM latest_satis), 0) > 0
         AND ((COALESCE((SELECT satis_contra_tl FROM latest_satis), 0)
              + COALESCE((SELECT alis_contra_tl FROM latest_alis), 0)
             ) / (SELECT gross_revenue_tl FROM latest_satis) * 100)
             / (SELECT median_pct FROM historical_stats) >= 1.5
        THEN 'elevated'
        ELSE 'normal'
    END                                                                    AS severity;

COMMENT ON VIEW v_contra_anomaly_detail IS
    'Single-row alert card. v2 — fixed correlated-subquery bug, pre-aggregates monthly ALIŞ/SATIŞ separately then joins.';


COMMIT;

-- ============================================================================
-- End of migration 011 v2
-- ============================================================================
