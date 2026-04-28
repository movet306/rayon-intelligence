-- =============================================================================
-- Migration 015 — Enrich v_top_suppliers_overall
-- =============================================================================
-- M2.2.1 Procurement Phase 1 — Top Suppliers table enrichment.
--
-- Adds to the existing view:
--   - share_pct: supplier's share of total cost-relevant procurement (12m)
--   - trend_direction: '▲' / '▼' / '–' based on H2 (last 6m) vs H1 (prior 6m)
--   - vergi_numarasi: tax id if available (for badge logic)
--   - is_verified: tax id valid?
--   - name_variants_count: drift indicator
--
-- Strategy:
--   - Keep grouping by cari_hesap_aciklamasi (display name) for now to match
--     existing semantics. Canonical-key consolidation is a separate concern,
--     handled at the Counterparty Explorer layer (M2.2.2 drawer wiring).
--   - Compute trend in two halves of the 12m window via FILTER aggregates
--   - Compute share_pct against the 12m total of cost-relevant rows
-- =============================================================================

DROP VIEW IF EXISTS v_top_suppliers_overall CASCADE;

CREATE VIEW v_top_suppliers_overall AS
WITH window_bounds AS (
    SELECT
        MAX(fatura_tarihi) AS max_date,
        (MAX(fatura_tarihi) - INTERVAL '1 year')::date  AS min_date,
        (MAX(fatura_tarihi) - INTERVAL '6 months')::date AS midpoint
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),
total_cost_relevant_12m AS (
    SELECT SUM(net_tutar_y)::numeric AS grand_total
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.is_cost_model_relevant = true
      AND p.fatura_tarihi >= wb.min_date
),
supplier_agg AS (
    SELECT
        p.cari_hesap_aciklamasi AS supplier_name,
        COUNT(*) AS row_count,
        COUNT(DISTINCT p.business_bucket) AS bucket_count,
        SUM(p.net_tutar_y)::numeric(20,2) AS amount_tl,
        SUM(CASE WHEN p.para_birimi_d = 'USD' THEN p.net_tutar_d ELSE 0 END)::numeric(20,2) AS amount_usd,
        SUM(CASE WHEN p.para_birimi_d = 'EUR' THEN p.net_tutar_d ELSE 0 END)::numeric(20,2) AS amount_eur,
        MIN(p.fatura_tarihi) AS first_invoice_date,
        MAX(p.fatura_tarihi) AS last_invoice_date,
        -- Trend halves: H2 (last 6m) and H1 (prior 6m)
        SUM(p.net_tutar_y) FILTER (WHERE p.fatura_tarihi >= wb.midpoint)::numeric AS amount_tl_h2,
        SUM(p.net_tutar_y) FILTER (WHERE p.fatura_tarihi <  wb.midpoint)::numeric AS amount_tl_h1,
        -- Tax id: latest non-empty value (for badge logic)
        MAX(CASE
            WHEN p.vergi_numarasi IS NOT NULL
             AND TRIM(p.vergi_numarasi) <> ''
             AND TRIM(p.vergi_numarasi) <> '0'
             AND TRIM(p.vergi_numarasi) <> '0.0'
            THEN p.vergi_numarasi
        END) AS vergi_numarasi,
        BOOL_OR(
            p.vergi_numarasi IS NOT NULL
             AND TRIM(p.vergi_numarasi) <> ''
             AND TRIM(p.vergi_numarasi) <> '0'
             AND TRIM(p.vergi_numarasi) <> '0.0'
        ) AS is_verified
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.is_cost_model_relevant = true
      AND p.cari_hesap_aciklamasi IS NOT NULL
      AND p.cari_hesap_aciklamasi <> ''
      AND p.fatura_tarihi >= wb.min_date
    GROUP BY p.cari_hesap_aciklamasi
),
-- Name drift: how many distinct display names share the same vergi_numarasi
-- (within the same supplier_name group, this number is always >=1; it's larger
-- only if the same tax id appears under multiple display names — which here
-- means *other* rows of the same legal entity exist under different spellings)
name_variants AS (
    SELECT
        p.vergi_numarasi,
        COUNT(DISTINCT p.cari_hesap_aciklamasi) AS variants_count
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.is_cost_model_relevant = true
      AND p.fatura_tarihi >= wb.min_date
      AND p.vergi_numarasi IS NOT NULL
      AND TRIM(p.vergi_numarasi) <> ''
      AND TRIM(p.vergi_numarasi) <> '0'
      AND TRIM(p.vergi_numarasi) <> '0.0'
    GROUP BY p.vergi_numarasi
)
SELECT
    sa.supplier_name,
    sa.row_count,
    sa.bucket_count,
    sa.amount_tl,
    sa.amount_usd,
    sa.amount_eur,
    sa.first_invoice_date,
    sa.last_invoice_date,
    -- top_bucket (preserved from original view)
    (
        SELECT p2.business_bucket
        FROM fact_purchase_lines_clean p2
        CROSS JOIN window_bounds wb
        WHERE p2.cari_hesap_aciklamasi = sa.supplier_name
          AND p2.is_cost_model_relevant = true
          AND p2.fatura_tarihi >= wb.min_date
        GROUP BY p2.business_bucket
        ORDER BY SUM(p2.net_tutar_y) DESC NULLS LAST
        LIMIT 1
    ) AS top_bucket,
    -- NEW: share_pct of total cost-relevant procurement (12m)
    ROUND(
        100.0 * sa.amount_tl / NULLIF((SELECT grand_total FROM total_cost_relevant_12m), 0),
        2
    ) AS share_pct,
    -- NEW: trend_direction based on H2 vs H1 spend
    CASE
        WHEN COALESCE(sa.amount_tl_h2, 0) = 0 AND COALESCE(sa.amount_tl_h1, 0) = 0 THEN '–'
        WHEN COALESCE(sa.amount_tl_h1, 0) = 0 AND sa.amount_tl_h2 > 0                THEN '▲'
        WHEN COALESCE(sa.amount_tl_h2, 0) = 0 AND sa.amount_tl_h1 > 0                THEN '▼'
        WHEN sa.amount_tl_h2 >= sa.amount_tl_h1 * 1.10 THEN '▲'   -- +10% or more
        WHEN sa.amount_tl_h2 <= sa.amount_tl_h1 * 0.90 THEN '▼'   -- -10% or more
        ELSE '–'
    END AS trend_direction,
    -- NEW: trend numerics (for tooltips later)
    sa.amount_tl_h1,
    sa.amount_tl_h2,
    -- NEW: badge inputs
    sa.vergi_numarasi,
    sa.is_verified,
    COALESCE(nv.variants_count, 1) AS name_variants_count
FROM supplier_agg sa
LEFT JOIN name_variants nv
       ON nv.vergi_numarasi = sa.vergi_numarasi;


COMMENT ON VIEW v_top_suppliers_overall IS
'Top suppliers — enriched (M2.2.1 / Migration 015). Adds share_pct, trend_direction,
vergi_numarasi, is_verified, and name_variants_count to the original 12m-window
view. Trend is H2 (last 6m) vs H1 (prior 6m) with a ±10% threshold for ▲/▼.
Grouping is still by cari_hesap_aciklamasi (display name); canonical-key
consolidation lives in dim_counterparty_mv and is wired in at row-click time
via the Counterparty Explorer drawer (M2.2.2).';
