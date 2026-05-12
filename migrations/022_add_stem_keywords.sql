-- migrations/022_add_stem_keywords.sql
-- Phase F1 fix: Migration 021 failed silently (wrong class names + wrong ON CONFLICT key).
-- This migration uses correct class names ('high_priority', 'medium_priority') and
-- correct unique key (keyword). Stem-based keywords catch all Turkish possessive
-- inflections (kiyafet->kiyafeti, kiyafetler, kiyafetinden, etc.) via substring match.

BEGIN;

INSERT INTO lkp_tender_keywords (keyword, normalized, keyword_class, weight, notes) VALUES
  -- Stem-based broad-coverage keywords (catch all inflections via substring match)
  ('kıyafet',          'kiyafet',           'high_priority',   25, 'Clothing stem - catches kiyafeti, kiyafetler, etc.'),
  ('elbise',           'elbise',            'high_priority',   25, 'Outfit/dress stem'),
  ('üniforma',         'uniforma',          'high_priority',   30, 'Uniform stem'),
  
  -- Specific clothing items
  ('tulum',            'tulum',             'medium_priority', 22, 'Coverall/jumpsuit'),
  ('mont',             'mont',              'medium_priority', 18, 'Jacket'),
  ('ceket',            'ceket',             'medium_priority', 18, 'Blazer/jacket'),
  ('gömlek',           'gomlek',            'medium_priority', 18, 'Shirt'),
  ('pantolon',         'pantolon',          'medium_priority', 18, 'Trousers'),
  ('palto',            'palto',             'medium_priority', 20, 'Coat'),
  ('yağmurluk',        'yagmurluk',         'medium_priority', 22, 'Raincoat - technical fabric'),
  ('eldiven',          'eldiven',           'medium_priority', 12, 'Glove - high FP risk'),
  ('iş güvenliği',     'is guvenligi',      'medium_priority', 20, 'Safety equipment'),
  ('kep',              'kep',               'medium_priority', 10, 'Cap'),
  ('bere',             'bere',              'medium_priority', 10, 'Beanie'),
  ('bot',              'bot',               'medium_priority', 12, 'Boot'),
  ('kazak',            'kazak',             'medium_priority', 15, 'Sweater'),
  ('etek',             'etek',              'medium_priority', 12, 'Skirt')
ON CONFLICT (keyword) DO UPDATE SET
  weight = GREATEST(lkp_tender_keywords.weight, EXCLUDED.weight),
  notes = EXCLUDED.notes;

-- Boost weights on Mert's mandatory core list (some had weight=15 from seed)
UPDATE lkp_tender_keywords SET weight = 30 WHERE normalized = 'is kiyafeti'      AND weight < 30;
UPDATE lkp_tender_keywords SET weight = 30 WHERE normalized = 'is elbisesi'      AND weight < 30;
UPDATE lkp_tender_keywords SET weight = 30 WHERE normalized = 'personel kiyafeti'AND weight < 30;
UPDATE lkp_tender_keywords SET weight = 30 WHERE normalized = 'tekstil'          AND weight < 30;
UPDATE lkp_tender_keywords SET weight = 25 WHERE normalized = 'kumas'            AND weight < 25;
UPDATE lkp_tender_keywords SET weight = 30 WHERE normalized = 'konfeksiyon'      AND weight < 30;
UPDATE lkp_tender_keywords SET weight = 35 WHERE normalized = 'askeri tekstil'   AND weight < 35;
UPDATE lkp_tender_keywords SET weight = 35 WHERE normalized = 'polis kumas'      AND weight < 35;
UPDATE lkp_tender_keywords SET weight = 35 WHERE normalized = 'asker kumas'      AND weight < 35;

COMMIT;
