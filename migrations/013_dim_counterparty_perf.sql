-- =============================================================================
-- Migration 013 — Refactor dim_counterparty for performance
-- =============================================================================
-- Issue:
--   Original v012 uses a correlated subquery for counterparty_type:
--     SELECT clean_counterparty_type FROM src s2
--     WHERE s2.side = s.side AND s2.canonical_key = s.canonical_key
--     ORDER BY COUNT(*) DESC LIMIT 1
--   This is N+1: ~3,300 counterparties × subquery = 24 seconds for list endpoint.
--
-- Fix:
--   Replace correlated subquery with a CTE that pre-aggregates the modal
--   counterparty_type per (side, canonical_key) using ROW_NUMBER window function.
--
-- Decision: kept as plain VIEW (CE-NS-3 honored). If still slow after this,
-- promote to MATERIALIZED VIEW in M2.2.
-- =============================================================================

DROP VIEW IF EXISTS dim_counterparty CASCADE;

CREATE VIEW dim_counterparty AS
WITH
-- ─────────────────────────────────────────────────────────────────────────
-- Step 1: union both fact tables, assign canonical_key per row.
-- ─────────────────────────────────────────────────────────────────────────
src AS (
    SELECT
        'purchase'::text                  AS side,
        fatura_tarihi,
        net_tutar_y,
        para_birimi_d,
        net_tutar_d,
        cari_hesap_aciklamasi,
        vergi_numarasi,
        clean_counterparty_type,
        review_flag,
        confidence_level,
        CASE
            WHEN vergi_numarasi IS NOT NULL
             AND TRIM(vergi_numarasi) <> ''
             AND TRIM(vergi_numarasi) <> '0'
             AND TRIM(vergi_numarasi) <> '0.0'
            THEN TRUE ELSE FALSE
        END AS tax_id_valid,
        CASE
            WHEN vergi_numarasi IS NOT NULL
             AND TRIM(vergi_numarasi) <> ''
             AND TRIM(vergi_numarasi) <> '0'
             AND TRIM(vergi_numarasi) <> '0.0'
            THEN 'tax:' || TRIM(vergi_numarasi)
            ELSE 'name:' || COALESCE(TRIM(cari_hesap_aciklamasi), '<unknown>')
        END AS canonical_key
    FROM fact_purchase_lines_clean

    UNION ALL

    SELECT
        'sales'::text,
        fatura_tarihi,
        net_tutar_y,
        para_birimi_d,
        net_tutar_d,
        cari_hesap_aciklamasi,
        vergi_numarasi,
        clean_counterparty_type,
        review_flag,
        confidence_level,
        CASE
            WHEN vergi_numarasi IS NOT NULL
             AND TRIM(vergi_numarasi) <> ''
             AND TRIM(vergi_numarasi) <> '0'
             AND TRIM(vergi_numarasi) <> '0.0'
            THEN TRUE ELSE FALSE
        END,
        CASE
            WHEN vergi_numarasi IS NOT NULL
             AND TRIM(vergi_numarasi) <> ''
             AND TRIM(vergi_numarasi) <> '0'
             AND TRIM(vergi_numarasi) <> '0.0'
            THEN 'tax:' || TRIM(vergi_numarasi)
            ELSE 'name:' || COALESCE(TRIM(cari_hesap_aciklamasi), '<unknown>')
        END
    FROM fact_sales_lines_clean
),

-- ─────────────────────────────────────────────────────────────────────────
-- Step 2: latest display name per (side, canonical_key) — DISTINCT ON
-- ─────────────────────────────────────────────────────────────────────────
latest_name AS (
    SELECT DISTINCT ON (side, canonical_key)
        side,
        canonical_key,
        cari_hesap_aciklamasi AS display_name
    FROM src
    WHERE cari_hesap_aciklamasi IS NOT NULL
      AND TRIM(cari_hesap_aciklamasi) <> ''
    ORDER BY side, canonical_key, fatura_tarihi DESC NULLS LAST
),

-- ─────────────────────────────────────────────────────────────────────────
-- Step 3: name variants count
-- ─────────────────────────────────────────────────────────────────────────
name_variants AS (
    SELECT
        side,
        canonical_key,
        COUNT(DISTINCT cari_hesap_aciklamasi) AS name_variants_count
    FROM src
    WHERE cari_hesap_aciklamasi IS NOT NULL
      AND TRIM(cari_hesap_aciklamasi) <> ''
    GROUP BY side, canonical_key
),

-- ─────────────────────────────────────────────────────────────────────────
-- Step 4: PRE-AGGREGATE counterparty_type as a window function (PERFORMANCE FIX)
-- Replaces the slow correlated subquery from v012.
-- ─────────────────────────────────────────────────────────────────────────
type_counts AS (
    SELECT
        side,
        canonical_key,
        clean_counterparty_type,
        COUNT(*) AS n
    FROM src
    WHERE clean_counterparty_type IS NOT NULL
    GROUP BY side, canonical_key, clean_counterparty_type
),
modal_type AS (
    SELECT DISTINCT ON (side, canonical_key)
        side,
        canonical_key,
        clean_counterparty_type AS counterparty_type
    FROM type_counts
    ORDER BY side, canonical_key, n DESC
),

-- ─────────────────────────────────────────────────────────────────────────
-- Step 5: data horizon for trailing 24-month window
-- ─────────────────────────────────────────────────────────────────────────
data_horizon AS (
    SELECT MAX(fatura_tarihi) AS max_invoice_date FROM src
),

-- ─────────────────────────────────────────────────────────────────────────
-- Step 6: aggregate metrics per counterparty
-- ─────────────────────────────────────────────────────────────────────────
agg AS (
    SELECT
        s.side,
        s.canonical_key,
        MAX(CASE WHEN s.tax_id_valid THEN s.vergi_numarasi END) AS vergi_numarasi,
        BOOL_OR(s.tax_id_valid) AS is_verified,
        SUM(s.net_tutar_y)::numeric AS total_tl_lifetime,
        COUNT(*)::int               AS row_count_lifetime,
        MIN(s.fatura_tarihi)        AS first_seen,
        MAX(s.fatura_tarihi)        AS last_seen,
        SUM(s.net_tutar_y) FILTER (
            WHERE s.fatura_tarihi >= (SELECT max_invoice_date - INTERVAL '24 months' FROM data_horizon)
        )::numeric AS total_tl_24m,
        COUNT(*) FILTER (
            WHERE s.fatura_tarihi >= (SELECT max_invoice_date - INTERVAL '24 months' FROM data_horizon)
        )::int AS row_count_24m,
        SUM(s.net_tutar_d) FILTER (WHERE s.para_birimi_d = 'USD')::numeric AS total_usd_lifetime,
        SUM(s.net_tutar_d) FILTER (WHERE s.para_birimi_d = 'EUR')::numeric AS total_eur_lifetime,
        100.0 * SUM(CASE WHEN s.review_flag THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS review_flag_pct,
        100.0 * SUM(CASE WHEN s.confidence_level = 'high' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS confidence_high_pct
    FROM src s
    GROUP BY s.side, s.canonical_key
)

-- ─────────────────────────────────────────────────────────────────────────
-- Final assembly — joins instead of correlated subqueries
-- ─────────────────────────────────────────────────────────────────────────
SELECT
    a.side,
    a.canonical_key,
    a.is_verified,
    a.vergi_numarasi,
    COALESCE(ln.display_name, '<unknown>') AS display_name,
    mt.counterparty_type,
    a.total_tl_lifetime,
    a.total_tl_24m,
    a.total_usd_lifetime,
    a.total_eur_lifetime,
    a.row_count_lifetime,
    a.row_count_24m,
    a.first_seen,
    a.last_seen,
    COALESCE(nv.name_variants_count, 1) AS name_variants_count,
    a.review_flag_pct,
    a.confidence_high_pct,
    NOT a.is_verified AS badge_tax_id_missing,
    (a.review_flag_pct >= 10) AS badge_high_review_rate
FROM agg a
LEFT JOIN latest_name  ln ON ln.side = a.side AND ln.canonical_key = a.canonical_key
LEFT JOIN name_variants nv ON nv.side = a.side AND nv.canonical_key = a.canonical_key
LEFT JOIN modal_type   mt ON mt.side = a.side AND mt.canonical_key = a.canonical_key
;

COMMENT ON VIEW dim_counterparty IS
'Counterparty dimension for M2.1 Counterparty Explorer. v013: refactored
counterparty_type to use a CTE+window function instead of correlated subquery
(was 24s, target <2s). Plain VIEW per CE-NS-3 decision; promote to MATERIALIZED
VIEW only if performance still inadequate. Name-grouped entities (is_verified=
FALSE) are PROVISIONAL — distinct legal entities sharing the same display name
would be merged. UI surfaces this via badge_tax_id_missing flag.';
