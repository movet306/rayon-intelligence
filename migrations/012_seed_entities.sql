-- Migration 012: Seed 23 entities (suppliers, competitors, regulators, associations)
-- Phase E P1 step 3
-- Status: APPLY MANUALLY in next session, AFTER Migration 010 (entity_type column must exist)
-- This file is committed for review; do NOT auto-apply
-- Source: docs/P1_ENTITY_REFACTOR_DESIGN.md (Migration 012 section)

BEGIN;

-- Upstream / Supplier (8 entities)
INSERT INTO entities (id, name, entity_type, country, geography, website, notes) VALUES
  (gen_random_uuid(), 'SASA', 'supplier', 'TR', 'TR', 'https://www.sasa.com.tr',
   'TR PTA/PET/POY/fiber — primary cost driver for Rayon polyester inputs'),
  (gen_random_uuid(), 'Korteks', 'supplier', 'TR', 'TR', 'https://www.korteks.com.tr',
   'TR polyester filament — direct yarn input'),
  (gen_random_uuid(), 'Indorama', 'supplier', 'TH', 'GLOBAL', 'https://www.indoramaventures.com',
   'Global PET/fiber — benchmark price'),
  (gen_random_uuid(), 'Reliance Recron', 'supplier', 'IN', 'GLOBAL', 'https://www.ril.com',
   'Global polyester capacity'),
  (gen_random_uuid(), 'Hyosung', 'supplier', 'KR', 'GLOBAL', 'https://www.hyosung.com',
   'Global filament benchmark'),
  (gen_random_uuid(), 'UNIFI REPREVE', 'benchmark_brand', 'US', 'GLOBAL', 'https://unifi.com',
   'Recycled polyester signaling'),
  (gen_random_uuid(), 'Aquafil ECONYL', 'benchmark_brand', 'IT', 'EU', 'https://www.aquafil.com',
   'Recycled nylon signaling'),
  (gen_random_uuid(), 'Toray', 'supplier', 'JP', 'GLOBAL', 'https://www.toray.com',
   'Japan technical fiber');

-- TR Benchmark Competitors (7 entities)
INSERT INTO entities (id, name, entity_type, country, geography, website, notes) VALUES
  (gen_random_uuid(), 'YeÅŸim Tekstil', 'competitor', 'TR', 'TR', 'https://www.yesim.com',
   'TR knit leader'),
  (gen_random_uuid(), 'Bossa', 'competitor', 'TR', 'TR', 'https://www.bossa.com.tr',
   'TR denim/woven legacy'),
  (gen_random_uuid(), 'Söktaş', 'competitor', 'TR', 'TR', 'https://www.soktas.com',
   'TR shirting benchmark'),
  (gen_random_uuid(), 'Kıvanç Tekstil', 'competitor', 'TR', 'TR', NULL,
   'TR woven export'),
  (gen_random_uuid(), 'Limonteks', 'competitor', 'TR', 'TR', NULL,
   'TR technical fabric'),
  (gen_random_uuid(), 'Hassan Tekstil', 'competitor', 'TR', 'TR', NULL,
   'TR vertical integration'),
  (gen_random_uuid(), 'Polyteks', 'competitor', 'TR', 'TR', NULL,
   'TR yarn export');

-- International Technical Benchmark (4 entities)
INSERT INTO entities (id, name, entity_type, country, geography, website, notes) VALUES
  (gen_random_uuid(), 'W.L. Gore', 'benchmark_brand', 'US', 'GLOBAL', 'https://www.gore-tex.com',
   'Premium membrane peer'),
  (gen_random_uuid(), 'INVISTA Cordura', 'benchmark_brand', 'US', 'GLOBAL', 'https://www.cordura.com',
   'Technical nylon benchmark, military market'),
  (gen_random_uuid(), 'DuPont Nomex', 'benchmark_brand', 'US', 'GLOBAL', 'https://www.dupont.com/nomex.html',
   'Flame-resistant benchmark');
-- Sympatex already in 32-list, no need to re-add

-- Associations / Regulators (4 entities)
INSERT INTO entities (id, name, entity_type, country, geography, website, notes) VALUES
  (gen_random_uuid(), 'İHKİB', 'association', 'TR', 'TR', 'https://www.ihkib.org.tr',
   'TR garment export narrative'),
  (gen_random_uuid(), 'EURATEX', 'association', 'BE', 'EU', 'https://euratex.eu',
   'EU textile lobby & policy'),
  (gen_random_uuid(), 'ECHA', 'regulator', 'FI', 'EU', 'https://echa.europa.eu',
   'EU chemical restrictions - critical for technical/military line'),
  (gen_random_uuid(), 'TGSD', 'association', 'TR', 'TR', 'https://www.tgsd.org.tr',
   'TR clothing manufacturers - labor/production');

-- Verify
-- SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type ORDER BY 2 DESC;
-- Expected: competitor=39 (32 existing + 7 new), supplier=6, benchmark_brand=6,
--           association=3, regulator=1, total=55

COMMIT;
