-- 008_yarn_master.sql
-- Yarn Master Architecture Phase 1
-- Creates 4 tables: dim_yarn_master, dim_yarn_price_driver,
-- fact_supplier_quotes, fact_yarn_price_pressure
-- Seeded via scrapers/seed_yarn_master.py from lkp_yarn_taxonomy (52 rows)

CREATE TABLE IF NOT EXISTS dim_yarn_master (
    yarn_id          SERIAL PRIMARY KEY,
    yarn_code        TEXT UNIQUE NOT NULL,
    display_name     TEXT NOT NULL,
    fiber_family     TEXT NOT NULL,
    material_form    TEXT NOT NULL,
    spinning_method  TEXT,
    filament_process TEXT,
    count_ne         NUMERIC(6,2),
    denier           INTEGER,
    filament_count   INTEGER,
    denier_class     TEXT,
    luster           TEXT,
    recycle_flag     BOOLEAN DEFAULT FALSE,
    blend_a_fiber    TEXT,
    blend_a_ratio    NUMERIC(4,2),
    blend_b_fiber    TEXT,
    blend_b_ratio    NUMERIC(4,2),
    application      TEXT[],
    rayon_uses       BOOLEAN DEFAULT FALSE,
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dim_yarn_price_driver (
    driver_id              SERIAL PRIMARY KEY,
    yarn_id                INTEGER REFERENCES dim_yarn_master(yarn_id),
    primary_driver_slug    TEXT NOT NULL,
    secondary_driver_slug  TEXT,
    blend_weight_primary   NUMERIC(4,3) DEFAULT 1.0,
    blend_weight_secondary NUMERIC(4,3) DEFAULT 0.0,
    pricing_method         TEXT NOT NULL,
    price_confidence       TEXT NOT NULL,
    denier_premium_rule    JSONB,
    quality_premium_rule   JSONB,
    luster_premium_rule    JSONB,
    recycle_factor         NUMERIC(4,3) DEFAULT 1.0,
    notes                  TEXT
);

CREATE TABLE IF NOT EXISTS fact_supplier_quotes (
    quote_id       SERIAL PRIMARY KEY,
    yarn_id        INTEGER REFERENCES dim_yarn_master(yarn_id),
    supplier_name  TEXT NOT NULL,
    quote_date     DATE NOT NULL,
    price_usd_kg   NUMERIC(10,4) NOT NULL,
    currency       TEXT DEFAULT 'USD',
    unit           TEXT DEFAULT 'kg',
    incoterm       TEXT,
    origin         TEXT,
    moq_kg         INTEGER,
    lead_time_days INTEGER,
    quality_notes  TEXT,
    source         TEXT DEFAULT 'manual',
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fact_yarn_price_pressure (
    id               SERIAL PRIMARY KEY,
    calc_date        DATE NOT NULL,
    yarn_id          INTEGER REFERENCES dim_yarn_master(yarn_id),
    driver_price_usd NUMERIC(10,4),
    estimated_index  NUMERIC(10,4),
    pressure_7d      NUMERIC(8,4),
    pressure_signal  TEXT,
    confidence       TEXT,
    pricing_method   TEXT,
    UNIQUE (calc_date, yarn_id)
);
