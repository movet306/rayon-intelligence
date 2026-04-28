-- =============================================================================
-- Migration 012 — dim_counterparty (plain VIEW)
-- =============================================================================
-- Purpose:
--   Foundation view for the Counterparty Explorer (M2.1).
--   Resolves counterparties to a canonical key + most-recent display name,
--   with summary metrics for both purchase (ALIŞ) and sales (SATIŞ) sides.
--
-- Decisions (from M2.1 audit):
--   • Plain VIEW, not materialized — premature optimization deferred to M2.2
--     if performance becomes a real issue.
--   • Canonical key uses 'tax:<vergi_numarasi>' when tax id is valid,
--     'name:<cari_hesap_aciklamasi>' otherwise.
--   • Tax-id-missing entities are GROUPED BY NAME with is_verified = FALSE.
--     ⚠️ Name-grouped entities are PROVISIONAL and may contain
--     collision risk: two unrelated parties sharing the same display name
--     would be merged. The Counterparty Explorer UI must surface this via
--     the `tax_id_missing` badge.
--   • Display name = the cari_hesap_aciklamasi from the most recent
--     (max fatura_tarihi) row for that canonical key.
--   • Full history retained — 24-month metrics computed alongside lifetime.
--
-- Read-only: this is a VIEW, not a table. No data is duplicated.
-- =============================================================================

DROP VIEW IF EXISTS dim_counterparty CASCADE;

CREATE VIEW dim_counterparty AS
WITH
-- ─────────────────────────────────────────────────────────────────────────
-- Step 1: union both fact tables into a single counterparty-row stream,
-- assigning canonical_key per row and tagging side.
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
        -- Tax id is "valid" if non-null, non-empty, and not '0'
        CASE
            WHEN vergi_numarasi IS NOT NULL
             AND TRIM(vergi_numarasi) <> ''
             AND TRIM(vergi_numarasi) <> '0'
             AND TRIM(vergi_numarasi) <> '0.0'
            THEN TRUE
            ELSE FALSE
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
        'sales'::text                      AS side,
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
            THEN TRUE
            ELSE FALSE
        END AS tax_id_valid,
        CASE
            WHEN vergi_numarasi IS NOT NULL
             AND TRIM(vergi_numarasi) <> ''
             AND TRIM(vergi_numarasi) <> '0'
             AND TRIM(vergi_numarasi) <> '0.0'
            THEN 'tax:' || TRIM(vergi_numarasi)
            ELSE 'name:' || COALESCE(TRIM(cari_hesap_aciklamasi), '<unknown>')
        END AS canonical_key
    FROM fact_sales_lines_clean
),

-- ─────────────────────────────────────────────────────────────────────────
-- Step 2: pick the latest display name per (side, canonical_key).
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
-- Step 3: name variants count (how many spellings ever seen).
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
-- Step 4: aggregate metrics — lifetime + trailing 24 months.
-- 24-month window is anchored to the latest fatura_tarihi in the dataset
-- (so it adapts as new data lands), not to CURRENT_DATE.
-- ─────────────────────────────────────────────────────────────────────────
data_horizon AS (
    SELECT MAX(fatura_tarihi) AS max_invoice_date FROM src
),
agg AS (
    SELECT
        s.side,
        s.canonical_key,
        -- Tax id surfacing: take the first non-null tax id (mode-like)
        MAX(CASE WHEN s.tax_id_valid THEN s.vergi_numarasi END) AS vergi_numarasi,
        BOOL_OR(s.tax_id_valid) AS is_verified,
        -- Counterparty type: most common per canonical_key
        (
            SELECT clean_counterparty_type
            FROM src s2
            WHERE s2.side = s.side
              AND s2.canonical_key = s.canonical_key
              AND s2.clean_counterparty_type IS NOT NULL
            GROUP BY clean_counterparty_type
            ORDER BY COUNT(*) DESC
            LIMIT 1
        ) AS counterparty_type,
        -- Lifetime metrics
        SUM(s.net_tutar_y)::numeric AS total_tl_lifetime,
        COUNT(*)::int               AS row_count_lifetime,
        MIN(s.fatura_tarihi)        AS first_seen,
        MAX(s.fatura_tarihi)        AS last_seen,
        -- 24-month metrics (anchored to data horizon, not CURRENT_DATE)
        SUM(s.net_tutar_y) FILTER (
            WHERE s.fatura_tarihi >= (
                SELECT max_invoice_date - INTERVAL '24 months' FROM data_horizon
            )
        )::numeric AS total_tl_24m,
        COUNT(*) FILTER (
            WHERE s.fatura_tarihi >= (
                SELECT max_invoice_date - INTERVAL '24 months' FROM data_horizon
            )
        )::int AS row_count_24m,
        -- Currency-broken-out lifetime totals (sum of net_tutar_d where para_birimi_d = ccy)
        SUM(s.net_tutar_d) FILTER (WHERE s.para_birimi_d = 'USD')::numeric AS total_usd_lifetime,
        SUM(s.net_tutar_d) FILTER (WHERE s.para_birimi_d = 'EUR')::numeric AS total_eur_lifetime,
        -- Classification quality
        100.0 * SUM(CASE WHEN s.review_flag THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS review_flag_pct,
        100.0 * SUM(CASE WHEN s.confidence_level = 'high' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS confidence_high_pct
    FROM src s
    GROUP BY s.side, s.canonical_key
)

-- ─────────────────────────────────────────────────────────────────────────
-- Final assembly
-- ─────────────────────────────────────────────────────────────────────────
SELECT
    a.side,
    a.canonical_key,
    a.is_verified,
    a.vergi_numarasi,
    COALESCE(ln.display_name, '<unknown>') AS display_name,
    a.counterparty_type,
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
    -- UI-friendly badges
    NOT a.is_verified AS badge_tax_id_missing,
    (a.review_flag_pct >= 10) AS badge_high_review_rate
FROM agg a
LEFT JOIN latest_name  ln ON ln.side = a.side AND ln.canonical_key = a.canonical_key
LEFT JOIN name_variants nv ON nv.side = a.side AND nv.canonical_key = a.canonical_key
;

-- ─────────────────────────────────────────────────────────────────────────
-- Comments / documentation
-- ─────────────────────────────────────────────────────────────────────────
COMMENT ON VIEW dim_counterparty IS
'Counterparty dimension for M2.1 Counterparty Explorer.
Resolves canonical key (tax:VN or name:NAME), latest display name,
and aggregate metrics. Plain VIEW (not materialized) — recomputed on
every query. WARNING: name-grouped entities (is_verified=FALSE) are
provisional and may contain collision risk: distinct legal entities
sharing the same display name would be merged. UI must surface this
via the badge_tax_id_missing flag.';

-- ─────────────────────────────────────────────────────────────────────────
-- Quick sanity check — run after migration to verify the view
-- ─────────────────────────────────────────────────────────────────────────
-- SELECT side, COUNT(*) AS counterparties,
--        SUM(CASE WHEN is_verified THEN 1 ELSE 0 END) AS verified,
--        SUM(CASE WHEN NOT is_verified THEN 1 ELSE 0 END) AS unverified
-- FROM dim_counterparty
-- GROUP BY side;
--
-- SELECT side, display_name, vergi_numarasi, total_tl_24m, row_count_24m, badge_tax_id_missing
-- FROM dim_counterparty
-- WHERE side = 'sales'
-- ORDER BY total_tl_24m DESC NULLS LAST
-- LIMIT 10;
