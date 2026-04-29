-- =============================================================================
-- Migration 023 — v_cost_kpis
-- =============================================================================
-- M2.4.2 Cost Structure Phase 1 — KPI strip data source.
--
-- Returns 6 metrics over the 12-month rolling window:
--
--   ANCHOR (top row):
--     1. cost_share_of_revenue_pct   — total cost / core revenue (margin proxy)
--     2. outsourced_processing_share — fason / total cost
--     3. active_cost_supplier_count  — distinct suppliers in cost scope (12m)
--
--   CONTEXT (bottom row):
--     4. maintenance_share_pct       — maintenance / total cost (factory health)
--     5. avg_monthly_cost_tl         — total_12m / 12
--     6. cost_revenue_ratio_delta_pp — last 3 months avg vs prior 3 months avg
--          → percentage-point shift in cost/revenue ratio.
--          Positive = margin compressing, negative = margin expanding.
--
-- Cost scope: utilities, maintenance_factory, packaging, factory_overhead,
--             outsourced_processing, logistics_distribution
-- Revenue scope: core_product_sales + outsourced_service_revenue
--                (yarn_resale excluded — same as Revenue Reality section)
-- =============================================================================

DROP VIEW IF EXISTS v_cost_kpis CASCADE;

CREATE VIEW v_cost_kpis AS
WITH
purchase_bounds AS (
    SELECT
        MAX(fatura_tarihi) AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '12 months')::date AS min_date_12m,
        -- 3m windows for ratio trend
        DATE_TRUNC('month', MAX(fatura_tarihi))::date                       AS month_anchor,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '3 months')::date AS recent_3m_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '6 months')::date AS prior_3m_start
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

sales_bounds AS (
    SELECT
        MAX(fatura_tarihi) AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '12 months')::date AS min_date_12m
    FROM fact_sales_lines_clean
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

-- Total cost (12m)
cost_total_12m AS (
    SELECT SUM(p.net_tutar_y)::numeric AS total_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN purchase_bounds pb
    WHERE p.business_bucket IN (SELECT b FROM cost_buckets)
      AND p.fatura_tarihi >= pb.min_date_12m
),

-- Per-bucket totals (for shares)
cost_by_bucket_12m AS (
    SELECT
        SUM(net_tutar_y) FILTER (WHERE business_bucket = 'outsourced_processing')::numeric AS outsourced_tl,
        SUM(net_tutar_y) FILTER (WHERE business_bucket = 'maintenance_factory')::numeric  AS maintenance_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN purchase_bounds pb
    WHERE p.business_bucket IN (SELECT b FROM cost_buckets)
      AND p.fatura_tarihi >= pb.min_date_12m
),

-- Active suppliers in cost scope (12m)
active_suppliers AS (
    SELECT COUNT(DISTINCT p.cari_hesap_aciklamasi)::int AS n
    FROM fact_purchase_lines_clean p
    CROSS JOIN purchase_bounds pb
    WHERE p.business_bucket IN (SELECT b FROM cost_buckets)
      AND p.cari_hesap_aciklamasi IS NOT NULL
      AND p.cari_hesap_aciklamasi <> ''
      AND p.fatura_tarihi >= pb.min_date_12m
),

-- Core revenue (12m) — same scope as Revenue Reality
revenue_total_12m AS (
    SELECT SUM(s.net_tutar_y)::numeric AS total_tl
    FROM fact_sales_lines_clean s
    CROSS JOIN sales_bounds sb
    WHERE s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
      AND COALESCE(s.subtype, '') <> 'yarn_resale'
      AND s.fatura_tarihi >= sb.min_date_12m
),

-- ── 3m windows for ratio trend ──
-- Recent 3 months (ending at last complete month)
cost_recent_3m AS (
    SELECT SUM(p.net_tutar_y)::numeric AS total_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN purchase_bounds pb
    WHERE p.business_bucket IN (SELECT b FROM cost_buckets)
      AND p.fatura_tarihi >= pb.recent_3m_start
      AND p.fatura_tarihi <  pb.month_anchor
),
revenue_recent_3m AS (
    SELECT SUM(s.net_tutar_y)::numeric AS total_tl
    FROM fact_sales_lines_clean s
    CROSS JOIN purchase_bounds pb     -- align to purchase month_anchor
    WHERE s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
      AND COALESCE(s.subtype, '') <> 'yarn_resale'
      AND s.fatura_tarihi >= pb.recent_3m_start
      AND s.fatura_tarihi <  pb.month_anchor
),

-- Prior 3 months (the 3m before the recent window)
cost_prior_3m AS (
    SELECT SUM(p.net_tutar_y)::numeric AS total_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN purchase_bounds pb
    WHERE p.business_bucket IN (SELECT b FROM cost_buckets)
      AND p.fatura_tarihi >= pb.prior_3m_start
      AND p.fatura_tarihi <  pb.recent_3m_start
),
revenue_prior_3m AS (
    SELECT SUM(s.net_tutar_y)::numeric AS total_tl
    FROM fact_sales_lines_clean s
    CROSS JOIN purchase_bounds pb
    WHERE s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
      AND COALESCE(s.subtype, '') <> 'yarn_resale'
      AND s.fatura_tarihi >= pb.prior_3m_start
      AND s.fatura_tarihi <  pb.recent_3m_start
)

SELECT
    -- Anchor row
    ROUND(
        100.0 * (SELECT total_tl FROM cost_total_12m)
              / NULLIF((SELECT total_tl FROM revenue_total_12m), 0),
        2
    ) AS cost_share_of_revenue_pct,
    ROUND(
        100.0 * (SELECT outsourced_tl FROM cost_by_bucket_12m)
              / NULLIF((SELECT total_tl FROM cost_total_12m), 0),
        2
    ) AS outsourced_processing_share_pct,
    (SELECT n FROM active_suppliers) AS active_cost_supplier_count,

    -- Context row
    ROUND(
        100.0 * (SELECT maintenance_tl FROM cost_by_bucket_12m)
              / NULLIF((SELECT total_tl FROM cost_total_12m), 0),
        2
    ) AS maintenance_share_pct,
    ROUND(
        (SELECT total_tl FROM cost_total_12m) / 12.0,
        2
    ) AS avg_monthly_cost_tl,

    -- KPI 6 — Cost/revenue ratio Δ (last 3m avg vs prior 3m avg, in pp)
    ROUND(
        (
            (100.0 * (SELECT total_tl FROM cost_recent_3m)
                   / NULLIF((SELECT total_tl FROM revenue_recent_3m), 0))
            -
            (100.0 * (SELECT total_tl FROM cost_prior_3m)
                   / NULLIF((SELECT total_tl FROM revenue_prior_3m), 0))
        )::numeric,
        1
    ) AS cost_revenue_ratio_delta_pp,
    ROUND(
        (100.0 * (SELECT total_tl FROM cost_recent_3m)
               / NULLIF((SELECT total_tl FROM revenue_recent_3m), 0))::numeric,
        1
    ) AS cost_revenue_ratio_recent_pct,
    ROUND(
        (100.0 * (SELECT total_tl FROM cost_prior_3m)
               / NULLIF((SELECT total_tl FROM revenue_prior_3m), 0))::numeric,
        1
    ) AS cost_revenue_ratio_prior_pct,

    -- Window metadata for label rendering
    (SELECT to_char(recent_3m_start, 'YYYY-MM') FROM purchase_bounds) AS recent_window_start,
    (SELECT to_char(month_anchor    - INTERVAL '1 day', 'YYYY-MM') FROM purchase_bounds) AS recent_window_end,
    (SELECT to_char(prior_3m_start,  'YYYY-MM') FROM purchase_bounds) AS prior_window_start,
    (SELECT to_char(recent_3m_start - INTERVAL '1 day', 'YYYY-MM') FROM purchase_bounds) AS prior_window_end,
    (SELECT total_tl FROM cost_total_12m)    AS cost_total_12m_tl,
    (SELECT total_tl FROM revenue_total_12m) AS revenue_total_12m_tl
;


COMMENT ON VIEW v_cost_kpis IS
'M2.4.2 — Cost Structure Phase 1 KPI strip data. Single-row view, returns
6 metrics over 12m rolling window plus a margin-pressure trend signal
(KPI 6 = cost/revenue ratio Δ in pp, last 3m avg vs prior 3m avg).
Cost scope: 6 cost buckets. Revenue scope: core + outsourced service.';
