-- migrations/021_extend_tender_keywords.sql
-- Phase F1 keyword extension after Mert's review of REJECTED tenders.
-- The original 47 keywords missed common Turkish public-procurement clothing
-- terms (is kiyafeti, is elbisesi, tulum, mont, gomlek, pantolon, etc.) and
-- broad terms (kiyafet, elbise) that catch tenders relevant to Rayon's profile.
-- Re-score all existing tenders after applying.

BEGIN;

INSERT INTO lkp_tender_keywords (keyword, normalized, keyword_class, weight, notes) VALUES
  -- Mert's mandatory core list (canonical) -- some may already exist
  ('tekstil',          'tekstil',           'canonical', 30, 'Generic textile term'),
  ('kumas',            'kumas',             'canonical', 25, 'Fabric (already there likely)'),
  ('konfeksiyon',      'konfeksiyon',       'canonical', 30, 'Garment manufacturing'),
  ('personel kiyafeti','personel kiyafeti', 'canonical', 30, 'Staff uniform - direct Rayon relevance'),
  ('is elbisesi',      'is elbisesi',       'canonical', 30, 'Work outfit'),
  ('is kiyafeti',      'is kiyafeti',       'canonical', 30, 'Work clothing'),
  ('askeri tekstil',   'askeri tekstil',    'canonical', 35, 'Military textile'),
  ('uniforma',         'uniforma',          'canonical', 30, 'Uniform'),
  ('polis kumas',      'polis kumas',       'canonical', 35, 'Police fabric'),
  ('asker kumas',      'asker kumas',       'canonical', 35, 'Military fabric'),
  ('guvenlik kumas',   'guvenlik kumas',    'canonical', 30, 'Security fabric'),
  
  -- New specific clothing items (high precision)
  ('yagmurluk',        'yagmurluk',         'supplementary', 22, 'Raincoat - technical fabric'),
  ('palto',            'palto',             'supplementary', 20, 'Coat'),
  ('tulum',            'tulum',             'supplementary', 20, 'Coverall/jumpsuit'),
  ('mont',             'mont',              'supplementary', 18, 'Jacket'),
  ('ceket',            'ceket',             'supplementary', 18, 'Blazer/jacket'),
  ('gomlek',           'gomlek',            'supplementary', 18, 'Shirt'),
  ('pantolon',         'pantolon',          'supplementary', 18, 'Trousers'),
  
  -- Broad terms (lower weight to control false positives)
  ('kiyafet',          'kiyafet',           'supplementary', 15, 'Generic clothing'),
  ('elbise',           'elbise',            'supplementary', 15, 'Generic outfit/dress'),
  ('is guvenligi',     'is guvenligi',      'supplementary', 20, 'Safety equipment context'),
  ('eldiven',          'eldiven',           'supplementary', 12, 'Glove - high FP risk (medical/lab)')
ON CONFLICT (normalized) DO UPDATE SET
  weight = GREATEST(lkp_tender_keywords.weight, EXCLUDED.weight),
  keyword_class = EXCLUDED.keyword_class,
  notes = EXCLUDED.notes;

COMMIT;
