-- Rayon Intelligence Platform — Price Metrics USD column
-- Adds price_usd (true USD conversion) to price_metrics_daily.
-- Populated by build_price_metrics.py using live CNY/USD rate.

BEGIN;

ALTER TABLE price_metrics_daily
    ADD COLUMN IF NOT EXISTS price_usd NUMERIC(14, 4);

COMMENT ON COLUMN price_metrics_daily.price_usd IS
    'Price converted to USD/ton using live CNY/USD rate from frankfurter.app at build time.';

COMMIT;
