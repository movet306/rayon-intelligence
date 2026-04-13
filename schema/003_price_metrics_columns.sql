-- Rayon Intelligence Platform — Price Metrics Data Quality Columns
-- Phase 1B patch: add data_points and confidence_level to price_metrics_daily

BEGIN;

ALTER TABLE price_metrics_daily
    ADD COLUMN IF NOT EXISTS data_points      INTEGER,
    ADD COLUMN IF NOT EXISTS confidence_level TEXT;

COMMENT ON COLUMN price_metrics_daily.data_points IS
    'Number of price_signals data points available at the time this metric row was computed.';

COMMENT ON COLUMN price_metrics_daily.confidence_level IS
    'high (>=30 pts) | medium (>=14) | low (>=7) | minimal (<7). '
    'Controls which metrics are non-NULL and whether signals are generated.';

COMMIT;
