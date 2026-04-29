-- =============================================================================
-- Migration 024 — Re-scope Procurement views to raw materials only
-- =============================================================================
-- Issue: The Procurement section was using `is_cost_model_relevant = TRUE`
--        which includes utilities, factory_overhead, maintenance, packaging,
--        outsourced_processing, logistics_distribution. These are operational
--        costs and live in the Cost Structure section. They were appearing in
--        BOTH sections — same supplier (e.g. AKSA ELEKTRİK) shown twice.
--
-- Fix: Procurement scope is now strictly the 4 raw-material buckets:
--        - raw_material_yarn
--        - raw_material_chemical
--        - raw_material_dye
--        - raw_material_greige_fabric
--
--      Cost Structure keeps its own 6-bucket scope. No overlap.
--
-- Affected views (4):
--   1. v_top_suppliers_overall          (Migration 015)
--   2. v_procurement_kpis               (Migration 016b)
--   3. v_procurement_concentration_trend (Migration 017)
--   4. v_monthly_procurement_by_currency (Migration 018)
--
-- v_monthly_procurement_by_bucket (Migration 010) was already raw-material
-- scoped — no change.
--
-- Frontend: NO CHANGES. Endpoints return the same columns, just with the
--           narrowed scope. Numbers will shift:
--             - Top 10 Suppliers: utilities/maintenance suppliers drop out
--             - Top 3 share %: rises (denominator shrinks faster than top 3)
--             - FX share %: rises (raw materials are USD-heavy; utilities are TRY)
--             - Active supplier count: drops (utilities suppliers excluded)
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────
-- 1) v_top_suppliers_overall (originally Migration 015)
-- ─────────────────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS v_top_suppliers_overall CASCADE;

CREATE VIEW v_top_suppliers_overall AS
WITH
window_bounds AS (
    SELECT
        MAX(fatura_tarihi)                                AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '12 months')::date AS min_date,
        (MAX(fatura_tarihi) - INTERVAL '6 months')::date  AS h2_start
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

raw_material_buckets(b) AS (
    VALUES
      ('raw_material_yarn'),
      ('raw_material_chemical'),
      ('raw_material_dye'),
      ('raw_material_greige_fabric')
),

base AS (
    SELECT
        p.cari_hesap_aciklamasi                                                            AS supplier_name,
        COUNT(*)                                                                           AS row_count,
        COUNT(DISTINCT p.business_bucket)                                                  AS bucket_count,
        SUM(p.net_tutar_y)::numeric(20, 2)                                                 AS amount_tl,
        SUM(CASE WHEN p.para_birimi_d = 'USD' THEN p.net_tutar_d ELSE 0 END)::numeric(20,2) AS amount_usd,
        SUM(CASE WHEN p.para_birimi_d = 'EUR' THEN p.net_tutar_d ELSE 0 END)::numeric(20,2) AS amount_eur,
        MAX(p.business_bucket)                                                             AS top_bucket_seed,
        SUM(p.net_tutar_y) FILTER (
            WHERE p.fatura_tarihi >= (SELECT min_date FROM window_bounds)
              AND p.fatura_tarihi <  (SELECT h2_start FROM window_bounds)
        )::numeric(20, 2) AS amount_tl_h1,
        SUM(p.net_tutar_y) FILTER (
            WHERE p.fatura_tarihi >= (SELECT h2_start FROM window_bounds)
        )::numeric(20, 2) AS amount_tl_h2,
        MIN(p.fatura_tarihi)                                                               AS first_invoice_date,
        MAX(p.fatura_tarihi)                                                               AS last_invoice_date
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.business_bucket IN (SELECT b FROM raw_material_buckets)
      AND p.cari_hesap_aciklamasi IS NOT NULL
      AND p.cari_hesap_aciklamasi <> ''
      AND p.fatura_tarihi >= wb.min_date
    GROUP BY p.cari_hesap_aciklamasi
),

-- True top bucket per supplier (not MAX which is alphabetic)
sb AS (
    SELECT
        cari_hesap_aciklamasi AS supplier_name,
        business_bucket       AS bucket,
        SUM(net_tutar_y)::numeric AS bucket_amount_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.business_bucket IN (SELECT b FROM raw_material_buckets)
      AND p.cari_hesap_aciklamasi IS NOT NULL
      AND p.cari_hesap_aciklamasi <> ''
      AND p.fatura_tarihi >= wb.min_date
    GROUP BY 1, 2
),
sb_ranked AS (
    SELECT supplier_name, bucket,
           ROW_NUMBER() OVER (PARTITION BY supplier_name ORDER BY bucket_amount_tl DESC) AS rk
    FROM sb
),
top_bucket_per_supplier AS (
    SELECT supplier_name, bucket AS top_bucket
    FROM sb_ranked WHERE rk = 1
),

grand_total AS (
    SELECT SUM(amount_tl)::numeric AS total_tl FROM base
),

cp_lookup AS (
    SELECT DISTINCT ON (display_name)
        display_name, vergi_numarasi, is_verified, name_variants_count
    FROM dim_counterparty_mv
    WHERE side = 'purchase'
    ORDER BY display_name, total_tl_24m DESC NULLS LAST
)

SELECT
    b.supplier_name,
    b.row_count,
    b.bucket_count,
    b.amount_tl,
    b.amount_usd,
    b.amount_eur,
    tb.top_bucket,
    b.first_invoice_date,
    b.last_invoice_date,
    ROUND(
        100.0 * b.amount_tl / NULLIF((SELECT total_tl FROM grand_total), 0),
        2
    )::numeric(6, 2) AS share_pct,
    CASE
        WHEN b.amount_tl_h1 IS NULL OR b.amount_tl_h1 = 0 THEN '–'
        WHEN b.amount_tl_h2 / b.amount_tl_h1 >= 1.10 THEN '▲'
        WHEN b.amount_tl_h2 / b.amount_tl_h1 <= 0.90 THEN '▼'
        ELSE '–'
    END AS trend_direction,
    b.amount_tl_h1,
    b.amount_tl_h2,
    cp.vergi_numarasi,
    COALESCE(cp.is_verified, FALSE)     AS is_verified,
    COALESCE(cp.name_variants_count, 1) AS name_variants_count
FROM base b
LEFT JOIN top_bucket_per_supplier tb ON tb.supplier_name = b.supplier_name
LEFT JOIN cp_lookup cp ON cp.display_name = b.supplier_name;

COMMENT ON VIEW v_top_suppliers_overall IS
'M2.2.1 (re-scoped in Migration 024) — Top suppliers in raw-material scope only:
yarn / chemical / dye / greige_fabric. Operational suppliers (utilities,
maintenance, fason, etc.) are tracked in Cost Structure section instead.';


-- ─────────────────────────────────────────────────────────────────────────
-- 2) v_procurement_kpis (originally Migration 016b)
-- ─────────────────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS v_procurement_kpis CASCADE;

CREATE VIEW v_procurement_kpis AS
WITH
purchase_bounds AS (
    SELECT
        MAX(fatura_tarihi) AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '12 months')::date AS min_date_12m,
        DATE_TRUNC('month', MAX(fatura_tarihi))::date                          AS current_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '1 month')::date   AS latest_complete_month_start,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '2 months')::date  AS prior_month_start
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

raw_material_buckets(b) AS (
    VALUES
      ('raw_material_yarn'),
      ('raw_material_chemical'),
      ('raw_material_dye'),
      ('raw_material_greige_fabric')
),

total_12m AS (
    SELECT SUM(p.net_tutar_y)::numeric AS grand_total
    FROM fact_purchase_lines_clean p
    CROSS JOIN purchase_bounds pb
    WHERE p.business_bucket IN (SELECT b FROM raw_material_buckets)
      AND p.fatura_tarihi >= pb.min_date_12m
),

supplier_totals AS (
    SELECT
        p.cari_hesap_aciklamasi AS supplier_name,
        SUM(p.net_tutar_y)::numeric AS supplier_amount_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN purchase_bounds pb
    WHERE p.business_bucket IN (SELECT b FROM raw_material_buckets)
      AND p.cari_hesap_aciklamasi IS NOT NULL
      AND p.cari_hesap_aciklamasi <> ''
      AND p.fatura_tarihi >= pb.min_date_12m
    GROUP BY p.cari_hesap_aciklamasi
),

top_3_total AS (
    SELECT SUM(supplier_amount_tl)::numeric AS top_3_amount_tl
    FROM (
        SELECT supplier_amount_tl FROM supplier_totals
        ORDER BY supplier_amount_tl DESC NULLS LAST LIMIT 3
    ) t
),

fx_share AS (
    SELECT
        SUM(CASE WHEN p.para_birimi_d IN ('USD', 'EUR')
                 THEN p.net_tutar_y ELSE 0 END)::numeric AS fx_amount_tl,
        SUM(p.net_tutar_y)::numeric                       AS total_amount_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN purchase_bounds pb
    WHERE p.business_bucket IN (SELECT b FROM raw_material_buckets)
      AND p.fatura_tarihi >= pb.min_date_12m
),

active_supplier_cnt AS (
    SELECT COUNT(*)::int AS n FROM supplier_totals
),

bucket_totals AS (
    SELECT
        SUM(net_tutar_y) FILTER (WHERE business_bucket = 'raw_material_yarn')::numeric          AS yarn_tl,
        SUM(net_tutar_y) FILTER (WHERE business_bucket = 'raw_material_greige_fabric')::numeric AS greige_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN purchase_bounds pb
    WHERE p.business_bucket IN (SELECT b FROM raw_material_buckets)
      AND p.fatura_tarihi >= pb.min_date_12m
),

-- Biggest mover bucket: latest complete month vs prior complete month
mover_data AS (
    SELECT
        business_bucket,
        SUM(net_tutar_y) FILTER (
            WHERE fatura_tarihi >= (SELECT latest_complete_month_start FROM purchase_bounds)
              AND fatura_tarihi <  (SELECT current_month_start FROM purchase_bounds)
        )::numeric AS latest_tl,
        SUM(net_tutar_y) FILTER (
            WHERE fatura_tarihi >= (SELECT prior_month_start FROM purchase_bounds)
              AND fatura_tarihi <  (SELECT latest_complete_month_start FROM purchase_bounds)
        )::numeric AS prior_tl
    FROM fact_purchase_lines_clean
    WHERE business_bucket IN (SELECT b FROM raw_material_buckets)
    GROUP BY business_bucket
),
mover_pct AS (
    SELECT business_bucket, latest_tl, prior_tl,
           CASE
             WHEN prior_tl IS NULL OR prior_tl = 0 THEN NULL
             ELSE 100.0 * (latest_tl - prior_tl) / prior_tl
           END AS pct_change,
           ABS(COALESCE(latest_tl - prior_tl, 0)) AS abs_change_tl
    FROM mover_data
),
biggest_mover AS (
    SELECT business_bucket AS biggest_mover_bucket,
           ROUND(pct_change::numeric, 1) AS biggest_mover_pct,
           (latest_tl - prior_tl)::numeric(20,2) AS biggest_mover_tl
    FROM mover_pct
    WHERE pct_change IS NOT NULL
    ORDER BY abs_change_tl DESC NULLS LAST
    LIMIT 1
)

SELECT
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
    (SELECT n FROM active_supplier_cnt) AS active_supplier_count,
    ROUND(
        100.0 * (SELECT yarn_tl FROM bucket_totals)
              / NULLIF((SELECT grand_total FROM total_12m), 0),
        2
    ) AS yarn_share_pct,
    ROUND(
        100.0 * (SELECT greige_tl FROM bucket_totals)
              / NULLIF((SELECT grand_total FROM total_12m), 0),
        2
    ) AS greige_share_pct,
    (SELECT biggest_mover_bucket FROM biggest_mover) AS biggest_mover_bucket,
    (SELECT biggest_mover_pct    FROM biggest_mover) AS biggest_mover_pct,
    (SELECT biggest_mover_tl     FROM biggest_mover) AS biggest_mover_tl,
    (SELECT to_char(latest_complete_month_start, 'YYYY-MM') FROM purchase_bounds) AS latest_month,
    (SELECT to_char(prior_month_start,           'YYYY-MM') FROM purchase_bounds) AS prior_month,
    (SELECT grand_total FROM total_12m) AS total_12m_tl
;

COMMENT ON VIEW v_procurement_kpis IS
'M2.2.2 (re-scoped in Migration 024) — Procurement KPI strip data, raw-material
scope only (yarn / chemical / dye / greige_fabric). Operational costs are in
Cost Structure section.';


-- ─────────────────────────────────────────────────────────────────────────
-- 3) v_procurement_concentration_trend (originally Migration 017)
-- ─────────────────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS v_procurement_concentration_trend CASCADE;

CREATE VIEW v_procurement_concentration_trend AS
WITH
window_bounds AS (
    SELECT
        MAX(fatura_tarihi) AS max_date,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '23 months')::date AS min_month
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

raw_material_buckets(b) AS (
    VALUES
      ('raw_material_yarn'),
      ('raw_material_chemical'),
      ('raw_material_dye'),
      ('raw_material_greige_fabric')
),

monthly_supplier AS (
    SELECT
        DATE_TRUNC('month', p.fatura_tarihi)::date AS month,
        p.cari_hesap_aciklamasi                    AS supplier_name,
        SUM(p.net_tutar_y)::numeric                AS supplier_amount_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.business_bucket IN (SELECT b FROM raw_material_buckets)
      AND p.cari_hesap_aciklamasi IS NOT NULL
      AND p.cari_hesap_aciklamasi <> ''
      AND p.fatura_tarihi >= wb.min_month
    GROUP BY DATE_TRUNC('month', p.fatura_tarihi)::date, p.cari_hesap_aciklamasi
),

ranked AS (
    SELECT
        month, supplier_name, supplier_amount_tl,
        ROW_NUMBER() OVER (PARTITION BY month ORDER BY supplier_amount_tl DESC NULLS LAST) AS rk,
        SUM(supplier_amount_tl) OVER (PARTITION BY month) AS month_total
    FROM monthly_supplier
),

agg AS (
    SELECT
        month,
        SUM(supplier_amount_tl) FILTER (WHERE rk <= 1)  AS top_1_amount_tl,
        SUM(supplier_amount_tl) FILTER (WHERE rk <= 3)  AS top_3_amount_tl,
        SUM(supplier_amount_tl) FILTER (WHERE rk <= 10) AS top_10_amount_tl,
        MAX(month_total)                                  AS total_tl,
        COUNT(DISTINCT supplier_name)                     AS active_suppliers
    FROM ranked
    GROUP BY month
)

SELECT
    to_char(month, 'YYYY-MM') AS month,
    ROUND(100.0 * COALESCE(top_1_amount_tl, 0)  / NULLIF(total_tl, 0), 2) AS top_1_share_pct,
    ROUND(100.0 * COALESCE(top_3_amount_tl, 0)  / NULLIF(total_tl, 0), 2) AS top_3_share_pct,
    ROUND(100.0 * COALESCE(top_10_amount_tl, 0) / NULLIF(total_tl, 0), 2) AS top_10_share_pct,
    total_tl::numeric(20,2) AS total_tl,
    active_suppliers
FROM agg
ORDER BY month;

COMMENT ON VIEW v_procurement_concentration_trend IS
'M2.2.4 (re-scoped in Migration 024) — Procurement concentration trend, raw-material
scope only. Mirror of v_customer_concentration_trend.';


-- ─────────────────────────────────────────────────────────────────────────
-- 4) v_monthly_procurement_by_currency (originally Migration 018)
-- ─────────────────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS v_monthly_procurement_by_currency CASCADE;

CREATE VIEW v_monthly_procurement_by_currency AS
WITH
window_bounds AS (
    SELECT
        MAX(fatura_tarihi) AS max_date,
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '23 months')::date AS min_month
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
)

SELECT
    to_char(DATE_TRUNC('month', p.fatura_tarihi)::date, 'YYYY-MM') AS month,
    CASE
        WHEN p.para_birimi_d IN ('TRY','USD','EUR') THEN p.para_birimi_d
        ELSE 'OTHER'
    END                                  AS currency,
    COUNT(*)                             AS row_count,
    SUM(p.net_tutar_y)::numeric(20, 2)   AS amount_tl
FROM fact_purchase_lines_clean p
CROSS JOIN window_bounds wb
WHERE p.business_bucket IN (
    'raw_material_yarn',
    'raw_material_chemical',
    'raw_material_dye',
    'raw_material_greige_fabric'
)
  AND p.fatura_tarihi >= wb.min_month
  AND p.fatura_tarihi IS NOT NULL
GROUP BY 1, 2
ORDER BY 1, 2;

COMMENT ON VIEW v_monthly_procurement_by_currency IS
'M2.2.5 (re-scoped in Migration 024) — Monthly procurement currency mix,
raw-material scope only. amount_tl is invoice-date TL equivalent (net_tutar_y).';
