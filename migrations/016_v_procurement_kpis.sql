-- =============================================================================
-- Migration 016 — v_procurement_kpis
-- =============================================================================
-- M2.2.2 Procurement Phase 1 — KPI strip data source.
--
-- Provides 6 anchor + context metrics for the Procurement sub-tab:
--
--   ANCHOR (top row, primary signals):
--     1. top_3_supplier_share_pct  — concentration risk indicator
--     2. fx_invoiced_share_pct     — FX exposure on payable side
--     3. active_supplier_count     — number of suppliers active in last 12m
--
--   CONTEXT (bottom row, supporting detail):
--     4. yarn_share_pct            — yarn as % of total cost-relevant procurement
--     5. greige_share_pct          — greige fabric as % of total
--     6. largest_monthly_delta_pct + label — biggest MoM movement among
--                                            cost-relevant buckets in last
--                                            complete month vs prior month
--
-- All metrics are computed within the standard 12-month rolling window,
-- consistent with v_top_suppliers_overall.
-- =============================================================================

DROP VIEW IF EXISTS v_procurement_kpis CASCADE;

CREATE VIEW v_procurement_kpis AS
WITH
window_bounds AS (
    SELECT
        MAX(fatura_tarihi)                                      AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '1 year')::date          AS min_date,
        DATE_TRUNC('month', MAX(fatura_tarihi))::date           AS latest_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '1 month')::date AS prior_month_start
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

-- Total cost-relevant procurement in 12m window
total_12m AS (
    SELECT SUM(p.net_tutar_y)::numeric AS grand_total
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.is_cost_model_relevant = true
      AND p.fatura_tarihi >= wb.min_date
),

-- Per-supplier 12m totals (cost-relevant only)
supplier_totals AS (
    SELECT
        p.cari_hesap_aciklamasi AS supplier_name,
        SUM(p.net_tutar_y)::numeric AS supplier_amount_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.is_cost_model_relevant = true
      AND p.fatura_tarihi >= wb.min_date
      AND p.cari_hesap_aciklamasi IS NOT NULL
      AND p.cari_hesap_aciklamasi <> ''
    GROUP BY p.cari_hesap_aciklamasi
),

-- Top 3 suppliers' total
top_3_total AS (
    SELECT SUM(supplier_amount_tl)::numeric AS top_3_amount_tl
    FROM (
        SELECT supplier_amount_tl
        FROM supplier_totals
        ORDER BY supplier_amount_tl DESC NULLS LAST
        LIMIT 3
    ) t
),

-- FX-invoiced rows (USD or EUR) — share of TL value
fx_share AS (
    SELECT
        SUM(CASE WHEN p.para_birimi_d IN ('USD', 'EUR')
                 THEN p.net_tutar_y ELSE 0 END)::numeric AS fx_amount_tl,
        SUM(p.net_tutar_y)::numeric                       AS total_amount_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.is_cost_model_relevant = true
      AND p.fatura_tarihi >= wb.min_date
),

-- Active supplier count
supplier_count AS (
    SELECT COUNT(*)::int AS n_suppliers
    FROM supplier_totals
),

-- Per-bucket 12m totals
bucket_totals AS (
    SELECT
        p.business_bucket,
        SUM(p.net_tutar_y)::numeric AS bucket_amount_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.is_cost_model_relevant = true
      AND p.fatura_tarihi >= wb.min_date
    GROUP BY p.business_bucket
),

-- Yarn share
yarn_share AS (
    SELECT COALESCE(SUM(bucket_amount_tl), 0)::numeric AS yarn_amount_tl
    FROM bucket_totals
    WHERE business_bucket = 'raw_material_yarn'
),

-- Greige share
greige_share AS (
    SELECT COALESCE(SUM(bucket_amount_tl), 0)::numeric AS greige_amount_tl
    FROM bucket_totals
    WHERE business_bucket = 'raw_material_greige_fabric'
),

-- Latest complete month per bucket
latest_by_bucket AS (
    SELECT
        p.business_bucket,
        SUM(CASE WHEN DATE_TRUNC('month', p.fatura_tarihi)::date = wb.latest_month_start
                 THEN p.net_tutar_y ELSE 0 END)::numeric AS latest_amount_tl,
        SUM(CASE WHEN DATE_TRUNC('month', p.fatura_tarihi)::date = wb.prior_month_start
                 THEN p.net_tutar_y ELSE 0 END)::numeric AS prior_amount_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.is_cost_model_relevant = true
      AND p.business_bucket IS NOT NULL
      AND p.fatura_tarihi >= wb.prior_month_start
    GROUP BY p.business_bucket
),

-- Largest monthly delta (% change) — only among buckets with prior > 0 to avoid divide-by-zero noise
delta_per_bucket AS (
    SELECT
        business_bucket,
        latest_amount_tl,
        prior_amount_tl,
        latest_amount_tl - prior_amount_tl AS delta_tl,
        CASE
            WHEN prior_amount_tl > 0
            THEN ROUND(100.0 * (latest_amount_tl - prior_amount_tl) / prior_amount_tl, 1)
            ELSE NULL
        END AS delta_pct
    FROM latest_by_bucket
),

-- Pick the largest absolute movement among meaningful buckets
-- (require prior >= 100k TL to avoid noisy small-base swings)
biggest_mover AS (
    SELECT
        business_bucket AS biggest_mover_bucket,
        delta_pct       AS biggest_mover_pct,
        delta_tl        AS biggest_mover_tl,
        CASE WHEN delta_tl >= 0 THEN '+' ELSE '' END AS biggest_mover_sign
    FROM delta_per_bucket
    WHERE delta_pct IS NOT NULL
      AND prior_amount_tl >= 100000
    ORDER BY ABS(delta_pct) DESC NULLS LAST
    LIMIT 1
)

SELECT
    -- Anchor row
    ROUND(
        100.0 * (SELECT top_3_amount_tl FROM top_3_total)
              / NULLIF((SELECT grand_total FROM total_12m), 0),
        2
    ) AS top_3_supplier_share_pct,
    ROUND(
        100.0 * (SELECT fx_amount_tl FROM fx_share)
              / NULLIF((SELECT total_amount_tl FROM fx_share), 0),
        2
    ) AS fx_invoiced_share_pct,
    (SELECT n_suppliers FROM supplier_count) AS active_supplier_count,

    -- Context row
    ROUND(
        100.0 * (SELECT yarn_amount_tl FROM yarn_share)
              / NULLIF((SELECT grand_total FROM total_12m), 0),
        2
    ) AS yarn_share_pct,
    ROUND(
        100.0 * (SELECT greige_amount_tl FROM greige_share)
              / NULLIF((SELECT grand_total FROM total_12m), 0),
        2
    ) AS greige_share_pct,
    (SELECT biggest_mover_bucket FROM biggest_mover) AS biggest_mover_bucket,
    (SELECT biggest_mover_pct FROM biggest_mover)    AS biggest_mover_pct,
    (SELECT biggest_mover_tl  FROM biggest_mover)    AS biggest_mover_tl,
    (SELECT biggest_mover_sign FROM biggest_mover)   AS biggest_mover_sign,

    -- Window metadata
    (SELECT to_char(latest_month_start, 'YYYY-MM') FROM window_bounds) AS latest_month,
    (SELECT to_char(prior_month_start,  'YYYY-MM') FROM window_bounds) AS prior_month,
    (SELECT grand_total FROM total_12m) AS total_12m_tl
;


COMMENT ON VIEW v_procurement_kpis IS
'M2.2.2 — Procurement Phase 1 KPI strip data. Single-row view, returns 6 anchor
+ context metrics over the 12-month rolling window. Largest mover requires
prior-month bucket spend >= 100k TL to avoid small-base noise.';
