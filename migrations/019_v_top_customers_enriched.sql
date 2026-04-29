-- =============================================================================
-- Migration 019 — v_top_customers_overall enrichment
-- =============================================================================
-- M2.3.1 Revenue Phase 1 — mirror of Migration 015 for the customer side.
--
-- Adds the following columns to v_top_customers_overall:
--   - share_pct           : customer's share of 12m core-revenue grand total
--   - trend_direction     : '▲' / '▼' / '–' (last 6m vs prior 6m, ±10% threshold)
--   - amount_tl_h1, h2    : H1/H2 totals for transparency
--   - vergi_numarasi      : tax id from dim_counterparty (sales side)
--   - is_verified         : has a verified tax id (not null/empty/zero)
--   - name_variants_count : how many display-name variants share this canonical
--
-- Scope: core_product_sales + outsourced_service_revenue (yarn_resale excluded)
-- Window: 12 months rolling (matches Migration 015 for symmetry)
-- =============================================================================

DROP VIEW IF EXISTS v_top_customers_overall CASCADE;

CREATE VIEW v_top_customers_overall AS
WITH
window_bounds AS (
    SELECT
        MAX(fatura_tarihi)                                AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '12 months')::date AS min_date,
        (MAX(fatura_tarihi) - INTERVAL '6 months')::date  AS h2_start
    FROM fact_sales_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

base AS (
    SELECT
        s.cari_hesap_aciklamasi                                                            AS customer_name,
        COUNT(*)                                                                           AS row_count,
        COUNT(DISTINCT s.business_bucket)                                                  AS bucket_count,
        SUM(s.net_tutar_y)::numeric(20, 2)                                                 AS amount_tl,
        SUM(CASE WHEN s.para_birimi_d = 'USD' THEN s.net_tutar_d ELSE 0 END)::numeric(20,2) AS amount_usd,
        SUM(CASE WHEN s.para_birimi_d = 'EUR' THEN s.net_tutar_d ELSE 0 END)::numeric(20,2) AS amount_eur,
        COUNT(*) FILTER (WHERE s.para_birimi_d = 'USD')                                    AS rows_usd,
        COUNT(*) FILTER (WHERE s.para_birimi_d = 'TRY')                                    AS rows_try,
        COUNT(*) FILTER (WHERE s.para_birimi_d = 'EUR')                                    AS rows_eur,
        -- H1 (older 6m: from min_date to h2_start)
        SUM(s.net_tutar_y) FILTER (
            WHERE s.fatura_tarihi >= (SELECT min_date FROM window_bounds)
              AND s.fatura_tarihi <  (SELECT h2_start FROM window_bounds)
        )::numeric(20, 2) AS amount_tl_h1,
        -- H2 (most recent 6m: from h2_start to max_date)
        SUM(s.net_tutar_y) FILTER (
            WHERE s.fatura_tarihi >= (SELECT h2_start FROM window_bounds)
        )::numeric(20, 2) AS amount_tl_h2,
        MIN(s.fatura_tarihi)                                                               AS first_invoice_date,
        MAX(s.fatura_tarihi)                                                               AS last_invoice_date
    FROM fact_sales_lines_clean s
    CROSS JOIN window_bounds wb
    WHERE s.business_bucket IN ('core_product_sales', 'outsourced_service_revenue')
      AND COALESCE(s.subtype, '') <> 'yarn_resale'
      AND s.cari_hesap_aciklamasi IS NOT NULL
      AND s.cari_hesap_aciklamasi <> ''
      AND s.fatura_tarihi >= wb.min_date
    GROUP BY s.cari_hesap_aciklamasi
),

grand_total AS (
    SELECT SUM(amount_tl)::numeric AS total_tl
    FROM base
),

-- One row per (customer_name) with the canonical counterparty fields, if any
-- match exists in dim_counterparty_mv on the sales side. We join by display_name
-- because base aggregates on cari_hesap_aciklamasi (raw display name).
cp_lookup AS (
    SELECT DISTINCT ON (display_name)
        display_name,
        vergi_numarasi,
        is_verified,
        name_variants_count
    FROM dim_counterparty_mv
    WHERE side = 'sales'
    ORDER BY display_name, total_tl_24m DESC NULLS LAST
)

SELECT
    b.customer_name,
    b.row_count,
    b.bucket_count,
    b.amount_tl,
    b.amount_usd,
    b.amount_eur,
    b.rows_usd,
    b.rows_try,
    b.rows_eur,
    b.first_invoice_date,
    b.last_invoice_date,
    -- Enrichment columns (M2.3.1)
    ROUND(
        100.0 * b.amount_tl / NULLIF((SELECT total_tl FROM grand_total), 0),
        2
    )::numeric(6, 2) AS share_pct,
    CASE
        WHEN b.amount_tl_h1 IS NULL OR b.amount_tl_h1 = 0 THEN '–'
        WHEN b.amount_tl_h2 / b.amount_tl_h1 >= 1.10 THEN '▲'
        WHEN b.amount_tl_h2 / b.amount_tl_h1 <= 0.90 THEN '▼'
        ELSE '–'
    END                                  AS trend_direction,
    b.amount_tl_h1,
    b.amount_tl_h2,
    cp.vergi_numarasi,
    COALESCE(cp.is_verified, FALSE)      AS is_verified,
    COALESCE(cp.name_variants_count, 1)  AS name_variants_count
FROM base b
LEFT JOIN cp_lookup cp ON cp.display_name = b.customer_name;


COMMENT ON VIEW v_top_customers_overall IS
'M2.3.1 — Customers overall totals (last 12 months, core revenue only, yarn_resale
excluded). Enriched with share_pct, trend_direction (▲/▼/–, ±10% threshold on
H2 vs H1), and dim_counterparty fields (vergi_numarasi, is_verified,
name_variants_count) joined by display_name on the sales side.';
