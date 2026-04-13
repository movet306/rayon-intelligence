-- Rayon Intelligence Platform — Price Architecture
-- Phase 1B: Source-governed price metadata + frequency-aware metrics

BEGIN;

-- ─────────────────────────────────────────────
-- dim_price_source
-- Registry of every price data source.
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dim_price_source (
    source_id       SERIAL      PRIMARY KEY,
    source_name     TEXT        NOT NULL UNIQUE,
    source_type     TEXT        NOT NULL,  -- 'spot', 'futures', 'benchmark', 'survey'
    frequency       TEXT        NOT NULL,  -- 'daily', 'weekly', 'monthly'
    unit            TEXT        NOT NULL,  -- 'RMB/ton', 'USD/kg', 'USc/lb'
    region          TEXT,                  -- 'China', 'Global', 'US'
    methodology     TEXT,                  -- 'spot_market', 'futures_settlement', 'world_bank_index'
    semantic_level  TEXT        NOT NULL,  -- 'commodity', 'semi-spec', 'spec'
    reliability     INTEGER     DEFAULT 3, -- 1=low, 5=high
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- dim_material
-- Canonical material registry keyed by slug.
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dim_material (
    material_id     SERIAL      PRIMARY KEY,
    slug            TEXT        NOT NULL UNIQUE,  -- e.g. 'polyester_staple_fiber'
    family          TEXT        NOT NULL,          -- 'polyester', 'cotton', 'nylon'
    commodity_name  TEXT        NOT NULL,          -- 'PSF', 'Cotton Lint', 'PA6 FDY'
    subtype         TEXT,                          -- 'SD', 'FD', 'micro', 'recycled'
    application     TEXT,                          -- 'woven', 'knit', 'general'
    unit_standard   TEXT        NOT NULL DEFAULT 'RMB/ton',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- Extend price_signals with source governance
-- Nullable for backward compatibility with
-- existing rows already in the table.
-- ─────────────────────────────────────────────
ALTER TABLE price_signals
    ADD COLUMN IF NOT EXISTS source_id      INTEGER REFERENCES dim_price_source(source_id),
    ADD COLUMN IF NOT EXISTS material_id    INTEGER REFERENCES dim_material(material_id),
    ADD COLUMN IF NOT EXISTS frequency      TEXT DEFAULT 'daily',
    ADD COLUMN IF NOT EXISTS semantic_level TEXT DEFAULT 'commodity';

-- ─────────────────────────────────────────────
-- price_metrics_daily
-- Pre-computed metrics table.
-- PRIMARY KEY includes frequency so daily/monthly
-- rows for the same material never collide.
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS price_metrics_daily (
    material        TEXT        NOT NULL,
    metric_date     DATE        NOT NULL,
    frequency       TEXT        NOT NULL DEFAULT 'daily',
    price           NUMERIC(14,4),
    change_1d       NUMERIC(8,4),   -- NULL if frequency != 'daily'
    change_7d       NUMERIC(8,4),   -- NULL if frequency == 'monthly'
    change_30d      NUMERIC(8,4),
    ma7             NUMERIC(14,4),  -- NULL if < 7 data points in series
    ma30            NUMERIC(14,4),  -- NULL if < 30 data points in series
    volatility_7d   NUMERIC(8,4),   -- NULL if frequency != 'daily'
    volatility_30d  NUMERIC(8,4),   -- NULL if frequency != 'daily'
    normalized_idx  NUMERIC(10,4),
    trend_direction TEXT,           -- 'up', 'down', 'flat', NULL if insufficient data
    PRIMARY KEY (material, metric_date, frequency)
);

CREATE INDEX IF NOT EXISTS pmd_material_date_idx
    ON price_metrics_daily (material, metric_date DESC);

-- ─────────────────────────────────────────────
-- Seed: dim_price_source
-- ─────────────────────────────────────────────
INSERT INTO dim_price_source
    (source_name, source_type, frequency, unit, region, methodology, semantic_level, reliability, notes)
VALUES
    ('sunsirs',     'spot',      'daily',   'RMB/ton', 'China',  'spot_market',          'commodity', 4,
     'SunSirs daily spot price, last 6 rows per page'),
    ('indexmundi',  'benchmark', 'monthly', 'USD/kg',  'Global', 'world_bank_index',      'commodity', 3,
     'IndexMundi monthly commodity benchmark, ~9 month lag'),
    ('fred_cotton', 'benchmark', 'monthly', 'USD/kg',  'Global', 'world_bank_pink_sheet', 'commodity', 4,
     'FRED World Bank cotton benchmark - DO NOT use for daily signals')
ON CONFLICT (source_name) DO NOTHING;

-- ─────────────────────────────────────────────
-- Seed: dim_material
-- ─────────────────────────────────────────────
INSERT INTO dim_material
    (slug, family, commodity_name, subtype, application, unit_standard)
VALUES
    ('polyester_staple_fiber', 'polyester', 'PSF',            NULL, 'general',  'RMB/ton'),
    ('polyester_fdy',          'polyester', 'Polyester FDY',  NULL, 'woven',    'RMB/ton'),
    ('polyester_poy',          'polyester', 'Polyester POY',  NULL, 'woven',    'RMB/ton'),
    ('polyester_dty',          'polyester', 'Polyester DTY',  NULL, 'knit',     'RMB/ton'),
    ('polyester_yarn',         'polyester', 'Polyester Yarn', NULL, 'general',  'RMB/ton'),
    ('pta',                    'polyester', 'PTA',            NULL, 'upstream', 'RMB/ton'),
    ('cotton_lint',            'cotton',    'Cotton Lint',    NULL, 'general',  'RMB/ton'),
    ('cotton_yarn',            'cotton',    'Cotton Yarn',    NULL, 'general',  'RMB/ton'),
    ('polyamide_fdy',          'nylon',     'Nylon FDY',      NULL, 'general',  'RMB/ton'),
    ('pa6_chip',               'nylon',     'PA6 Chip',       NULL, 'upstream', 'RMB/ton'),
    ('pa66_chip',              'nylon',     'PA66 Chip',      NULL, 'upstream', 'RMB/ton'),
    ('rayon_yarn',             'rayon',     'Rayon Yarn',     NULL, 'general',  'RMB/ton'),
    ('adipic_acid',            'nylon',     'Adipic Acid',    NULL, 'upstream', 'RMB/ton')
ON CONFLICT (slug) DO NOTHING;

COMMIT;
