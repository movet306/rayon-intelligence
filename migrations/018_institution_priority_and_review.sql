-- migrations/018_institution_priority_and_review.sql
-- Phase F1 (per ChatGPT critique synthesis): two pieces of "human-aware
-- scoring infrastructure":
--   1. lkp_institution_priority: institution-level weighting layer
--   2. tenders.manual_review_*: track manual review outcomes
--
-- CRITICAL CONTRACT (enforced in scraper, not DB):
--   institution_boost alone CANNOT promote a tender to HIGH.
--   If text_keyword_score == 0, institution boost only triggers LOW (watchlist).
--   If text_keyword_score > 0, combined = text + boost, normal thresholds apply.

BEGIN;

-- 1) Institution priority lookup
CREATE TABLE IF NOT EXISTS lkp_institution_priority (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern TEXT NOT NULL UNIQUE,
    normalized_pattern TEXT NOT NULL,
    weight INTEGER NOT NULL,
    category TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_inst_weight CHECK (weight BETWEEN -50 AND 50),
    CONSTRAINT chk_inst_category CHECK (category IN (
        'defense','police','gendarmerie','coast_guard',
        'firefighter','negative','neutral'
    ))
);

CREATE INDEX IF NOT EXISTS idx_inst_priority_norm
    ON lkp_institution_priority(normalized_pattern);

INSERT INTO lkp_institution_priority (pattern, normalized_pattern, weight, category, notes) VALUES
    ('Milli Savunma',    'milli savunma',     30, 'defense',     'MSB and affiliated military procurement bodies'),
    ('Savunma Sanayi',   'savunma sanayi',    30, 'defense',     'SSB - Savunma Sanayii Baskanligi (defense industry procurement)'),
    ('Genelkurmay',      'genelkurmay',       30, 'defense',     'Genelkurmay Baskanligi (general staff)'),
    ('Hava Kuvvetleri',  'hava kuvvetleri',   30, 'defense',     'Turkish Air Force Command'),
    ('Kara Kuvvetleri',  'kara kuvvetleri',   30, 'defense',     'Turkish Land Forces Command'),
    ('Deniz Kuvvetleri', 'deniz kuvvetleri',  30, 'defense',     'Turkish Navy Command'),
    ('Emniyet',          'emniyet',           25, 'police',      'Emniyet Genel Mudurlugu and provincial police'),
    ('Jandarma',         'jandarma',          25, 'gendarmerie', 'Jandarma Genel Komutanligi and provincial gendarmerie'),
    ('Sahil Guvenlik',   'sahil guvenlik',    25, 'coast_guard', 'Sahil Guvenlik Komutanligi (Coast Guard)'),
    ('Itfaiye',          'itfaiye',           20, 'firefighter', 'Fire departments (any level)'),
    ('Belediye Kultur',  'belediye kultur',  -10, 'negative',    'Belediye Kultur Mudurlugu - tends to procure furnishings (mefrusat) not uniforms'),
    ('Kultur Sosyal',    'kultur sosyal',    -10, 'negative',    'Kultur ve Sosyal Isler - non-uniform-relevant procurement')
ON CONFLICT (pattern) DO NOTHING;

-- 2) Manual review tracking on tenders
ALTER TABLE tenders
    ADD COLUMN IF NOT EXISTS manual_review_label TEXT,
    ADD COLUMN IF NOT EXISTS manual_reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS manual_review_notes TEXT;

ALTER TABLE tenders
    DROP CONSTRAINT IF EXISTS chk_manual_review_label;

ALTER TABLE tenders
    ADD CONSTRAINT chk_manual_review_label CHECK (
        manual_review_label IS NULL OR manual_review_label IN (
            'CONFIRMED_RELEVANT',
            'FALSE_POSITIVE',
            'NEEDS_REVIEW'
        )
    );

CREATE INDEX IF NOT EXISTS idx_tenders_manual_review
    ON tenders(manual_review_label)
    WHERE manual_review_label IS NOT NULL;

COMMIT;
