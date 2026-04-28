-- ============================================================================
-- Migration 010 v2 — Gold Views for Operations Intelligence
-- ============================================================================
-- Version: v2 (post-review corrections)
--
-- Changes vs v1:
--   1. Separate date_bounds for purchase vs sales (revenue KPIs no longer
--      depend on purchase max date).
--   2. FX amounts split by currency (amount_try_d, amount_usd, amount_eur).
--      Mixed-currency SUM eliminated entirely.
--   3. yarn_resale exclusion is now an EXPLICIT SQL filter, not a comment.
--   4. Top suppliers/customers split into two view families:
--        - v_top_suppliers_overall   (counterparty totals)
--        - v_top_suppliers_by_bucket (counterparty x bucket — for drill)
--      Same for customers.
--   5. qty_total removed from procurement view (mixed units → meaningless).
--   6. Comments now match SQL exactly. latest_complete_month = MAX(month)-1.
--   7. Defense-in-depth: explicit subtype <> 'yarn_resale' on every revenue
--      aggregation, even though current classification already isolates it.
--
-- Currency rule (NS-A):
--   - TL is always the primary value (amount_tl)
--   - FX is split per currency: amount_try_d, amount_usd, amount_eur
--   - NEVER sum across currencies
--   - If a row's para_birimi_d is something else (GBP), it's tracked but
--     not promoted to KPI tier in MVP
--
-- Top counterparty rule (NS-B):
--   - "_overall" views: one row per counterparty (totals across all buckets)
--   - "_by_bucket" views: one row per counterparty x bucket
--   - MVP frontend uses _overall; _by_bucket exists for drill-down later
--
-- Idempotent: DROP IF EXISTS + CREATE.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- DROP existing views
-- ----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_kpi_latest_month                CASCADE;
DROP VIEW IF EXISTS v_top_customers_by_bucket         CASCADE;
DROP VIEW IF EXISTS v_top_customers_overall           CASCADE;
DROP VIEW IF EXISTS v_top_suppliers_by_bucket         CASCADE;
DROP VIEW IF EXISTS v_top_suppliers_overall           CASCADE;
DROP VIEW IF EXISTS v_monthly_revenue_core            CASCADE;
DROP VIEW IF EXISTS v_monthly_cost_structure          CASCADE;
DROP VIEW IF EXISTS v_monthly_procurement_by_bucket   CASCADE;


-- ============================================================================
-- 1) v_monthly_procurement_by_bucket
-- Panel 1 main chart. Per-month, per-bucket procurement spend.
-- TL primary; FX split by currency. No qty_total (mixed units meaningless).
-- ============================================================================
CREATE VIEW v_monthly_procurement_by_bucket AS
SELECT
    DATE_TRUNC('month', fatura_tarihi)::date          AS month,
    business_bucket,
    COUNT(*)                                          AS row_count,
    -- TL primary
    SUM(net_tutar_y)::numeric(20, 2)                  AS amount_tl,
    -- FX split by currency (no mixing across rates)
    SUM(CASE WHEN para_birimi_d = 'TRY' THEN net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_try_d,
    SUM(CASE WHEN para_birimi_d = 'USD' THEN net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_usd,
    SUM(CASE WHEN para_birimi_d = 'EUR' THEN net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_eur,
    SUM(CASE WHEN para_birimi_d NOT IN ('TRY', 'USD', 'EUR')
             THEN net_tutar_d ELSE 0 END)::numeric(20, 2)                              AS amount_other_fx,
    -- Row counts by currency for transparency
    COUNT(*) FILTER (WHERE para_birimi_d = 'USD')                                      AS rows_usd_invoiced,
    COUNT(*) FILTER (WHERE para_birimi_d = 'EUR')                                      AS rows_eur_invoiced
FROM fact_purchase_lines_clean
WHERE fatura_tarihi IS NOT NULL
  AND business_bucket IN (
      'raw_material_yarn',
      'raw_material_chemical',
      'raw_material_dye',
      'raw_material_greige_fabric'
  )
GROUP BY 1, 2;

COMMENT ON VIEW v_monthly_procurement_by_bucket IS
    'Monthly procurement spend by raw-material bucket. TL primary; FX split per currency (no mixed sums). Panel 1 main chart.';


-- ============================================================================
-- 2) v_monthly_cost_structure
-- Panel 2 main chart. Production-side costs.
-- NOTE: logistics_distribution remains a single line in MVP.
--       In M2.1 this should be split into inbound (procurement) vs outbound.
-- ============================================================================
CREATE VIEW v_monthly_cost_structure AS
SELECT
    DATE_TRUNC('month', fatura_tarihi)::date          AS month,
    business_bucket,
    COUNT(*)                                          AS row_count,
    SUM(net_tutar_y)::numeric(20, 2)                  AS amount_tl,
    SUM(CASE WHEN para_birimi_d = 'TRY' THEN net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_try_d,
    SUM(CASE WHEN para_birimi_d = 'USD' THEN net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_usd,
    SUM(CASE WHEN para_birimi_d = 'EUR' THEN net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_eur
FROM fact_purchase_lines_clean
WHERE fatura_tarihi IS NOT NULL
  AND business_bucket IN (
      'utilities',
      'maintenance_factory',
      'packaging',
      'factory_overhead',
      'outsourced_processing',
      'logistics_distribution'  -- provisional: M2.1 will split inbound/outbound
  )
GROUP BY 1, 2;

COMMENT ON VIEW v_monthly_cost_structure IS
    'Monthly production cost structure. Panel 2. logistics_distribution provisional (M2.1: split inbound/outbound). FX split per currency.';


-- ============================================================================
-- 3) v_monthly_revenue_core
-- Panel 3 main chart. Gross & net core revenue.
--
-- BUSINESS RULE (embedded explicitly):
--   yarn_resale (subtype) is EXCLUDED from core revenue.
--   Defense-in-depth: even though yarn_resale is classified to anomalous_review
--   (not core_product_sales), we still apply explicit subtype filter so any
--   future classification change cannot accidentally include it in core.
-- ============================================================================
CREATE VIEW v_monthly_revenue_core AS
WITH revenue_by_month AS (
    SELECT
        DATE_TRUNC('month', fatura_tarihi)::date AS month,
        -- Core product sales (with explicit yarn_resale defense)
        SUM(CASE
            WHEN business_bucket = 'core_product_sales'
              AND COALESCE(subtype, '') <> 'yarn_resale'
            THEN net_tutar_y ELSE 0
        END)::numeric(20, 2)                    AS core_sales_tl,
        SUM(CASE
            WHEN business_bucket = 'core_product_sales'
              AND COALESCE(subtype, '') <> 'yarn_resale'
              AND para_birimi_d = 'TRY'
            THEN net_tutar_d ELSE 0
        END)::numeric(20, 2)                    AS core_sales_try_d,
        SUM(CASE
            WHEN business_bucket = 'core_product_sales'
              AND COALESCE(subtype, '') <> 'yarn_resale'
              AND para_birimi_d = 'USD'
            THEN net_tutar_d ELSE 0
        END)::numeric(20, 2)                    AS core_sales_usd,
        SUM(CASE
            WHEN business_bucket = 'core_product_sales'
              AND COALESCE(subtype, '') <> 'yarn_resale'
              AND para_birimi_d = 'EUR'
            THEN net_tutar_d ELSE 0
        END)::numeric(20, 2)                    AS core_sales_eur,
        -- FASON service revenue
        SUM(CASE
            WHEN business_bucket = 'outsourced_service_revenue'
            THEN net_tutar_y ELSE 0
        END)::numeric(20, 2)                    AS fason_revenue_tl,
        SUM(CASE
            WHEN business_bucket = 'outsourced_service_revenue'
              AND para_birimi_d = 'USD'
            THEN net_tutar_d ELSE 0
        END)::numeric(20, 2)                    AS fason_revenue_usd,
        SUM(CASE
            WHEN business_bucket = 'outsourced_service_revenue'
              AND para_birimi_d = 'EUR'
            THEN net_tutar_d ELSE 0
        END)::numeric(20, 2)                    AS fason_revenue_eur,
        -- Sales returns/discounts (SATIŞ side)
        SUM(CASE
            WHEN business_bucket = 'sales_return_contra'
            THEN net_tutar_y ELSE 0
        END)::numeric(20, 2)                    AS satis_contra_tl,
        -- Yarn resale (tracked separately, NEVER in core)
        SUM(CASE
            WHEN COALESCE(subtype, '') = 'yarn_resale'
            THEN net_tutar_y ELSE 0
        END)::numeric(20, 2)                    AS yarn_resale_tl
    FROM fact_sales_lines_clean
    WHERE fatura_tarihi IS NOT NULL
    GROUP BY 1
),
returns_from_alis AS (
    SELECT
        DATE_TRUNC('month', fatura_tarihi)::date AS month,
        SUM(net_tutar_y)::numeric(20, 2)         AS alis_contra_tl
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
      AND business_bucket = 'sales_return_contra'
    GROUP BY 1
)
SELECT
    rbm.month,
    -- Core sales (yarn_resale-free, by currency)
    rbm.core_sales_tl,
    rbm.core_sales_try_d,
    rbm.core_sales_usd,
    rbm.core_sales_eur,
    -- FASON revenue
    rbm.fason_revenue_tl,
    rbm.fason_revenue_usd,
    rbm.fason_revenue_eur,
    -- Total contra (returns + discounts) — TL only (mixed-source FX not safe)
    (rbm.satis_contra_tl + COALESCE(raf.alis_contra_tl, 0))::numeric(20, 2)
                                                  AS total_contra_tl,
    -- Gross core revenue (TL)
    (rbm.core_sales_tl + rbm.fason_revenue_tl)::numeric(20, 2)
                                                  AS gross_revenue_tl,
    -- Net core revenue (TL)
    (rbm.core_sales_tl + rbm.fason_revenue_tl
        - rbm.satis_contra_tl
        - COALESCE(raf.alis_contra_tl, 0))::numeric(20, 2)
                                                  AS net_revenue_tl,
    -- Yarn resale (informational, NOT included in core)
    rbm.yarn_resale_tl
FROM revenue_by_month rbm
LEFT JOIN returns_from_alis raf USING (month);

COMMENT ON VIEW v_monthly_revenue_core IS
    'Monthly core revenue. Yarn resale EXPLICITLY EXCLUDED via subtype filter. Net = Gross - SATIŞ contra - ALIŞ contra. FX split per currency.';


-- ============================================================================
-- 4) v_top_suppliers_overall
-- Panel 1 list (MVP frontend uses this). One row per supplier.
-- Last 12 months, cost-relevant buckets.
-- ============================================================================
CREATE VIEW v_top_suppliers_overall AS
WITH window_bounds AS (
    SELECT
        MAX(fatura_tarihi)                                       AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '12 months')::date        AS min_date
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
)
SELECT
    p.cari_hesap_aciklamasi                              AS supplier_name,
    COUNT(*)                                             AS row_count,
    COUNT(DISTINCT p.business_bucket)                    AS bucket_count,
    SUM(p.net_tutar_y)::numeric(20, 2)                   AS amount_tl,
    SUM(CASE WHEN p.para_birimi_d = 'USD' THEN p.net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_usd,
    SUM(CASE WHEN p.para_birimi_d = 'EUR' THEN p.net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_eur,
    MIN(p.fatura_tarihi)                                 AS first_invoice_date,
    MAX(p.fatura_tarihi)                                 AS last_invoice_date,
    -- Most-spent bucket (informational)
    (
        SELECT business_bucket
        FROM fact_purchase_lines_clean p2
        WHERE p2.cari_hesap_aciklamasi = p.cari_hesap_aciklamasi
          AND p2.is_cost_model_relevant = TRUE
          AND p2.fatura_tarihi >= (SELECT min_date FROM window_bounds)
        GROUP BY business_bucket
        ORDER BY SUM(net_tutar_y) DESC
        LIMIT 1
    )                                                    AS top_bucket
FROM fact_purchase_lines_clean p
CROSS JOIN window_bounds wb
WHERE p.is_cost_model_relevant = TRUE
  AND p.cari_hesap_aciklamasi IS NOT NULL
  AND p.cari_hesap_aciklamasi <> ''
  AND p.fatura_tarihi >= wb.min_date
GROUP BY p.cari_hesap_aciklamasi;

COMMENT ON VIEW v_top_suppliers_overall IS
    'Suppliers — overall totals (last 12 months, cost-relevant buckets). One row per supplier. MVP frontend: ORDER BY amount_tl DESC LIMIT 10.';


-- ============================================================================
-- 5) v_top_suppliers_by_bucket
-- Drill-down. One row per (supplier, bucket).
-- Backend foundation; MVP UI may not consume yet.
-- ============================================================================
CREATE VIEW v_top_suppliers_by_bucket AS
WITH window_bounds AS (
    SELECT
        MAX(fatura_tarihi)                                       AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '12 months')::date        AS min_date
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
)
SELECT
    p.cari_hesap_aciklamasi                              AS supplier_name,
    p.business_bucket,
    COUNT(*)                                             AS row_count,
    SUM(p.net_tutar_y)::numeric(20, 2)                   AS amount_tl,
    SUM(CASE WHEN p.para_birimi_d = 'USD' THEN p.net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_usd,
    SUM(CASE WHEN p.para_birimi_d = 'EUR' THEN p.net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_eur,
    MIN(p.fatura_tarihi)                                 AS first_invoice_date,
    MAX(p.fatura_tarihi)                                 AS last_invoice_date
FROM fact_purchase_lines_clean p
CROSS JOIN window_bounds wb
WHERE p.is_cost_model_relevant = TRUE
  AND p.cari_hesap_aciklamasi IS NOT NULL
  AND p.cari_hesap_aciklamasi <> ''
  AND p.fatura_tarihi >= wb.min_date
GROUP BY p.cari_hesap_aciklamasi, p.business_bucket;

COMMENT ON VIEW v_top_suppliers_by_bucket IS
    'Suppliers — per-bucket breakdown (last 12 months). Drill-down view for category-level rankings.';


-- ============================================================================
-- 6) v_top_customers_overall
-- Panel 3 list (MVP frontend uses this). One row per customer.
-- Last 12 months, core-revenue buckets only. Yarn resale EXCLUDED.
-- ============================================================================
CREATE VIEW v_top_customers_overall AS
WITH window_bounds AS (
    SELECT
        MAX(fatura_tarihi)                                       AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '12 months')::date        AS min_date
    FROM fact_sales_lines_clean
    WHERE fatura_tarihi IS NOT NULL
)
SELECT
    s.cari_hesap_aciklamasi                              AS customer_name,
    COUNT(*)                                             AS row_count,
    COUNT(DISTINCT s.business_bucket)                    AS bucket_count,
    SUM(s.net_tutar_y)::numeric(20, 2)                   AS amount_tl,
    SUM(CASE WHEN s.para_birimi_d = 'USD' THEN s.net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_usd,
    SUM(CASE WHEN s.para_birimi_d = 'EUR' THEN s.net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_eur,
    -- Currency mix (transparency)
    COUNT(*) FILTER (WHERE s.para_birimi_d = 'USD')      AS rows_usd,
    COUNT(*) FILTER (WHERE s.para_birimi_d = 'TRY')      AS rows_try,
    COUNT(*) FILTER (WHERE s.para_birimi_d = 'EUR')      AS rows_eur,
    MIN(s.fatura_tarihi)                                 AS first_invoice_date,
    MAX(s.fatura_tarihi)                                 AS last_invoice_date
FROM fact_sales_lines_clean s
CROSS JOIN window_bounds wb
WHERE s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
  AND COALESCE(s.subtype, '') <> 'yarn_resale'      -- explicit defense
  AND s.cari_hesap_aciklamasi IS NOT NULL
  AND s.cari_hesap_aciklamasi <> ''
  AND s.fatura_tarihi >= wb.min_date
GROUP BY s.cari_hesap_aciklamasi;

COMMENT ON VIEW v_top_customers_overall IS
    'Customers — overall totals (last 12 months, core revenue only, yarn_resale excluded). MVP frontend: ORDER BY amount_tl DESC LIMIT 10.';


-- ============================================================================
-- 7) v_top_customers_by_bucket
-- Drill-down. One row per (customer, bucket).
-- ============================================================================
CREATE VIEW v_top_customers_by_bucket AS
WITH window_bounds AS (
    SELECT
        MAX(fatura_tarihi)                                       AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '12 months')::date        AS min_date
    FROM fact_sales_lines_clean
    WHERE fatura_tarihi IS NOT NULL
)
SELECT
    s.cari_hesap_aciklamasi                              AS customer_name,
    s.business_bucket,
    COUNT(*)                                             AS row_count,
    SUM(s.net_tutar_y)::numeric(20, 2)                   AS amount_tl,
    SUM(CASE WHEN s.para_birimi_d = 'USD' THEN s.net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_usd,
    SUM(CASE WHEN s.para_birimi_d = 'EUR' THEN s.net_tutar_d ELSE 0 END)::numeric(20, 2)  AS amount_eur,
    MIN(s.fatura_tarihi)                                 AS first_invoice_date,
    MAX(s.fatura_tarihi)                                 AS last_invoice_date
FROM fact_sales_lines_clean s
CROSS JOIN window_bounds wb
WHERE s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
  AND COALESCE(s.subtype, '') <> 'yarn_resale'
  AND s.cari_hesap_aciklamasi IS NOT NULL
  AND s.cari_hesap_aciklamasi <> ''
  AND s.fatura_tarihi >= wb.min_date
GROUP BY s.cari_hesap_aciklamasi, s.business_bucket;

COMMENT ON VIEW v_top_customers_by_bucket IS
    'Customers — per-bucket breakdown (last 12 months, core only, yarn_resale excluded). Drill-down view.';


-- ============================================================================
-- 8) v_kpi_latest_month
-- 12 KPI cards across 3 panels, with YoY.
--
-- "Latest complete month" = MAX(month) - 1 month, computed SEPARATELY for
-- purchase and sales tables (since refresh cadence may differ in future).
-- ============================================================================
CREATE VIEW v_kpi_latest_month AS
WITH
purchase_bounds AS (
    SELECT
        DATE_TRUNC('month', MAX(fatura_tarihi))::date                          AS current_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '1 month')::date   AS latest_complete_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '13 months')::date AS prior_year_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '12 months')::date AS prior_year_month_end
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),
sales_bounds AS (
    SELECT
        DATE_TRUNC('month', MAX(fatura_tarihi))::date                          AS current_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '1 month')::date   AS latest_complete_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '13 months')::date AS prior_year_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '12 months')::date AS prior_year_month_end
    FROM fact_sales_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

-- ALIŞ aggregations (per-bucket per-period)
alis_current AS (
    SELECT business_bucket,
           SUM(net_tutar_y) AS amt_tl,
           SUM(CASE WHEN para_birimi_d = 'USD' THEN net_tutar_d ELSE 0 END) AS amt_usd,
           SUM(CASE WHEN para_birimi_d = 'EUR' THEN net_tutar_d ELSE 0 END) AS amt_eur
    FROM fact_purchase_lines_clean p
    CROSS JOIN purchase_bounds db
    WHERE p.fatura_tarihi >= db.latest_complete_month_start
      AND p.fatura_tarihi <  db.current_month_start
    GROUP BY 1
),
alis_prior AS (
    SELECT business_bucket,
           SUM(net_tutar_y) AS amt_tl,
           SUM(CASE WHEN para_birimi_d = 'USD' THEN net_tutar_d ELSE 0 END) AS amt_usd,
           SUM(CASE WHEN para_birimi_d = 'EUR' THEN net_tutar_d ELSE 0 END) AS amt_eur
    FROM fact_purchase_lines_clean p
    CROSS JOIN purchase_bounds db
    WHERE p.fatura_tarihi >= db.prior_year_month_start
      AND p.fatura_tarihi <  db.prior_year_month_end
    GROUP BY 1
),

-- SATIŞ aggregations (yarn_resale excluded explicitly)
satis_current AS (
    SELECT business_bucket,
           SUM(CASE WHEN COALESCE(subtype, '') <> 'yarn_resale'
                    THEN net_tutar_y ELSE 0 END) AS amt_tl,
           SUM(CASE WHEN COALESCE(subtype, '') <> 'yarn_resale'
                     AND para_birimi_d = 'USD'
                    THEN net_tutar_d ELSE 0 END) AS amt_usd,
           SUM(CASE WHEN COALESCE(subtype, '') <> 'yarn_resale'
                     AND para_birimi_d = 'EUR'
                    THEN net_tutar_d ELSE 0 END) AS amt_eur
    FROM fact_sales_lines_clean s
    CROSS JOIN sales_bounds db
    WHERE s.fatura_tarihi >= db.latest_complete_month_start
      AND s.fatura_tarihi <  db.current_month_start
    GROUP BY 1
),
satis_prior AS (
    SELECT business_bucket,
           SUM(CASE WHEN COALESCE(subtype, '') <> 'yarn_resale'
                    THEN net_tutar_y ELSE 0 END) AS amt_tl,
           SUM(CASE WHEN COALESCE(subtype, '') <> 'yarn_resale'
                     AND para_birimi_d = 'USD'
                    THEN net_tutar_d ELSE 0 END) AS amt_usd,
           SUM(CASE WHEN COALESCE(subtype, '') <> 'yarn_resale'
                     AND para_birimi_d = 'EUR'
                    THEN net_tutar_d ELSE 0 END) AS amt_eur
    FROM fact_sales_lines_clean s
    CROSS JOIN sales_bounds db
    WHERE s.fatura_tarihi >= db.prior_year_month_start
      AND s.fatura_tarihi <  db.prior_year_month_end
    GROUP BY 1
),

kpis AS (
    -- ============ PANEL 1: PROCUREMENT ============
    SELECT 'procurement'::text AS panel, 1::int AS display_order,
        'total_procurement'::text AS metric_key,
        'Total procurement (raw materials)'::text AS metric_label,
        COALESCE((SELECT SUM(amt_tl) FROM alis_current
                  WHERE business_bucket IN ('raw_material_yarn', 'raw_material_chemical',
                                            'raw_material_dye', 'raw_material_greige_fabric')), 0) AS current_tl,
        COALESCE((SELECT SUM(amt_usd) FROM alis_current
                  WHERE business_bucket IN ('raw_material_yarn', 'raw_material_chemical',
                                            'raw_material_dye', 'raw_material_greige_fabric')), 0) AS current_usd,
        COALESCE((SELECT SUM(amt_eur) FROM alis_current
                  WHERE business_bucket IN ('raw_material_yarn', 'raw_material_chemical',
                                            'raw_material_dye', 'raw_material_greige_fabric')), 0) AS current_eur,
        COALESCE((SELECT SUM(amt_tl) FROM alis_prior
                  WHERE business_bucket IN ('raw_material_yarn', 'raw_material_chemical',
                                            'raw_material_dye', 'raw_material_greige_fabric')), 0) AS prior_tl,
        COALESCE((SELECT SUM(amt_usd) FROM alis_prior
                  WHERE business_bucket IN ('raw_material_yarn', 'raw_material_chemical',
                                            'raw_material_dye', 'raw_material_greige_fabric')), 0) AS prior_usd,
        COALESCE((SELECT SUM(amt_eur) FROM alis_prior
                  WHERE business_bucket IN ('raw_material_yarn', 'raw_material_chemical',
                                            'raw_material_dye', 'raw_material_greige_fabric')), 0) AS prior_eur
    UNION ALL
    SELECT 'procurement', 2, 'yarn', 'Yarn purchases',
        COALESCE((SELECT amt_tl  FROM alis_current WHERE business_bucket = 'raw_material_yarn'), 0),
        COALESCE((SELECT amt_usd FROM alis_current WHERE business_bucket = 'raw_material_yarn'), 0),
        COALESCE((SELECT amt_eur FROM alis_current WHERE business_bucket = 'raw_material_yarn'), 0),
        COALESCE((SELECT amt_tl  FROM alis_prior   WHERE business_bucket = 'raw_material_yarn'), 0),
        COALESCE((SELECT amt_usd FROM alis_prior   WHERE business_bucket = 'raw_material_yarn'), 0),
        COALESCE((SELECT amt_eur FROM alis_prior   WHERE business_bucket = 'raw_material_yarn'), 0)
    UNION ALL
    SELECT 'procurement', 3, 'chemical_dye', 'Chemical + Dye',
        COALESCE((SELECT SUM(amt_tl)  FROM alis_current WHERE business_bucket IN ('raw_material_chemical', 'raw_material_dye')), 0),
        COALESCE((SELECT SUM(amt_usd) FROM alis_current WHERE business_bucket IN ('raw_material_chemical', 'raw_material_dye')), 0),
        COALESCE((SELECT SUM(amt_eur) FROM alis_current WHERE business_bucket IN ('raw_material_chemical', 'raw_material_dye')), 0),
        COALESCE((SELECT SUM(amt_tl)  FROM alis_prior   WHERE business_bucket IN ('raw_material_chemical', 'raw_material_dye')), 0),
        COALESCE((SELECT SUM(amt_usd) FROM alis_prior   WHERE business_bucket IN ('raw_material_chemical', 'raw_material_dye')), 0),
        COALESCE((SELECT SUM(amt_eur) FROM alis_prior   WHERE business_bucket IN ('raw_material_chemical', 'raw_material_dye')), 0)
    UNION ALL
    SELECT 'procurement', 4, 'greige', 'Greige fabric',
        COALESCE((SELECT amt_tl  FROM alis_current WHERE business_bucket = 'raw_material_greige_fabric'), 0),
        COALESCE((SELECT amt_usd FROM alis_current WHERE business_bucket = 'raw_material_greige_fabric'), 0),
        COALESCE((SELECT amt_eur FROM alis_current WHERE business_bucket = 'raw_material_greige_fabric'), 0),
        COALESCE((SELECT amt_tl  FROM alis_prior   WHERE business_bucket = 'raw_material_greige_fabric'), 0),
        COALESCE((SELECT amt_usd FROM alis_prior   WHERE business_bucket = 'raw_material_greige_fabric'), 0),
        COALESCE((SELECT amt_eur FROM alis_prior   WHERE business_bucket = 'raw_material_greige_fabric'), 0)

    -- ============ PANEL 2: COST STRUCTURE ============
    UNION ALL
    SELECT 'cost_structure', 1, 'utilities', 'Utilities',
        COALESCE((SELECT amt_tl  FROM alis_current WHERE business_bucket = 'utilities'), 0),
        COALESCE((SELECT amt_usd FROM alis_current WHERE business_bucket = 'utilities'), 0),
        COALESCE((SELECT amt_eur FROM alis_current WHERE business_bucket = 'utilities'), 0),
        COALESCE((SELECT amt_tl  FROM alis_prior   WHERE business_bucket = 'utilities'), 0),
        COALESCE((SELECT amt_usd FROM alis_prior   WHERE business_bucket = 'utilities'), 0),
        COALESCE((SELECT amt_eur FROM alis_prior   WHERE business_bucket = 'utilities'), 0)
    UNION ALL
    SELECT 'cost_structure', 2, 'maintenance', 'Maintenance',
        COALESCE((SELECT amt_tl  FROM alis_current WHERE business_bucket = 'maintenance_factory'), 0),
        COALESCE((SELECT amt_usd FROM alis_current WHERE business_bucket = 'maintenance_factory'), 0),
        COALESCE((SELECT amt_eur FROM alis_current WHERE business_bucket = 'maintenance_factory'), 0),
        COALESCE((SELECT amt_tl  FROM alis_prior   WHERE business_bucket = 'maintenance_factory'), 0),
        COALESCE((SELECT amt_usd FROM alis_prior   WHERE business_bucket = 'maintenance_factory'), 0),
        COALESCE((SELECT amt_eur FROM alis_prior   WHERE business_bucket = 'maintenance_factory'), 0)
    UNION ALL
    SELECT 'cost_structure', 3, 'fason', 'FASON (outsourced processing)',
        COALESCE((SELECT amt_tl  FROM alis_current WHERE business_bucket = 'outsourced_processing'), 0),
        COALESCE((SELECT amt_usd FROM alis_current WHERE business_bucket = 'outsourced_processing'), 0),
        COALESCE((SELECT amt_eur FROM alis_current WHERE business_bucket = 'outsourced_processing'), 0),
        COALESCE((SELECT amt_tl  FROM alis_prior   WHERE business_bucket = 'outsourced_processing'), 0),
        COALESCE((SELECT amt_usd FROM alis_prior   WHERE business_bucket = 'outsourced_processing'), 0),
        COALESCE((SELECT amt_eur FROM alis_prior   WHERE business_bucket = 'outsourced_processing'), 0)
    UNION ALL
    SELECT 'cost_structure', 4, 'factory_overhead', 'Factory overhead',
        COALESCE((SELECT amt_tl  FROM alis_current WHERE business_bucket = 'factory_overhead'), 0),
        COALESCE((SELECT amt_usd FROM alis_current WHERE business_bucket = 'factory_overhead'), 0),
        COALESCE((SELECT amt_eur FROM alis_current WHERE business_bucket = 'factory_overhead'), 0),
        COALESCE((SELECT amt_tl  FROM alis_prior   WHERE business_bucket = 'factory_overhead'), 0),
        COALESCE((SELECT amt_usd FROM alis_prior   WHERE business_bucket = 'factory_overhead'), 0),
        COALESCE((SELECT amt_eur FROM alis_prior   WHERE business_bucket = 'factory_overhead'), 0)

    -- ============ PANEL 3: REVENUE REALITY ============
    UNION ALL
    SELECT 'revenue_reality', 1, 'core_sales',
        'Core product sales (yarn resale excluded)',
        COALESCE((SELECT amt_tl  FROM satis_current WHERE business_bucket = 'core_product_sales'), 0),
        COALESCE((SELECT amt_usd FROM satis_current WHERE business_bucket = 'core_product_sales'), 0),
        COALESCE((SELECT amt_eur FROM satis_current WHERE business_bucket = 'core_product_sales'), 0),
        COALESCE((SELECT amt_tl  FROM satis_prior   WHERE business_bucket = 'core_product_sales'), 0),
        COALESCE((SELECT amt_usd FROM satis_prior   WHERE business_bucket = 'core_product_sales'), 0),
        COALESCE((SELECT amt_eur FROM satis_prior   WHERE business_bucket = 'core_product_sales'), 0)
    UNION ALL
    SELECT 'revenue_reality', 2, 'fason_revenue', 'FASON service revenue',
        COALESCE((SELECT amt_tl  FROM satis_current WHERE business_bucket = 'outsourced_service_revenue'), 0),
        COALESCE((SELECT amt_usd FROM satis_current WHERE business_bucket = 'outsourced_service_revenue'), 0),
        COALESCE((SELECT amt_eur FROM satis_current WHERE business_bucket = 'outsourced_service_revenue'), 0),
        COALESCE((SELECT amt_tl  FROM satis_prior   WHERE business_bucket = 'outsourced_service_revenue'), 0),
        COALESCE((SELECT amt_usd FROM satis_prior   WHERE business_bucket = 'outsourced_service_revenue'), 0),
        COALESCE((SELECT amt_eur FROM satis_prior   WHERE business_bucket = 'outsourced_service_revenue'), 0)
    UNION ALL
    -- Net revenue (TL only — net is conceptually TL because contra is mixed-source)
    SELECT 'revenue_reality', 3, 'net_revenue',
        'Net revenue (after returns/discounts)',
        COALESCE((SELECT amt_tl FROM satis_current WHERE business_bucket = 'core_product_sales'), 0)
        + COALESCE((SELECT amt_tl FROM satis_current WHERE business_bucket = 'outsourced_service_revenue'), 0)
        - COALESCE((SELECT amt_tl FROM satis_current WHERE business_bucket = 'sales_return_contra'), 0)
        - COALESCE((SELECT amt_tl FROM alis_current  WHERE business_bucket = 'sales_return_contra'), 0),
        0::numeric, 0::numeric,  -- net revenue not split by FX (unsafe)
        COALESCE((SELECT amt_tl FROM satis_prior   WHERE business_bucket = 'core_product_sales'), 0)
        + COALESCE((SELECT amt_tl FROM satis_prior   WHERE business_bucket = 'outsourced_service_revenue'), 0)
        - COALESCE((SELECT amt_tl FROM satis_prior   WHERE business_bucket = 'sales_return_contra'), 0)
        - COALESCE((SELECT amt_tl FROM alis_prior    WHERE business_bucket = 'sales_return_contra'), 0),
        0::numeric, 0::numeric
    UNION ALL
    -- Total contra (TL only)
    SELECT 'revenue_reality', 4, 'contra_revenue',
        'Total contra revenue (returns + discounts)',
        COALESCE((SELECT amt_tl FROM satis_current WHERE business_bucket = 'sales_return_contra'), 0)
        + COALESCE((SELECT amt_tl FROM alis_current  WHERE business_bucket = 'sales_return_contra'), 0),
        0::numeric, 0::numeric,
        COALESCE((SELECT amt_tl FROM satis_prior   WHERE business_bucket = 'sales_return_contra'), 0)
        + COALESCE((SELECT amt_tl FROM alis_prior    WHERE business_bucket = 'sales_return_contra'), 0),
        0::numeric, 0::numeric
)

SELECT
    panel,
    display_order,
    metric_key,
    metric_label,
    -- TL primary
    current_tl::numeric(20, 2)                       AS current_tl,
    prior_tl::numeric(20, 2)                         AS prior_tl,
    CASE WHEN prior_tl IS NULL OR prior_tl = 0 THEN NULL
         ELSE ROUND(((current_tl - prior_tl) / prior_tl * 100)::numeric, 1)
    END                                              AS yoy_pct_tl,
    -- USD secondary (for USD-invoiced rows only)
    current_usd::numeric(20, 2)                      AS current_usd,
    prior_usd::numeric(20, 2)                        AS prior_usd,
    CASE WHEN prior_usd IS NULL OR prior_usd = 0 THEN NULL
         ELSE ROUND(((current_usd - prior_usd) / prior_usd * 100)::numeric, 1)
    END                                              AS yoy_pct_usd,
    -- EUR secondary
    current_eur::numeric(20, 2)                      AS current_eur,
    prior_eur::numeric(20, 2)                        AS prior_eur,
    CASE WHEN prior_eur IS NULL OR prior_eur = 0 THEN NULL
         ELSE ROUND(((current_eur - prior_eur) / prior_eur * 100)::numeric, 1)
    END                                              AS yoy_pct_eur,
    -- Reference dates
    (SELECT latest_complete_month_start FROM purchase_bounds) AS purchase_latest_month,
    (SELECT latest_complete_month_start FROM sales_bounds)    AS sales_latest_month
FROM kpis
ORDER BY panel, display_order;

COMMENT ON VIEW v_kpi_latest_month IS
    'KPI metrics (12 cards). Latest complete month = MAX(month)-1. Purchase and sales date bounds computed separately. TL primary; USD/EUR secondary, never mixed. Yarn resale excluded explicitly.';


COMMIT;

-- ============================================================================
-- End of migration 010 v2
-- ============================================================================
