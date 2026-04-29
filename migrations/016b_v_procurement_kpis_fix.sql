-- =============================================================================
-- Migration 016b — v_procurement_kpis correctness patch
-- =============================================================================
-- Issue 1: latest_month was the month containing MAX(fatura_tarihi). When that
--          month is in-progress (e.g. running on 2026-04-15, latest_month
--          would be 2026-04 with partial data), MoM comparison vs 2026-03 is
--          unfair — the partial month always looks like a sharp drop.
--
-- Fix: redefine latest_month as the most recent FULLY-COMPLETED month.
--      Heuristic: take the latest month for which we have data extending into
--      the next month — i.e. there exists at least one row with
--      fatura_tarihi >= (latest_month_start + 1 month).
--      Equivalently: drop the in-progress trailing month if MAX(fatura_tarihi)
--      is inside it.
--
-- Issue 2: biggest_mover_sign returned '' for negative values, providing no
--          information. Frontend will infer sign from the numeric value.
-- =============================================================================

DROP VIEW IF EXISTS v_procurement_kpis CASCADE;

CREATE VIEW v_procurement_kpis AS
WITH
window_bounds AS (
    SELECT
        MAX(fatura_tarihi) AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '1 year')::date AS min_date,
        -- Last complete month: the month BEFORE the month containing max_date,
        -- IF max_date is not the last day of its month. Otherwise max_date's month.
        -- Simpler heuristic: take the previous month boundary unless we have
        -- evidence that max_date's month is fully closed (i.e. max_date >=
        -- last day of its month). For safety, always step back one month if
        -- we are inside the month.
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
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

total_12m AS (
    SELECT SUM(p.net_tutar_y)::numeric AS grand_total
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.is_cost_model_relevant = true
      AND p.fatura_tarihi >= wb.min_date
),

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

top_3_total AS (
    SELECT SUM(supplier_amount_tl)::numeric AS top_3_amount_tl
    FROM (
        SELECT supplier_amount_tl
        FROM supplier_totals
        ORDER BY supplier_amount_tl DESC NULLS LAST
        LIMIT 3
    ) t
),

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

supplier_count AS (
    SELECT COUNT(*)::int AS n_suppliers
    FROM supplier_totals
),

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

yarn_share AS (
    SELECT COALESCE(SUM(bucket_amount_tl), 0)::numeric AS yarn_amount_tl
    FROM bucket_totals
    WHERE business_bucket = 'raw_material_yarn'
),

greige_share AS (
    SELECT COALESCE(SUM(bucket_amount_tl), 0)::numeric AS greige_amount_tl
    FROM bucket_totals
    WHERE business_bucket = 'raw_material_greige_fabric'
),

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

biggest_mover AS (
    SELECT
        business_bucket AS biggest_mover_bucket,
        delta_pct       AS biggest_mover_pct,
        delta_tl        AS biggest_mover_tl
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

    -- Window metadata
    (SELECT to_char(latest_month_start, 'YYYY-MM') FROM window_bounds) AS latest_month,
    (SELECT to_char(prior_month_start,  'YYYY-MM') FROM window_bounds) AS prior_month,
    (SELECT grand_total FROM total_12m) AS total_12m_tl
;


COMMENT ON VIEW v_procurement_kpis IS
'M2.2.2 — Procurement Phase 1 KPI strip data. v016b: latest_month is the most
recent FULLY-COMPLETED calendar month (drops in-progress trailing month).
Sign column removed — frontend infers from numeric value.';
