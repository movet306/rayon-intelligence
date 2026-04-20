-- ============================================================
-- 007_price_intelligence_v2.sql
-- Etap 1A: Price Intelligence v2 schema
-- chain spreads, lag model, confidence tiers, ICE Cotton source
-- ============================================================

-- 1. price_chain_spreads table
CREATE TABLE IF NOT EXISTS price_chain_spreads (
    id              SERIAL PRIMARY KEY,
    calc_date       DATE NOT NULL,
    chain           TEXT NOT NULL,
    upstream_slug   TEXT NOT NULL,
    downstream_slug TEXT NOT NULL,
    spread_usd      NUMERIC(14,4),
    spread_pct      NUMERIC(8,4),
    spread_7d_delta NUMERIC(8,4),
    zscore_30d      NUMERIC(8,4),
    signal          TEXT CHECK (signal IN ('widening','tightening','stable', NULL)),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (calc_date, upstream_slug, downstream_slug)
);

-- 2. dim_material lag columns
ALTER TABLE dim_material
  ADD COLUMN IF NOT EXISTS lag_min_weeks     INTEGER DEFAULT 4,
  ADD COLUMN IF NOT EXISTS lag_max_weeks     INTEGER DEFAULT 8,
  ADD COLUMN IF NOT EXISTS lag_model_version TEXT    DEFAULT 'v1_rule_based';

-- 3. Seed lag values per material
UPDATE dim_material SET lag_min_weeks=2,  lag_max_weeks=4   WHERE slug='pta';
UPDATE dim_material SET lag_min_weeks=3,  lag_max_weeks=6   WHERE slug='polyester_staple_fiber';
UPDATE dim_material SET lag_min_weeks=4,  lag_max_weeks=8   WHERE slug='polyester_fdy';
UPDATE dim_material SET lag_min_weeks=4,  lag_max_weeks=8   WHERE slug='polyester_poy';
UPDATE dim_material SET lag_min_weeks=4,  lag_max_weeks=8   WHERE slug='polyester_dty';
UPDATE dim_material SET lag_min_weeks=4,  lag_max_weeks=8   WHERE slug='polyester_yarn';
UPDATE dim_material SET lag_min_weeks=3,  lag_max_weeks=6   WHERE slug='pa6_chip';
UPDATE dim_material SET lag_min_weeks=3,  lag_max_weeks=6   WHERE slug='pa66_chip';
UPDATE dim_material SET lag_min_weeks=4,  lag_max_weeks=8   WHERE slug='polyamide_fdy';
UPDATE dim_material SET lag_min_weeks=4,  lag_max_weeks=8   WHERE slug='rayon_yarn';
UPDATE dim_material SET lag_min_weeks=6,  lag_max_weeks=12  WHERE slug='cotton_lint';
UPDATE dim_material SET lag_min_weeks=6,  lag_max_weeks=12  WHERE slug='cotton_yarn';
UPDATE dim_material SET lag_min_weeks=3,  lag_max_weeks=6   WHERE slug='adipic_acid';

-- 4. price_metrics_daily new columns
ALTER TABLE price_metrics_daily
  ADD COLUMN IF NOT EXISTS momentum_score    NUMERIC(8,4),
  ADD COLUMN IF NOT EXISTS divergence_score  NUMERIC(8,4),
  ADD COLUMN IF NOT EXISTS confidence_tier   TEXT CHECK (confidence_tier IN ('A','B','C','D','E'));

-- 5. dim_price_source ICE Cotton
INSERT INTO dim_price_source
    (source_name, source_type, frequency, unit, region, methodology, semantic_level, reliability, notes)
VALUES
    ('ice_cotton', 'futures', 'daily', 'USc/lb', 'Global',
     'futures_settlement', 'commodity', 4,
     'ICE Cotton No.2 front-month futures. Global benchmark. NOT China spot. Must be kept in separate analysis layer from SunSirs.')
ON CONFLICT (source_name) DO NOTHING;
