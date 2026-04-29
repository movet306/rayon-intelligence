-- =============================================================================
-- Migration 021 — v_customer_concentration_trend
-- =============================================================================
-- M2.3.3 Revenue Phase 1 — mirror of Migration 017 for the customer side.
--
-- For each month in the trailing 24-month window, computes:
--   - top_1_share_pct  : largest customer's share of that month's core revenue
--   - top_3_share_pct  : sum of top 3 customers' share
--   - top_10_share_pct : sum of top 10 customers' share
--   - total_tl         : month total (core revenue, yarn_resale excluded)
--   - active_customers : distinct customer count this month
--
-- Window: 24 months rolling (matches the absolute revenue chart).
-- Scope: core_product_sales + outsourced_service_revenue (yarn_resale excluded).
-- =============================================================================

DROP VIEW IF EXISTS v_customer_concentration_trend CASCADE;

CREATE VIEW v_customer_concentration_trend AS
WITH
window_bounds AS (
    SELECT
        MAX(fatura_tarihi) AS max_date,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '23 months')::date AS min_month
    FROM fact_sales_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

monthly_customer AS (
    SELECT
        DATE_TRUNC('month', s.fatura_tarihi)::date AS month,
        s.cari_hesap_aciklamasi                    AS customer_name,
        SUM(s.net_tutar_y)::numeric                AS customer_amount_tl
    FROM fact_sales_lines_clean s
    CROSS JOIN window_bounds wb
    WHERE s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
      AND COALESCE(s.subtype, '') <> 'yarn_resale'
      AND s.cari_hesap_aciklamasi IS NOT NULL
      AND s.cari_hesap_aciklamasi <> ''
      AND s.fatura_tarihi >= wb.min_month
    GROUP BY DATE_TRUNC('month', s.fatura_tarihi)::date, s.cari_hesap_aciklamasi
),

ranked AS (
    SELECT
        month,
        customer_name,
        customer_amount_tl,
        ROW_NUMBER() OVER (PARTITION BY month ORDER BY customer_amount_tl DESC NULLS LAST) AS rk,
        SUM(customer_amount_tl) OVER (PARTITION BY month) AS month_total
    FROM monthly_customer
),

agg AS (
    SELECT
        month,
        SUM(customer_amount_tl) FILTER (WHERE rk <= 1)  AS top_1_amount_tl,
        SUM(customer_amount_tl) FILTER (WHERE rk <= 3)  AS top_3_amount_tl,
        SUM(customer_amount_tl) FILTER (WHERE rk <= 10) AS top_10_amount_tl,
        MAX(month_total)                                 AS total_tl,
        COUNT(DISTINCT customer_name)                    AS active_customers
    FROM ranked
    GROUP BY month
)

SELECT
    to_char(month, 'YYYY-MM') AS month,
    ROUND(100.0 * COALESCE(top_1_amount_tl, 0)  / NULLIF(total_tl, 0), 2) AS top_1_share_pct,
    ROUND(100.0 * COALESCE(top_3_amount_tl, 0)  / NULLIF(total_tl, 0), 2) AS top_3_share_pct,
    ROUND(100.0 * COALESCE(top_10_amount_tl, 0) / NULLIF(total_tl, 0), 2) AS top_10_share_pct,
    total_tl::numeric(20,2) AS total_tl,
    active_customers
FROM agg
ORDER BY month;


COMMENT ON VIEW v_customer_concentration_trend IS
'M2.3.3 — Revenue Phase 1: monthly top-1/top-3/top-10 customer share, 24m
rolling window, core_product_sales + outsourced_service_revenue scope
(yarn_resale excluded). Mirror of v_procurement_concentration_trend.';
