-- =============================================================================
-- Migration 018 — v_monthly_procurement_by_currency
-- =============================================================================
-- M2.2.5 Procurement Phase 1 — Chart 4: Currency composition mix.
--
-- For each (month, invoice currency), aggregates net_tutar_y (TL equivalent
-- of the invoice line at invoice-date FX rate, as recorded by Nebim).
--
-- Scope: cost-relevant rows only (matches the rest of Procurement Phase 1).
-- Window: 24 months rolling (the chart panel will display all rows; frontend
-- can slice if needed).
--
-- Currencies: TRY, USD, EUR are the three primary invoicing currencies.
-- Anything else (rare — typically GBP or none) is bucketed into 'OTHER' so
-- the mix-% chart still sums cleanly to 100%.
-- =============================================================================

DROP VIEW IF EXISTS v_monthly_procurement_by_currency CASCADE;

CREATE VIEW v_monthly_procurement_by_currency AS
WITH
window_bounds AS (
    SELECT
        (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '23 months')::date AS min_month
    FROM fact_purchase_lines_clean
    WHERE fatura_tarihi IS NOT NULL
),

normalized AS (
    SELECT
        DATE_TRUNC('month', p.fatura_tarihi)::date AS month,
        CASE
            WHEN p.para_birimi_d IN ('TRY', 'USD', 'EUR') THEN p.para_birimi_d
            ELSE 'OTHER'
        END AS currency,
        p.net_tutar_y::numeric AS amount_tl
    FROM fact_purchase_lines_clean p
    CROSS JOIN window_bounds wb
    WHERE p.is_cost_model_relevant = true
      AND p.fatura_tarihi >= wb.min_month
      AND p.net_tutar_y IS NOT NULL
)

SELECT
    to_char(month, 'YYYY-MM') AS month,
    currency,
    COUNT(*)::int             AS row_count,
    SUM(amount_tl)::numeric(20,2) AS amount_tl
FROM normalized
GROUP BY month, currency
ORDER BY month, currency;


COMMENT ON VIEW v_monthly_procurement_by_currency IS
'M2.2.5 — Procurement Phase 1 Chart 4: monthly TL-equivalent spend grouped
by invoice currency (TRY/USD/EUR/OTHER), 24m rolling window, cost-relevant
scope only. Source for the currency composition mix-% chart.';
