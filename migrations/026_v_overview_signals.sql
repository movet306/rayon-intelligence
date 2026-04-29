-- =============================================================================
-- Migration 026 — v_overview_signals
-- =============================================================================
-- M2.5.1 Overview Phase 1 — top signals strip data source.
--
-- Returns 4 fixed slots (ordered by display_order). Each slot is one signal
-- with: severity ('critical'/'warning'/'ok'/'info'), title, metric_text,
-- why_text. Empty slots return severity='ok' and a "stable" message so the
-- frontend always renders 4 cards.
--
-- Rule-based thresholds:
--
--   Slot 1 — Customer concentration:
--     critical : top_3_share_delta_pp >= +5 OR top_3_share_latest >= 40
--     warning  : top_3_share_delta_pp >= +2 OR top_3_share_latest >= 33
--     ok       : otherwise
--     why      : "Driven by one customer surge" if top_1 latest >= 25%
--                else "Concentration shifted upward" if delta >= +2
--                else "Within normal range"
--
--   Slot 2 — Procurement concentration:
--     warning  : top_3_supplier_share_pct >= 40
--     ok       : otherwise
--     why      : "Greige + yarn remain dominant" if those are top 2 buckets
--                else "Concentrated supplier base"
--                else "Healthy supplier diversification"
--
--   Slot 3 — Contra revenue:
--     critical : contra_share_pct >= 10
--     warning  : contra_share_pct >= 5
--     ok       : otherwise
--     why      : "Above watch threshold (5%)" or "Quality/return signal"
--                else "Within normal range"
--
--   Slot 4 — Margin trend:
--     warning  : cost_revenue_ratio_delta_pp >= +1
--     ok (good): cost_revenue_ratio_delta_pp <= -1
--     ok (stable): otherwise
--     why      : "Pressure easing" if delta <= -1
--                else "Margin compression risk" if delta >= +1
--                else "Stable margin"
--
-- =============================================================================

DROP VIEW IF EXISTS v_overview_signals CASCADE;

CREATE VIEW v_overview_signals AS
WITH
rev_kpi AS (SELECT * FROM v_revenue_kpis),
proc_kpi AS (SELECT * FROM v_procurement_kpis),
cost_kpi AS (SELECT * FROM v_cost_kpis),

-- Top customer (for the "driven by one customer" why-line)
top_customer AS (
    SELECT
        customer_name,
        share_pct
    FROM v_top_customers_overall
    ORDER BY amount_tl DESC NULLS LAST
    LIMIT 1
),

-- Top 2 procurement buckets (for "greige + yarn dominant" why-line)
top_proc_buckets AS (
    SELECT business_bucket, total_tl, rk
    FROM (
        SELECT
            business_bucket,
            SUM(amount_tl)::numeric AS total_tl,
            ROW_NUMBER() OVER (ORDER BY SUM(amount_tl) DESC NULLS LAST) AS rk
        FROM v_monthly_procurement_by_bucket
        WHERE month >= (
            SELECT (DATE_TRUNC('month', MAX(fatura_tarihi)) - INTERVAL '12 months')::date
            FROM fact_purchase_lines_clean
        )
        GROUP BY business_bucket
    ) t
    WHERE rk <= 2
),
proc_top2_set AS (
    SELECT
        ARRAY_AGG(business_bucket::text ORDER BY rk) AS buckets
    FROM top_proc_buckets
),

-- ── SLOT 1 — Customer concentration ──
slot1 AS (
    SELECT
        1 AS display_order,
        'customer_concentration' AS signal_key,
        CASE
            WHEN r.top_3_share_delta_pp >= 5 OR r.top_3_share_latest_pct >= 40 THEN 'critical'
            WHEN r.top_3_share_delta_pp >= 2 OR r.top_3_share_latest_pct >= 33 THEN 'warning'
            ELSE 'ok'
        END AS severity,
        'Customer concentration' AS title,
        ('Top 3 share '
            || COALESCE(r.top_3_share_latest_pct::text || '%', '—')
            || CASE
                 WHEN r.top_3_share_delta_pp IS NULL THEN ''
                 WHEN r.top_3_share_delta_pp >= 0 THEN ' (+' || r.top_3_share_delta_pp::text || 'pp)'
                 ELSE ' (' || r.top_3_share_delta_pp::text || 'pp)'
               END
        )::text AS metric_text,
        CASE
            WHEN (SELECT share_pct FROM top_customer) >= 25 THEN
                'Driven by one customer surge ('
                || COALESCE((SELECT customer_name FROM top_customer), '?')
                || ' ' || COALESCE((SELECT share_pct::text FROM top_customer), '?')
                || '%)'
            WHEN r.top_3_share_delta_pp >= 2 THEN 'Concentration shifted upward'
            WHEN r.top_3_share_latest_pct >= 33 THEN 'Above 33% watch threshold'
            ELSE 'Within normal range'
        END::text AS why_text
    FROM rev_kpi r
),

-- ── SLOT 2 — Procurement concentration ──
slot2 AS (
    SELECT
        2 AS display_order,
        'procurement_concentration' AS signal_key,
        CASE
            WHEN p.top_3_supplier_share_pct >= 50 THEN 'critical'
            WHEN p.top_3_supplier_share_pct >= 40 THEN 'warning'
            WHEN p.top_3_supplier_share_pct >= 33 THEN 'warning'
            ELSE 'ok'
        END AS severity,
        'Procurement concentration' AS title,
        ('Top 3 supplier share ' || COALESCE(p.top_3_supplier_share_pct::text || '%', '—'))::text AS metric_text,
        CASE
            WHEN (SELECT buckets FROM proc_top2_set) @> ARRAY['raw_material_greige_fabric','raw_material_yarn']::text[]
              OR (SELECT buckets FROM proc_top2_set) @> ARRAY['raw_material_yarn','raw_material_greige_fabric']::text[]
              THEN 'Greige + yarn remain dominant'
            WHEN p.top_3_supplier_share_pct >= 40 THEN 'Concentrated supplier base'
            ELSE 'Healthy supplier diversification'
        END::text AS why_text
    FROM proc_kpi p
),

-- ── SLOT 3 — Contra revenue ──
slot3 AS (
    SELECT
        3 AS display_order,
        'contra_revenue' AS signal_key,
        CASE
            WHEN r.contra_share_pct >= 10 THEN 'critical'
            WHEN r.contra_share_pct >= 5  THEN 'warning'
            ELSE 'ok'
        END AS severity,
        'Contra revenue' AS title,
        ('Contra share ' || COALESCE(r.contra_share_pct::text || '%', '—'))::text AS metric_text,
        CASE
            WHEN r.contra_share_pct >= 10 THEN 'Above critical level — quality/return signal'
            WHEN r.contra_share_pct >= 5  THEN 'Above watch threshold (5%)'
            ELSE 'Within normal range'
        END::text AS why_text
    FROM rev_kpi r
),

-- ── SLOT 4 — Margin trend ──
slot4 AS (
    SELECT
        4 AS display_order,
        'margin_trend' AS signal_key,
        CASE
            WHEN c.cost_revenue_ratio_delta_pp >= 2  THEN 'critical'
            WHEN c.cost_revenue_ratio_delta_pp >= 1  THEN 'warning'
            WHEN c.cost_revenue_ratio_delta_pp <= -1 THEN 'ok'
            ELSE 'ok'
        END AS severity,
        'Margin trend' AS title,
        ('Cost/revenue '
            || CASE
                 WHEN c.cost_revenue_ratio_delta_pp IS NULL THEN '—'
                 WHEN c.cost_revenue_ratio_delta_pp >= 0 THEN '+' || c.cost_revenue_ratio_delta_pp::text || 'pp'
                 ELSE c.cost_revenue_ratio_delta_pp::text || 'pp'
               END
        )::text AS metric_text,
        CASE
            WHEN c.cost_revenue_ratio_delta_pp >= 2  THEN 'Significant margin compression'
            WHEN c.cost_revenue_ratio_delta_pp >= 1  THEN 'Margin compression risk'
            WHEN c.cost_revenue_ratio_delta_pp <= -1 THEN 'Pressure easing'
            ELSE 'Stable margin'
        END::text AS why_text
    FROM cost_kpi c
)

SELECT * FROM slot1
UNION ALL SELECT * FROM slot2
UNION ALL SELECT * FROM slot3
UNION ALL SELECT * FROM slot4
ORDER BY display_order;


COMMENT ON VIEW v_overview_signals IS
'M2.5.1 — Overview Phase 1 top-signals strip. Always returns 4 rows, one per
signal slot: customer_concentration, procurement_concentration, contra_revenue,
margin_trend. Severity rules are explicit and threshold-based.';
