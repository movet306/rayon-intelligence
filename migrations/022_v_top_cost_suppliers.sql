-- =============================================================================
-- Migration 022 — v_top_cost_suppliers_overall
-- =============================================================================
-- M2.4.1 Cost Structure Phase 1 — analogous to v_top_suppliers_overall
-- (Procurement) but scoped to the 6 cost buckets:
--   utilities, maintenance_factory, packaging, factory_overhead,
--   outsourced_processing, logistics_distribution
--
-- New compared to Procurement enrichment:
--   - secondary_bucket : 2nd largest bucket for this supplier (when supplier
--                        spans multiple cost buckets)
--   - secondary_bucket_share_pct : its TL share within the supplier's spend
--   - top_bucket_share_pct       : top bucket's TL share within the supplier's spend
--
-- Other enrichment columns mirror Migration 015:
--   share_pct, trend_direction, amount_tl_h1/h2, vergi_numarasi, is_verified,
--   name_variants_count.
-- =============================================================================

DROP VIEW IF EXISTS v_top_cost_suppliers_overall CASCADE;

CREATE VIEW v_top_cost_suppliers_overall AS
WITH
window_bounds AS (
    SELECT
        MAX(fatura_tarihi)                                AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '12 months')::date AS min_date,
        (MAX(fatura_tarihi) - INTERVAL '6 months')::date  AS h2_start
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

-- Per-supplier per-bucket totals (12m, cost-bucket scope)
supplier_bucket AS (
    SELECT
        p.cari_hesap_aciklamasi                                        AS supplier_name,
        p.business_bucket                                              AS bucket,
        SUM(p.net_tutar_y)::numeric                                    AS bucket_amount_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.business_bucket IN (SELECT b FROM cost_buckets)
      AND p.cari_hesap_aciklamasi IS NOT NULL
      AND p.cari_hesap_aciklamasi <> ''
      AND p.fatura_tarihi >= wb.min_date
    GROUP BY 1, 2
),

-- Per-supplier overall (12m totals + currency split + H1/H2)
supplier_total AS (
    SELECT
        p.cari_hesap_aciklamasi                                                            AS supplier_name,
        COUNT(*)                                                                           AS row_count,
        COUNT(DISTINCT p.business_bucket)                                                  AS bucket_count,
        SUM(p.net_tutar_y)::numeric(20, 2)                                                 AS amount_tl,
        SUM(CASE WHEN p.para_birimi_d = 'USD' THEN p.net_tutar_d ELSE 0 END)::numeric(20,2) AS amount_usd,
        SUM(CASE WHEN p.para_birimi_d = 'EUR' THEN p.net_tutar_d ELSE 0 END)::numeric(20,2) AS amount_eur,
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
    WHERE p.business_bucket IN (SELECT b FROM cost_buckets)
      AND p.cari_hesap_aciklamasi IS NOT NULL
      AND p.cari_hesap_aciklamasi <> ''
      AND p.fatura_tarihi >= wb.min_date
    GROUP BY p.cari_hesap_aciklamasi
),

-- Rank buckets per supplier
ranked_buckets AS (
    SELECT
        supplier_name,
        bucket,
        bucket_amount_tl,
        ROW_NUMBER() OVER (PARTITION BY supplier_name ORDER BY bucket_amount_tl DESC) AS rk,
        SUM(bucket_amount_tl) OVER (PARTITION BY supplier_name) AS supplier_total_tl
    FROM supplier_bucket
),

top_bucket AS (
    SELECT
        supplier_name,
        bucket AS top_bucket,
        ROUND(100.0 * bucket_amount_tl / NULLIF(supplier_total_tl, 0), 1)::numeric(6,1) AS top_bucket_share_pct
    FROM ranked_buckets
    WHERE rk = 1
),

second_bucket AS (
    SELECT
        supplier_name,
        bucket AS secondary_bucket,
        ROUND(100.0 * bucket_amount_tl / NULLIF(supplier_total_tl, 0), 1)::numeric(6,1) AS secondary_bucket_share_pct
    FROM ranked_buckets
    WHERE rk = 2
),

grand_total AS (
    SELECT SUM(amount_tl)::numeric AS total_tl
    FROM supplier_total
),

-- Counterparty enrichment join (purchase side)
cp_lookup AS (
    SELECT DISTINCT ON (display_name)
        display_name,
        vergi_numarasi,
        is_verified,
        name_variants_count
    FROM dim_counterparty_mv
    WHERE side = 'purchase'
    ORDER BY display_name, total_tl_24m DESC NULLS LAST
)

SELECT
    st.supplier_name,
    st.row_count,
    st.bucket_count,
    st.amount_tl,
    st.amount_usd,
    st.amount_eur,
    tb.top_bucket,
    tb.top_bucket_share_pct,
    sb.secondary_bucket,
    sb.secondary_bucket_share_pct,
    st.first_invoice_date,
    st.last_invoice_date,
    -- Enrichment columns (mirror Migration 015 + secondary bucket)
    ROUND(
        100.0 * st.amount_tl / NULLIF((SELECT total_tl FROM grand_total), 0),
        2
    )::numeric(6, 2) AS share_pct,
    CASE
        WHEN st.amount_tl_h1 IS NULL OR st.amount_tl_h1 = 0 THEN '–'
        WHEN st.amount_tl_h2 / st.amount_tl_h1 >= 1.10 THEN '▲'
        WHEN st.amount_tl_h2 / st.amount_tl_h1 <= 0.90 THEN '▼'
        ELSE '–'
    END                                  AS trend_direction,
    st.amount_tl_h1,
    st.amount_tl_h2,
    cp.vergi_numarasi,
    COALESCE(cp.is_verified, FALSE)      AS is_verified,
    COALESCE(cp.name_variants_count, 1)  AS name_variants_count
FROM supplier_total st
LEFT JOIN top_bucket    tb ON tb.supplier_name = st.supplier_name
LEFT JOIN second_bucket sb ON sb.supplier_name = st.supplier_name
LEFT JOIN cp_lookup     cp ON cp.display_name  = st.supplier_name;


COMMENT ON VIEW v_top_cost_suppliers_overall IS
'M2.4.1 — Top suppliers in cost-structure scope (utilities, maintenance,
packaging, factory_overhead, outsourced_processing, logistics_distribution).
12m rolling. Adds top_bucket / secondary_bucket with their share_pct within
the supplier total, plus standard enrichment (share, trend, h1/h2, taxid,
is_verified, name_variants_count).';
