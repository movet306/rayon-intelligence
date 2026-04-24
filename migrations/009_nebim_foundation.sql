-- ============================================================================
-- Migration 009 — Nebim Internal Data Foundation
-- ============================================================================
-- Purpose: Load 5-year Nebim ALIŞ/SATIŞ accounting data into PostgreSQL with
--          classification layer (v3 post-sampling) for internal BI use.
--
-- Structure:
--   BRONZE    — raw accounting export, tam kopya
--   SILVER    — classified transaction lines (fact_*_lines_clean)
--   DIMENSION — business bucket definitions + classification versioning
--
-- Convention:
--   - bronze_*   = raw data, never modified by business logic
--   - fact_*     = line-level transactional facts
--   - dim_*      = slowly-changing or static reference tables
--   - *_clean    = suffix for silver (classified) tables
--
-- Idempotent: DROP IF EXISTS + CREATE. Safe to re-run.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- DROP existing if migration re-runs
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_sales_lines_clean    CASCADE;
DROP TABLE IF EXISTS fact_purchase_lines_clean CASCADE;
DROP TABLE IF EXISTS bronze_nebim_satis_raw    CASCADE;
DROP TABLE IF EXISTS bronze_nebim_alis_raw     CASCADE;
DROP TABLE IF EXISTS dim_business_bucket       CASCADE;
DROP TABLE IF EXISTS dim_classification_version CASCADE;

-- ============================================================================
-- DIMENSION TABLES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- dim_classification_version
-- Tracks each version of the classification framework for auditable lineage
-- ----------------------------------------------------------------------------
CREATE TABLE dim_classification_version (
    version_id          SERIAL        PRIMARY KEY,
    version_label       VARCHAR(20)   NOT NULL UNIQUE,
    description         TEXT,
    effective_from      DATE          NOT NULL DEFAULT CURRENT_DATE,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    is_current          BOOLEAN       NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE dim_classification_version IS
    'Tracks Nebim classification framework versions. Exactly one row has is_current=true.';

-- Seed v3 as current
INSERT INTO dim_classification_version (version_label, description, is_current) VALUES
('v3', 'Post-sampling framework. 5 new buckets (leasing_financial, customer_claims, capex_investment, capex_disposal, supplier_prepayments). Subtypes: contra_revenue_return/discount, suspected_asset_sale. Micro-corrections to utilities. is_prepayment flag added.', TRUE);


-- ----------------------------------------------------------------------------
-- dim_business_bucket
-- Master list of business buckets with dual relevance flags
-- ----------------------------------------------------------------------------
CREATE TABLE dim_business_bucket (
    bucket_id                   SERIAL      PRIMARY KEY,
    bucket_name                 VARCHAR(50) NOT NULL UNIQUE,
    bucket_category             VARCHAR(30) NOT NULL,  -- procurement/revenue/capex/noise/review
    is_core_business_relevant   BOOLEAN,               -- NULL=uncertain
    is_cost_model_relevant      BOOLEAN,               -- NULL=uncertain
    description                 TEXT,
    example_account_codes       TEXT,
    notes                       TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE dim_business_bucket IS
    'Business bucket master. NULL relevance flags = uncertainty preserved (review/prepayment buckets).';

-- Seed all v3 buckets
INSERT INTO dim_business_bucket (bucket_name, bucket_category, is_core_business_relevant, is_cost_model_relevant, description, example_account_codes) VALUES
    -- Core raw materials
    ('raw_material_yarn',           'procurement', TRUE,  TRUE,
     'Yarn purchases (cotton/polyester/nylon/elastane/blend). Phase B priority input.',
     '150 06 xxxx'),
    ('raw_material_chemical',       'procurement', TRUE,  TRUE,
     'Production chemicals.',
     '150 04 xxxx'),
    ('raw_material_dye',            'procurement', TRUE,  TRUE,
     'Dyes for fabric finishing.',
     '150 05 xxxx'),
    ('raw_material_greige_fabric',  'procurement', TRUE,  TRUE,
     'Imported greige (HAM) fabric for woven finishing.',
     '150 10 xxxx'),

    -- Production / cost model but not core-business
    ('outsourced_processing',       'production',  FALSE, TRUE,
     'FASON processing (dyeing/weaving/texturing/lamination/etc).',
     '730 03 xxxx'),
    ('utilities',                   'production',  FALSE, TRUE,
     'Electricity, natural gas, solid fuel (coal, hazelnut shell).',
     '730 04 0010, 730 04 0022, 150 07 0001'),
    ('maintenance_factory',         'production',  FALSE, TRUE,
     'Factory maintenance, repair, supplies (KEÇE, KERESTE).',
     '730 04 0008, 730 04 0035, 150 07 0005'),
    ('packaging',                   'production',  FALSE, TRUE,
     'Packaging materials and consumables.',
     '730 04 xxxx (AMBALAJ), 150 07 0006'),
    ('factory_overhead',            'production',  FALSE, TRUE,
     'Factory meals, transport, safety, demirbaş — allocation input.',
     '730 04 0005, 730 04 0021'),
    ('logistics_distribution',      'production',  FALSE, TRUE,
     'Outbound NAKLİYE / KARGO / GÜMRÜK / IHRACAT.',
     '760 04 xxxx'),
    ('selling_distribution',        'production',  FALSE, TRUE,
     '760 fallback (pazarlama aracı, seyahat).',
     '760 xx xxxx'),

    -- Pure overhead
    ('admin_gna',                   'overhead',    FALSE, FALSE,
     'General admin (telefon, kırtasiye, yemek, bina bakım).',
     '770 04 xxxx'),
    ('professional_services',       'overhead',    FALSE, FALSE,
     'Avukatlık, danışmanlık, mali müşavirlik, noter.',
     '770 04 0002, 0003, 0011'),
    ('tax_nondeductible',           'overhead',    FALSE, FALSE,
     'KKEG / 6802 non-deductible expenses.',
     '689 01 xxxx'),

    -- Revenue side — core business
    ('core_product_sales',          'revenue',     TRUE,  FALSE,
     'Knit + woven fabric core sales.',
     '600 02 0001, 600 61 xxxx'),
    ('outsourced_service_revenue',  'revenue',     TRUE,  FALSE,
     'FASON service revenue (Rayon as processor).',
     '600 18, 600 22-30 xxxx'),
    ('sales_return_contra',         'revenue',     TRUE,  FALSE,
     'Sales returns + discounts. Subtypes: contra_revenue_return, contra_revenue_discount.',
     '601 xx xxxx, 611 xx xxxx, 600 xx in ALIŞ'),
    ('customer_claims',             'revenue',     TRUE,  FALSE,
     'Reklamasyon giderleri (customer damage/claim compensation). Distinct from returns.',
     '612 01 0002'),

    -- Non-core / noise
    ('scrap_sales',                 'noise',       FALSE, FALSE,
     'HURDA PLASTİK VE ATIK SATIŞLARI.',
     '602 01 0006'),
    ('fx_gain_loss',                'noise',       FALSE, FALSE,
     'Kur farkı karları/zararları.',
     '646 01 xxxx'),
    ('misc_noncore_sales',          'noise',       FALSE, FALSE,
     'DİĞER GELİRLER, REKLAMASYON GELİRLERİ (small).',
     '602 01 0009, 0011'),
    ('other_noncore_income',        'noise',       FALSE, FALSE,
     'DIGER CESITLI GELIRLER.',
     '679 01 xxxx'),
    ('adjustments_noncore',         'noise',       FALSE, FALSE,
     'FIYAT FARKLARI, CİRO PRİMLERİ.',
     '602 01 0001, 0008'),
    ('non_core_trading',            'noise',       FALSE, FALSE,
     'TİCARİ MAL resale (greige/chemical/dye/coated fabric).',
     '600 08-12 xxxx, SATIŞ 150/153'),

    -- CAPEX family
    ('leasing_financial',           'capex',       FALSE, FALSE,
     'Machine leasing (CAPEX finance — Denizbank, Garanti, etc.).',
     '301 01 xxxx'),
    ('capex_investment',            'capex',       FALSE, FALSE,
     'Fixed asset purchase: land, machines, fixtures, vehicles (buy side).',
     '253 xx xxxx, 254 xx xxxx, 255 xx xxxx, 258 xx xxxx'),
    ('capex_disposal',              'capex',       FALSE, FALSE,
     'Fixed asset sale: vehicles, equipment (sell side).',
     '254 in SATIŞ, 253/255/258 in SATIŞ'),

    -- Uncertain
    ('supplier_prepayments',        'prepayment',  NULL,  NULL,
     'Verilen avanslar — material/yarn prepayments, not yet realized procurement. is_prepayment flag=TRUE.',
     '159 01 xxxx'),
    ('anomalous_review',            'review',      NULL,  NULL,
     'Holding bucket for rows needing manual review. Contains yarn_resale (SATIŞ 600-13), suspected_asset_sale (602 >10M), and unclassified 153/730/760/770 in SATIŞ.',
     'Various');


-- ============================================================================
-- BRONZE TABLES — tam kopya, ham veri
-- ============================================================================

-- ----------------------------------------------------------------------------
-- bronze_nebim_alis_raw
-- ----------------------------------------------------------------------------
CREATE TABLE bronze_nebim_alis_raw (
    bronze_id             BIGSERIAL      PRIMARY KEY,
    source_row_id         INTEGER        NOT NULL,       -- 0-indexed excel row
    load_batch_id         UUID           NOT NULL,
    loaded_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),

    -- Original Excel columns (exact field names, mapped to snake_case)
    fatura_tarihi              DATE,
    e_fatura_seri_numarasi     TEXT,
    cari_hesap_aciklamasi      TEXT,
    vergi_dairesi              TEXT,
    vergi_numarasi             TEXT,
    kdv_orani                  NUMERIC(5, 2),
    birim_cinsi_1              TEXT,
    miktar                     NUMERIC(18, 4),
    vergi_haric_tutar_y        NUMERIC(18, 2),
    kdv_y                      NUMERIC(18, 2),
    net_tutar_y                NUMERIC(18, 2),
    hesap_kodu                 TEXT,
    hesap_aciklamasi           TEXT,
    vergi_haric_tutar_d        NUMERIC(18, 2),
    kdv_d                      NUMERIC(18, 2),
    net_tutar_d                NUMERIC(18, 2),
    para_birimi_d              TEXT,

    CONSTRAINT uq_alis_source_row UNIQUE (source_row_id, load_batch_id)
);

CREATE INDEX idx_alis_raw_date     ON bronze_nebim_alis_raw (fatura_tarihi);
CREATE INDEX idx_alis_raw_hesap    ON bronze_nebim_alis_raw (hesap_kodu);
CREATE INDEX idx_alis_raw_batch    ON bronze_nebim_alis_raw (load_batch_id);

COMMENT ON TABLE bronze_nebim_alis_raw IS
    'Raw Nebim ALIŞ export. Never modified by business logic. Source of truth.';


-- ----------------------------------------------------------------------------
-- bronze_nebim_satis_raw
-- ----------------------------------------------------------------------------
CREATE TABLE bronze_nebim_satis_raw (
    bronze_id             BIGSERIAL      PRIMARY KEY,
    source_row_id         INTEGER        NOT NULL,
    load_batch_id         UUID           NOT NULL,
    loaded_at             TIMESTAMPTZ    NOT NULL DEFAULT NOW(),

    fatura_tarihi              DATE,
    e_fatura_seri_numarasi     TEXT,
    cari_hesap_aciklamasi      TEXT,
    vergi_dairesi              TEXT,
    vergi_numarasi             TEXT,
    kdv_orani                  NUMERIC(5, 2),
    birim_cinsi_1              TEXT,
    miktar                     NUMERIC(18, 4),
    vergi_haric_tutar_y        NUMERIC(18, 2),
    kdv_y                      NUMERIC(18, 2),
    net_tutar_y                NUMERIC(18, 2),
    hesap_kodu                 TEXT,
    hesap_aciklamasi           TEXT,
    vergi_haric_tutar_d        NUMERIC(18, 2),
    kdv_d                      NUMERIC(18, 2),
    net_tutar_d                NUMERIC(18, 2),
    para_birimi_d              TEXT,

    CONSTRAINT uq_satis_source_row UNIQUE (source_row_id, load_batch_id)
);

CREATE INDEX idx_satis_raw_date   ON bronze_nebim_satis_raw (fatura_tarihi);
CREATE INDEX idx_satis_raw_hesap  ON bronze_nebim_satis_raw (hesap_kodu);
CREATE INDEX idx_satis_raw_batch  ON bronze_nebim_satis_raw (load_batch_id);

COMMENT ON TABLE bronze_nebim_satis_raw IS
    'Raw Nebim SATIŞ export. Never modified by business logic. Source of truth.';


-- ============================================================================
-- SILVER TABLES — classified transaction lines
-- ============================================================================

-- ----------------------------------------------------------------------------
-- fact_purchase_lines_clean
-- ----------------------------------------------------------------------------
CREATE TABLE fact_purchase_lines_clean (
    fact_id                    BIGSERIAL      PRIMARY KEY,

    -- Audit & lineage
    source_sheet               VARCHAR(10)    NOT NULL,  -- 'ALIS'
    source_row_id              INTEGER        NOT NULL,
    bronze_id                  BIGINT,                   -- FK-ish to bronze
    load_batch_id              UUID           NOT NULL,
    classification_version     VARCHAR(20)    NOT NULL,  -- 'v3'
    loaded_at                  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),

    -- Raw fields (copied from bronze for query performance — denormalized)
    fatura_tarihi              DATE,
    e_fatura_seri_numarasi     TEXT,
    cari_hesap_aciklamasi      TEXT,
    vergi_dairesi              TEXT,
    vergi_numarasi             TEXT,
    kdv_orani                  NUMERIC(5, 2),
    birim_cinsi                TEXT,
    miktar                     NUMERIC(18, 4),
    vergi_haric_tutar_y        NUMERIC(18, 2),
    kdv_y                      NUMERIC(18, 2),
    net_tutar_y                NUMERIC(18, 2),
    hesap_kodu                 TEXT,
    hesap_aciklamasi           TEXT,
    vergi_haric_tutar_d        NUMERIC(18, 2),
    kdv_d                      NUMERIC(18, 2),
    net_tutar_d                NUMERIC(18, 2),
    para_birimi_d              TEXT,

    -- Derived classification fields (from classify_v3.py)
    account_prefix_3           VARCHAR(3),
    account_class_main         VARCHAR(50),
    account_class_sub          VARCHAR(50),
    business_bucket            VARCHAR(50)    NOT NULL,
    subtype                    VARCHAR(50),              -- contra_revenue_return, yarn_resale, etc
    project_use_case           VARCHAR(50),
    is_core_business_relevant  BOOLEAN,                  -- NULL=uncertain
    is_cost_model_relevant     BOOLEAN,                  -- NULL=uncertain
    review_flag                BOOLEAN        NOT NULL DEFAULT FALSE,
    confidence_level           VARCHAR(10),              -- high/medium/low
    classification_reason      TEXT,
    clean_unit_group           VARCHAR(20),
    clean_product_type         VARCHAR(40),
    clean_counterparty_type    VARCHAR(30),

    -- Prepayment flags (for supplier_prepayments bucket)
    is_prepayment              BOOLEAN        NOT NULL DEFAULT FALSE,
    realized_in_procurement    VARCHAR(20)    -- 'unknown' / NULL / future: 'yes'/'no'
);

CREATE INDEX idx_fpl_date          ON fact_purchase_lines_clean (fatura_tarihi);
CREATE INDEX idx_fpl_bucket        ON fact_purchase_lines_clean (business_bucket);
CREATE INDEX idx_fpl_prod_type     ON fact_purchase_lines_clean (clean_product_type);
CREATE INDEX idx_fpl_supplier      ON fact_purchase_lines_clean (cari_hesap_aciklamasi);
CREATE INDEX idx_fpl_batch         ON fact_purchase_lines_clean (load_batch_id);
CREATE INDEX idx_fpl_core_biz      ON fact_purchase_lines_clean (is_core_business_relevant) WHERE is_core_business_relevant = TRUE;
CREATE INDEX idx_fpl_cost_model    ON fact_purchase_lines_clean (is_cost_model_relevant) WHERE is_cost_model_relevant = TRUE;
CREATE INDEX idx_fpl_review        ON fact_purchase_lines_clean (review_flag) WHERE review_flag = TRUE;

COMMENT ON TABLE fact_purchase_lines_clean IS
    'Classified Nebim ALIŞ transaction lines. Silver layer. Regenerated from bronze when classification rules change.';


-- ----------------------------------------------------------------------------
-- fact_sales_lines_clean
-- ----------------------------------------------------------------------------
CREATE TABLE fact_sales_lines_clean (
    fact_id                    BIGSERIAL      PRIMARY KEY,

    -- Audit & lineage
    source_sheet               VARCHAR(10)    NOT NULL,  -- 'SATIS'
    source_row_id              INTEGER        NOT NULL,
    bronze_id                  BIGINT,
    load_batch_id              UUID           NOT NULL,
    classification_version     VARCHAR(20)    NOT NULL,
    loaded_at                  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),

    -- Raw fields (denormalized)
    fatura_tarihi              DATE,
    e_fatura_seri_numarasi     TEXT,
    cari_hesap_aciklamasi      TEXT,
    vergi_dairesi              TEXT,
    vergi_numarasi             TEXT,
    kdv_orani                  NUMERIC(5, 2),
    birim_cinsi                TEXT,
    miktar                     NUMERIC(18, 4),
    vergi_haric_tutar_y        NUMERIC(18, 2),
    kdv_y                      NUMERIC(18, 2),
    net_tutar_y                NUMERIC(18, 2),
    hesap_kodu                 TEXT,
    hesap_aciklamasi           TEXT,
    vergi_haric_tutar_d        NUMERIC(18, 2),
    kdv_d                      NUMERIC(18, 2),
    net_tutar_d                NUMERIC(18, 2),
    para_birimi_d              TEXT,

    -- Derived classification fields
    account_prefix_3           VARCHAR(3),
    account_class_main         VARCHAR(50),
    account_class_sub          VARCHAR(50),
    business_bucket            VARCHAR(50)    NOT NULL,
    subtype                    VARCHAR(50),
    project_use_case           VARCHAR(50),
    is_core_business_relevant  BOOLEAN,
    is_cost_model_relevant     BOOLEAN,
    review_flag                BOOLEAN        NOT NULL DEFAULT FALSE,
    confidence_level           VARCHAR(10),
    classification_reason      TEXT,
    clean_unit_group           VARCHAR(20),
    clean_product_type         VARCHAR(40),
    clean_counterparty_type    VARCHAR(30),

    -- Prepayment fields (kept for schema symmetry; always FALSE / NULL for sales)
    is_prepayment              BOOLEAN        NOT NULL DEFAULT FALSE,
    realized_in_procurement    VARCHAR(20)
);

CREATE INDEX idx_fsl_date       ON fact_sales_lines_clean (fatura_tarihi);
CREATE INDEX idx_fsl_bucket     ON fact_sales_lines_clean (business_bucket);
CREATE INDEX idx_fsl_prod_type  ON fact_sales_lines_clean (clean_product_type);
CREATE INDEX idx_fsl_customer   ON fact_sales_lines_clean (cari_hesap_aciklamasi);
CREATE INDEX idx_fsl_batch      ON fact_sales_lines_clean (load_batch_id);
CREATE INDEX idx_fsl_subtype    ON fact_sales_lines_clean (subtype);
CREATE INDEX idx_fsl_core_biz   ON fact_sales_lines_clean (is_core_business_relevant) WHERE is_core_business_relevant = TRUE;
CREATE INDEX idx_fsl_review     ON fact_sales_lines_clean (review_flag) WHERE review_flag = TRUE;

COMMENT ON TABLE fact_sales_lines_clean IS
    'Classified Nebim SATIŞ transaction lines. Silver layer. Subtype column flags yarn_resale, suspected_asset_sale, contra_revenue_return/discount.';


COMMIT;

-- ============================================================================
-- End of migration 009
-- ============================================================================
