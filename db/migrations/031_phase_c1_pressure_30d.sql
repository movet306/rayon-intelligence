-- 031_phase_c1_pressure_30d.sql
-- Phase C+1: Add pressure_30d column to fact_yarn_price_pressure
--
-- Enables 30-day rolling % change calculation per yarn (in addition to
-- the existing pressure_7d). Computed by build_yarn_pricing.py via
-- lookup of the fact row at calc_date - 30 calendar days.
--
-- NULL is preserved when insufficient history exists. Idempotent.

ALTER TABLE fact_yarn_price_pressure
    ADD COLUMN IF NOT EXISTS pressure_30d NUMERIC(8, 4);

COMMENT ON COLUMN fact_yarn_price_pressure.pressure_30d IS
    'Phase C+1: 30-day rolling percent change in yarn estimated index. '
    'Computed by build_yarn_pricing.py via lookup of fact row at calc_date - 30 days. '
    'NULL when insufficient history (first 30 days after backfill or sparse data).';

-- Verification
DO $$
DECLARE
    has_col BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'fact_yarn_price_pressure'
        AND column_name = 'pressure_30d'
    ) INTO has_col;

    IF has_col THEN
        RAISE NOTICE 'Migration 031: pressure_30d column ready';
    ELSE
        RAISE EXCEPTION 'Migration 031 FAILED: pressure_30d column missing';
    END IF;
END $$;
