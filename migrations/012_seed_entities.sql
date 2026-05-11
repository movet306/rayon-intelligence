-- Migration 012: Seed 23 entities (suppliers, competitors, regulators, associations)
-- Phase E P1 step 3
-- Status: APPLY MANUALLY in next session, AFTER Migration 010 (entity_type column must exist)
-- This file is committed for review; do NOT auto-apply
-- Source: docs/P1_ENTITY_REFACTOR_DESIGN.md (Migration 012 section), regenerated for entity_type consistency

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
  (gen_random_uuid(), 'UNIFI REPREVE', 'supplier', 'US', 'GLOBAL', 'https://unifi.com',
   'Recycled polyester supplier (was benchmark_brand in design)'),
  (gen_random_uuid(), 'Aquafil ECONYL', 'supplier', 'IT', 'EU', 'https://www.aquafil.com',
   'Recycled nylon supplier (was benchmark_brand in design)'),
  (gen_random_uuid(), 'Toray', 'supplier', 'JP', 'GLOBAL', 'https://www.toray.com',
   'Japan technical fiber');

-- TR Benchmark Competitors (7 entities)
INSERT INTO entities (id, name, entity_type, country, geography, website, notes) VALUES
  (gen_random_uuid(), 'Yeşim Tekstil', 'competitor_tr', 'TR', 'TR', 'https://www.yesim.com',
   'TR knit leader'),
  (gen_random_uuid(), 'Bossa', 'competitor_tr', 'TR', 'TR', 'https://www.bossa.com.tr',
   'TR denim/woven legacy'),
  (gen_random_uuid(), 'Söktaş', 'competitor_tr', 'TR', 'TR', 'https://www.soktas.com',
   'TR shirting benchmark'),
  (gen_random_uuid(), 'Kıvanç Tekstil', 'competitor_tr', 'TR', 'TR', 'https://www.kivancgroup.com',
   'TR woven exporter'),
  (gen_random_uuid(), 'Limonteks', 'competitor_tr', 'TR', 'TR', 'https://www.limonteks.com',
   'TR woven exporter'),
  (gen_random_uuid(), 'Hassan Tekstil', 'competitor_tr', 'TR', 'TR', 'https://www.hassantekstil.com',
   'TR knit exporter'),
  (gen_random_uuid(), 'Polyteks', 'competitor_tr', 'TR', 'TR', 'https://www.polyteks.com',
   'TR yarn / fiber');

-- International Technical Benchmark (4 entities)
INSERT INTO entities (id, name, entity_type, country, geography, website, notes) VALUES
  (gen_random_uuid(), 'W.L. Gore', 'competitor_intl', 'US', 'GLOBAL', 'https://www.gore.com',
   'Membrane / laminate benchmark'),
  (gen_random_uuid(), 'INVISTA Cordura', 'competitor_intl', 'US', 'GLOBAL', 'https://www.cordura.com',
   'High-tenacity nylon'),
  (gen_random_uuid(), 'DuPont Nomex', 'competitor_intl', 'US', 'GLOBAL', 'https://www.dupont.com/brands/nomex.html',
   'FR aramid benchmark'),
  (gen_random_uuid(), 'Sympatex', 'competitor_intl', 'DE', 'EU', 'https://www.sympatex.com',
   'Recyclable membrane');

-- Associations / Regulators (4 entities)
INSERT INTO entities (id, name, entity_type, country, geography, website, notes) VALUES
  (gen_random_uuid(), 'İHKİB', 'association', 'TR', 'TR', 'https://www.ihkib.org.tr',
   'Istanbul Apparel Exporters Association'),
  (gen_random_uuid(), 'EURATEX', 'association', 'BE', 'EU', 'https://euratex.eu',
   'European Apparel and Textile Confederation'),
  (gen_random_uuid(), 'ECHA', 'regulator', 'FI', 'EU', 'https://echa.europa.eu',
   'European Chemicals Agency (REACH)'),
  (gen_random_uuid(), 'TGSD', 'association', 'TR', 'TR', 'https://www.tgsd.org.tr',
   'Turkish Clothing Manufacturers Association');

COMMIT;

-- Verification queries (run after apply):
-- SELECT COUNT(*) FROM entities;  -- Should be 32 (existing) + 23 (new) = 55
-- SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type ORDER BY 2 DESC;
-- SELECT name, entity_type, country FROM entities WHERE entity_type IN ('supplier','association','regulator') ORDER BY entity_type, name;