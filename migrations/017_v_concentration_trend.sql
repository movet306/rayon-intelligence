-- =============================================================================
-- Migration 017 — v_procurement_concentration_trend
-- =============================================================================
-- M2.2.4 Procurement Phase 1 — Chart 3: Supplier concentration trend.
--
-- For each month in the trailing 24-month window, computes:
--   - top_1_share_pct  : largest supplier's share of that month's spend
--   - top_3_share_pct  : sum of top 3 suppliers' share
--   - top_10_share_pct : sum of top 10 suppliers' share
--   - total_tl         : month total (cost-relevant)
--   - active_suppliers : distinct supplier count this month
--
-- Window: 24 months rolling (matches the absolute TL chart).
-- Scope: cost-relevant rows only.
-- =============================================================================

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

monthly_supplier AS (
    SELECT
        DATE_TRUNC('month', p.fatura_tarihi)::date AS month,
        p.cari_hesap_aciklamasi AS supplier_name,
        SUM(p.net_tutar_y)::numeric AS supplier_amount_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.is_cost_model_relevant = true
      AND p.cari_hesap_aciklamasi IS NOT NULL
      AND p.cari_hesap_aciklamasi <> ''
      AND p.fatura_tarihi >= wb.min_month
    GROUP BY DATE_TRUNC('month', p.fatura_tarihi)::date, p.cari_hesap_aciklamasi
),

ranked AS (
    SELECT
        month,
        supplier_name,
        supplier_amount_tl,
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
        MAX(month_total)                                 AS total_tl,
        COUNT(DISTINCT supplier_name)                    AS active_suppliers
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
'M2.2.4 — Procurement Phase 1 Chart 3: monthly top-1/top-3/top-10 supplier
share, 24m rolling window, cost-relevant scope only. Source for the
concentration trend chart and the future M2.6 concentration drilldown.';
