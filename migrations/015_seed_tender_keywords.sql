-- migrations/015_seed_tender_keywords.sql
-- Phase F0: Seed canonical keyword list per design doc Appendix A v1.1
-- Idempotent: ON CONFLICT DO NOTHING

BEGIN;

INSERT INTO lkp_tender_keywords (keyword, normalized, keyword_class, weight, notes) VALUES
  -- A.1 CANONICAL CORE (mandatory baseline, frozen by Mert)
  ('tekstil',           'tekstil',           'medium_priority',  25, 'A.1 canonical core'),
  ('kumaş',             'kumas',             'medium_priority',  25, 'A.1 canonical core'),
  ('kumas',             'kumas',             'medium_priority',  25, 'A.1 canonical core (aksanız)'),
  ('konfeksiyon',       'konfeksiyon',       'medium_priority',  25, 'A.1 canonical core'),
  ('personel kıyafeti', 'personel kiyafeti', 'medium_priority',  15, 'A.1 canonical core'),
  ('personel kiyafeti', 'personel kiyafeti', 'medium_priority',  15, 'A.1 canonical core (aksanız)'),
  ('iş elbisesi',       'is elbisesi',       'medium_priority',  15, 'A.1 canonical core'),
  ('is elbisesi',       'is elbisesi',       'medium_priority',  15, 'A.1 canonical core (aksanız)'),
  ('iş kıyafeti',       'is kiyafeti',       'medium_priority',  15, 'A.1 canonical core'),
  ('is kiyafeti',       'is kiyafeti',       'medium_priority',  15, 'A.1 canonical core (aksanız)'),
  ('askeri tekstil',    'askeri tekstil',    'high_priority',    40, 'A.1 canonical core'),
  ('üniforma',          'uniforma',          'medium_priority',  25, 'A.1 canonical core'),
  ('uniforma',          'uniforma',          'medium_priority',  25, 'A.1 canonical core (aksanız)'),
  ('polis kumaş',       'polis kumas',       'high_priority',    40, 'A.1 canonical core'),
  ('polis kumas',       'polis kumas',       'high_priority',    40, 'A.1 canonical core (aksanız)'),
  ('asker kumaş',       'asker kumas',       'high_priority',    40, 'A.1 canonical core'),
  ('asker kumas',       'asker kumas',       'high_priority',    40, 'A.1 canonical core (aksanız)'),
  ('güvenlik kumaş',    'guvenlik kumas',    'high_priority',    40, 'A.1 canonical core'),
  ('guvenlik kumas',    'guvenlik kumas',    'high_priority',    40, 'A.1 canonical core (aksanız)'),

  -- A.2 SUPPLEMENTARY recall layer (approved v1.1)
  ('FR kumaş',          'fr kumas',          'high_priority',    35, 'A.2 supplementary'),
  ('FR kumas',          'fr kumas',          'high_priority',    35, 'A.2 supplementary (aksanız)'),
  ('flame retardant',   'flame retardant',   'high_priority',    35, 'A.2 supplementary'),
  ('yanmaz kumaş',      'yanmaz kumas',      'high_priority',    35, 'A.2 supplementary'),
  ('yanmaz kumas',      'yanmaz kumas',      'high_priority',    35, 'A.2 supplementary (aksanız)'),
  ('taktik kıyafet',    'taktik kiyafet',    'high_priority',    30, 'A.2 supplementary'),
  ('taktik kiyafet',    'taktik kiyafet',    'high_priority',    30, 'A.2 supplementary (aksanız)'),
  ('teknik tekstil',    'teknik tekstil',    'high_priority',    30, 'A.2 supplementary'),
  ('koruyucu kıyafet',  'koruyucu kiyafet',  'medium_priority',  20, 'A.2 supplementary'),
  ('koruyucu kiyafet',  'koruyucu kiyafet',  'medium_priority',  20, 'A.2 supplementary (aksanız)'),
  ('softshell',         'softshell',         'medium_priority',  20, 'A.2 supplementary'),
  ('kamuflaj',          'kamuflaj',          'medium_priority',  25, 'A.2 supplementary'),
  ('su geçirmez kumaş', 'su gecirmez kumas', 'medium_priority',  20, 'A.2 supplementary'),
  ('su gecirmez kumas', 'su gecirmez kumas', 'medium_priority',  20, 'A.2 supplementary (aksanız)'),
  ('outdoor kıyafet',   'outdoor kiyafet',   'medium_priority',  15, 'A.2 supplementary'),
  ('outdoor kiyafet',   'outdoor kiyafet',   'medium_priority',  15, 'A.2 supplementary (aksanız)'),

  -- A.3 EXCLUSION (soft-reject: REJECTED flag + history log, NOT deleted)
  ('tekstil fabrikası', 'tekstil fabrikasi', 'exclusion',       -100, 'A.3 exclusion: construction context'),
  ('tekstil fabrikasi', 'tekstil fabrikasi', 'exclusion',       -100, 'A.3 exclusion: construction context (aksanız)'),
  ('tekstil kortlu',    'tekstil kortlu',    'exclusion',       -100, 'A.3 exclusion: conveyor belt'),
  ('tekstil atık',      'tekstil atik',      'exclusion',       -100, 'A.3 exclusion: waste disposal'),
  ('tekstil atik',      'tekstil atik',      'exclusion',       -100, 'A.3 exclusion: waste (aksanız)'),
  ('tekstil temizleme', 'tekstil temizleme', 'exclusion',       -100, 'A.3 exclusion: cleaning service'),
  ('mefruşat',          'mefrusat',          'exclusion',       -100, 'A.3 exclusion: home furnishings'),
  ('mefrusat',          'mefrusat',          'exclusion',       -100, 'A.3 exclusion: home furnishings (aksanız)'),
  ('perde',             'perde',             'exclusion',       -100, 'A.3 exclusion: curtains'),
  ('çarşaf',            'carsaf',            'exclusion',       -100, 'A.3 exclusion: bed linen'),
  ('carsaf',            'carsaf',            'exclusion',       -100, 'A.3 exclusion: bed linen (aksanız)'),
  ('havlu',             'havlu',             'exclusion',       -100, 'A.3 exclusion: towels')
ON CONFLICT (keyword) DO NOTHING;

COMMIT;
