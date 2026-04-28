-- =============================================================================
-- Migration 014 — Performance: MV for list, indexes for detail
-- =============================================================================
-- Issue:
--   Even after v013 query refactor, list endpoint still ~5s and detail endpoint
--   slow. The detail endpoint runs 9 separate queries against fact tables filtered
--   by counterparty (vergi_numarasi or cari_hesap_aciklamasi) without indexes.
--
-- Decision (revised CE-NS-3):
--   Plain VIEW was the right initial choice — but with usage data showing 5s+
--   latency, this is now evidence-based optimization, not premature.
--
-- Changes:
--   1. dim_counterparty → MATERIALIZED VIEW dim_counterparty_mv
--      (Keep dim_counterparty as a thin wrapper for backward compatibility)
--   2. Add indexes on fact tables for counterparty filter columns
--   3. Add unique index on MV for future REFRESH CONCURRENTLY support
--
-- Refresh strategy:
--   Manual refresh via `REFRESH MATERIALIZED VIEW dim_counterparty_mv`.
--   Add this step to GitHub Actions daily workflow after build_price_metrics.
--
-- Expected:
--   - List endpoint: 5s → <200ms
--   - Detail endpoint: variable but each query <100ms (was multi-second)
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────
-- Step 1: Drop the plain view (will recreate as MV)
-- ─────────────────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS dim_counterparty CASCADE;
DROP MATERIALIZED VIEW IF EXISTS dim_counterparty_mv CASCADE;


-- ─────────────────────────────────────────────────────────────────────────
-- Step 2: Create the materialized view (same logic as v013)
-- ─────────────────────────────────────────────────────────────────────────
CREATE MATERIALIZED VIEW dim_counterparty_mv AS
WITH src AS (
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
latest_name AS (
    SELECT DISTINCT ON (side, canonical_key)
        side, canonical_key,
        cari_hesap_aciklamasi AS display_name
    FROM src
    WHERE cari_hesap_aciklamasi IS NOT NULL AND TRIM(cari_hesap_aciklamasi) <> ''
    ORDER BY side, canonical_key, fatura_tarihi DESC NULLS LAST
),
name_variants AS (
    SELECT side, canonical_key,
           COUNT(DISTINCT cari_hesap_aciklamasi) AS name_variants_count
    FROM src
    WHERE cari_hesap_aciklamasi IS NOT NULL AND TRIM(cari_hesap_aciklamasi) <> ''
    GROUP BY side, canonical_key
),
type_counts AS (
    SELECT side, canonical_key, clean_counterparty_type, COUNT(*) AS n
    FROM src
    WHERE clean_counterparty_type IS NOT NULL
    GROUP BY side, canonical_key, clean_counterparty_type
),
modal_type AS (
    SELECT DISTINCT ON (side, canonical_key)
        side, canonical_key, clean_counterparty_type AS counterparty_type
    FROM type_counts
    ORDER BY side, canonical_key, n DESC
),
data_horizon AS (
    SELECT MAX(fatura_tarihi) AS max_invoice_date FROM src
),
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


-- ─────────────────────────────────────────────────────────────────────────
-- Step 3: Indexes on the MV
-- ─────────────────────────────────────────────────────────────────────────
-- Unique index on (side, canonical_key) — required for REFRESH CONCURRENTLY
CREATE UNIQUE INDEX idx_dim_cp_mv_pk
    ON dim_counterparty_mv (side, canonical_key);

-- Sorting index for list endpoint default ordering
CREATE INDEX idx_dim_cp_mv_24m_tl
    ON dim_counterparty_mv (side, total_tl_24m DESC NULLS LAST);

-- Search support (lowercased name + tax id)
CREATE INDEX idx_dim_cp_mv_name
    ON dim_counterparty_mv (side, lower(display_name) text_pattern_ops);
CREATE INDEX idx_dim_cp_mv_tax
    ON dim_counterparty_mv (side, vergi_numarasi text_pattern_ops);


-- ─────────────────────────────────────────────────────────────────────────
-- Step 4: Backward-compat wrapper (so existing code using dim_counterparty works)
-- ─────────────────────────────────────────────────────────────────────────
CREATE VIEW dim_counterparty AS SELECT * FROM dim_counterparty_mv;


-- ─────────────────────────────────────────────────────────────────────────
-- Step 5: Indexes on fact tables for detail endpoint speedup
-- ─────────────────────────────────────────────────────────────────────────
-- Detail endpoint filters: WHERE vergi_numarasi = X OR cari_hesap_aciklamasi = X
-- and groups/orders by fatura_tarihi.

-- Purchase side
CREATE INDEX IF NOT EXISTS idx_fact_purch_vn_date
    ON fact_purchase_lines_clean (vergi_numarasi, fatura_tarihi);

CREATE INDEX IF NOT EXISTS idx_fact_purch_cariname_date
    ON fact_purchase_lines_clean (cari_hesap_aciklamasi, fatura_tarihi);

-- Sales side
CREATE INDEX IF NOT EXISTS idx_fact_sales_vn_date
    ON fact_sales_lines_clean (vergi_numarasi, fatura_tarihi);

CREATE INDEX IF NOT EXISTS idx_fact_sales_cariname_date
    ON fact_sales_lines_clean (cari_hesap_aciklamasi, fatura_tarihi);


-- ─────────────────────────────────────────────────────────────────────────
-- Step 6: Comments / documentation
-- ─────────────────────────────────────────────────────────────────────────
COMMENT ON MATERIALIZED VIEW dim_counterparty_mv IS
'Counterparty dimension — MATERIALIZED. v014 promoted from plain VIEW after
usage data showed 5s+ latency. Refresh manually or via daily workflow:
REFRESH MATERIALIZED VIEW dim_counterparty_mv;
Use REFRESH MATERIALIZED VIEW CONCURRENTLY dim_counterparty_mv when
non-blocking refresh is needed (idx_dim_cp_mv_pk supports this).';

COMMENT ON VIEW dim_counterparty IS
'Backward-compatibility wrapper around dim_counterparty_mv. Existing code
that references dim_counterparty continues to work unchanged.';


-- ─────────────────────────────────────────────────────────────────────────
-- Step 7: Sanity check (uncomment to test after applying)
-- ─────────────────────────────────────────────────────────────────────────
-- SELECT side, COUNT(*) FROM dim_counterparty_mv GROUP BY side;
-- EXPLAIN ANALYZE SELECT * FROM dim_counterparty
--   WHERE side = 'purchase' ORDER BY total_tl_24m DESC NULLS LAST LIMIT 50;
