-- =============================================================================
-- Migration 020b — v_revenue_kpis contra share fix
-- =============================================================================
-- Issue: Migration 020 used bucket names 'returns_revenue' and 'discounts_revenue'
--        which do not exist in fact_sales_lines_clean. The actual contra bucket
--        is 'sales_return_contra' (88 rows in last 12 months).
--
-- Diagnostic confirmed:
--   - All sales rows are positive amounts (no negative-amount contra entries)
--   - Contra is tracked as a separate bucket with positive amounts
--   - Real bucket name: sales_return_contra
--
-- Other KPIs (FX %98.84, top 3 share %30.04, etc.) are unchanged and correct.
-- =============================================================================

DROP VIEW IF EXISTS v_revenue_kpis CASCADE;

CREATE VIEW v_revenue_kpis AS
WITH
window_bounds AS (
    SELECT
        MAX(fatura_tarihi) AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '1 year')::date AS min_date,
        CASE
            WHEN MAX(fatura_tarihi) = (DATE_TRUNC('month', MAX(fatura_tarihi)) + INTERVAL '1 month - 1 day')::date
              THEN DATE_TRUNC('month', MAX(fatura_tarihi))::date
            ELSE (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '1 month')::date
        END AS latest_month_start,
        CASE
            WHEN MAX(fatura_tarihi) = (DATE_TRUNC('month', MAX(fatura_tarihi)) + INTERVAL '1 month - 1 day')::date
              THEN (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '1 month')::date
            ELSE (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '2 months')::date
        END AS prior_month_start
    FROM fact_sales_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

core_total_12m AS (
    SELECT SUM(s.net_tutar_y)::numeric AS grand_total
    FROM fact_sales_lines_clean s
    CROSS JOIN window_bounds wb
    WHERE s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
      AND COALESCE(s.subtype, '') <> 'yarn_resale'
      AND s.fatura_tarihi >= wb.min_date
),

customer_totals AS (
    SELECT
        s.cari_hesap_aciklamasi AS customer_name,
        SUM(s.net_tutar_y)::numeric AS customer_amount_tl
    FROM fact_sales_lines_clean s
    CROSS JOIN window_bounds wb
    WHERE s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
      AND COALESCE(s.subtype, '') <> 'yarn_resale'
      AND s.fatura_tarihi >= wb.min_date
      AND s.cari_hesap_aciklamasi IS NOT NULL
      AND s.cari_hesap_aciklamasi <> ''
    GROUP BY s.cari_hesap_aciklamasi
),

top_3_total AS (
    SELECT SUM(customer_amount_tl)::numeric AS top_3_amount_tl
    FROM (
        SELECT customer_amount_tl
        FROM customer_totals
        ORDER BY customer_amount_tl DESC NULLS LAST
        LIMIT 3
    ) t
),

fx_share AS (
    SELECT
        SUM(CASE WHEN s.para_birimi_d IN ('USD', 'EUR')
                 THEN s.net_tutar_y ELSE 0 END)::numeric AS fx_amount_tl,
        SUM(s.net_tutar_y)::numeric                       AS total_amount_tl
    FROM fact_sales_lines_clean s
    CROSS JOIN window_bounds wb
    WHERE s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
      AND COALESCE(s.subtype, '') <> 'yarn_resale'
      AND s.fatura_tarihi >= wb.min_date
),

customer_count AS (
    SELECT COUNT(*)::int AS n_customers
    FROM customer_totals
),

total_revenue_12m AS (
    SELECT SUM(s.net_tutar_y)::numeric AS total_amount_tl
    FROM fact_sales_lines_clean s
    CROSS JOIN window_bounds wb
    WHERE s.fatura_tarihi >= wb.min_date
),

-- M2.3.2 fix — actual contra bucket name is sales_return_contra.
-- Contra is tracked as a separate POSITIVE-amount bucket, not as
-- negative entries on the core_product_sales bucket.
contra_12m AS (
    SELECT
        SUM(CASE
              WHEN s.business_bucket = 'sales_return_contra'
              THEN s.net_tutar_y ELSE 0
            END)::numeric AS contra_amount_tl,
        -- Gross = core + contra. We compare contra against core+contra
        -- (the "as-billed gross" before the contra is netted out).
        SUM(CASE
              WHEN s.business_bucket IN (
                'core_product_sales', 'outsourced_service_revenue',
                'sales_return_contra'
              ) THEN s.net_tutar_y ELSE 0
            END)::numeric AS gross_billed_tl
    FROM fact_sales_lines_clean s
    CROSS JOIN window_bounds wb
    WHERE s.fatura_tarihi >= wb.min_date
),

-- ── Concentration shift ──
monthly_customer AS (
    SELECT
        DATE_TRUNC('month', s.fatura_tarihi)::date AS month,
        s.cari_hesap_aciklamasi                    AS customer_name,
        SUM(s.net_tutar_y)::numeric                AS amount_tl
    FROM fact_sales_lines_clean s
    CROSS JOIN window_bounds wb
    WHERE s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
      AND COALESCE(s.subtype, '') <> 'yarn_resale'
      AND s.cari_hesap_aciklamasi IS NOT NULL
      AND s.cari_hesap_aciklamasi <> ''
      AND s.fatura_tarihi >= wb.prior_month_start
    GROUP BY 1, 2
),
ranked_per_month AS (
    SELECT
        month, customer_name, amount_tl,
        ROW_NUMBER() OVER (PARTITION BY month ORDER BY amount_tl DESC NULLS LAST) AS rk,
        SUM(amount_tl) OVER (PARTITION BY month) AS month_total
    FROM monthly_customer
),
top_3_per_month AS (
    SELECT
        month,
        100.0 * SUM(amount_tl) FILTER (WHERE rk <= 3) / NULLIF(MAX(month_total), 0) AS top_3_share_pct
    FROM ranked_per_month
    GROUP BY month
),
shift AS (
    SELECT
        (SELECT top_3_share_pct FROM top_3_per_month
         WHERE month = (SELECT latest_month_start FROM window_bounds)) AS latest_top3_pct,
        (SELECT top_3_share_pct FROM top_3_per_month
         WHERE month = (SELECT prior_month_start FROM window_bounds))  AS prior_top3_pct
)

SELECT
    -- Anchor row
    ROUND(
        100.0 * (SELECT top_3_amount_tl FROM top_3_total)
              / NULLIF((SELECT grand_total FROM core_total_12m), 0),
        2
    ) AS top_3_customer_share_pct,
    ROUND(
        100.0 * (SELECT fx_amount_tl FROM fx_share)
              / NULLIF((SELECT total_amount_tl FROM fx_share), 0),
        2
    ) AS fx_invoiced_share_pct,
    (SELECT n_customers FROM customer_count) AS active_customer_count,

    -- Context row
    ROUND(
        100.0 * (SELECT grand_total FROM core_total_12m)
              / NULLIF((SELECT total_amount_tl FROM total_revenue_12m), 0),
        2
    ) AS core_revenue_share_pct,
    ROUND(
        100.0 * (SELECT contra_amount_tl FROM contra_12m)
              / NULLIF((SELECT gross_billed_tl FROM contra_12m), 0),
        2
    ) AS contra_share_pct,

    -- KPI 6 — Top 3 customer share Δ
    ROUND(
        ((SELECT latest_top3_pct FROM shift) - (SELECT prior_top3_pct FROM shift))::numeric,
        1
    ) AS top_3_share_delta_pp,
    ROUND((SELECT latest_top3_pct FROM shift)::numeric, 1) AS top_3_share_latest_pct,
    ROUND((SELECT prior_top3_pct  FROM shift)::numeric, 1) AS top_3_share_prior_pct,

    -- Window metadata
    (SELECT to_char(latest_month_start, 'YYYY-MM') FROM window_bounds) AS latest_month,
    (SELECT to_char(prior_month_start,  'YYYY-MM') FROM window_bounds) AS prior_month,
    (SELECT grand_total FROM core_total_12m)                          AS core_total_12m_tl
;


COMMENT ON VIEW v_revenue_kpis IS
'M2.3.2 (v020b) — Revenue Phase 1 KPI strip. Contra share now uses correct
bucket name (sales_return_contra) with as-billed gross as denominator.
KPI 6 = top-3 customer share Δ in percentage points (latest vs prior month).';
