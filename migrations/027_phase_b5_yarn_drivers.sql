-- Migration 027 v3 — simple multi-row INSERT (no SELECT FROM VALUES wrapper).
-- Idempotency dropped because dim_material currently has 0 of these 12 slugs.

INSERT INTO dim_material
  (slug, family, commodity_name, subtype, application, applications,
   unit_standard, material_form, rayon_relevance_score)
VALUES
  ('viscose_staple', 'viscose', 'Viscose Staple Yarn', 'spun',
   'apparel_woven_knit', ARRAY['fabric','garment','knit','woven'],
   'USD/kg', 'staple', 4),

  ('modal_staple', 'modal', 'Modal Staple Yarn', 'spun',
   'apparel_woven_knit', ARRAY['fabric','garment','knit','underwear'],
   'USD/kg', 'staple', 4),

  ('cotton_staple', 'cotton', 'Cotton Spun Yarn', 'spun',
   'apparel_woven_knit', ARRAY['fabric','garment','knit','woven','denim'],
   'USD/kg', 'staple', 4),

  ('polyester_staple', 'polyester', 'Polyester Staple Yarn', 'spun',
   'apparel_woven_knit', ARRAY['fabric','garment','technical'],
   'USD/kg', 'staple', 3),

  ('polyamide_staple', 'polyamide', 'Polyamide 6.6 Staple Yarn', 'spun',
   'apparel_specialty', ARRAY['fabric','garment','technical','hosiery'],
   'USD/kg', 'staple', 2),

  ('pv_blend_staple', 'blend', 'PV Blend Yarn (Polyester/Viscose)', 'pv_blend',
   'apparel_woven_knit', ARRAY['fabric','garment','knit','woven'],
   'USD/kg', 'blend', 4),

  ('pm_blend_staple', 'blend', 'PM Blend Yarn (Polyester/Modal)', 'pm_blend',
   'apparel_woven_knit', ARRAY['fabric','garment','knit'],
   'USD/kg', 'blend', 3),

  ('cotton_blend_staple', 'blend', 'Cotton Blend Yarn (PC/CV/CM)', 'cotton_blend',
   'apparel_woven_knit', ARRAY['fabric','garment','knit','woven','denim'],
   'USD/kg', 'blend', 4),

  ('three_component_staple', 'blend', '3-Component Blend Yarn', 'multi_blend',
   'apparel_woven_knit', ARRAY['fabric','garment','knit'],
   'USD/kg', 'blend', 3),

  ('corespun_staple', 'blend', 'Corespun Yarn (with Elastane core)', 'corespun',
   'apparel_stretch', ARRAY['stretch_fabric','denim','sportswear','underwear'],
   'USD/kg', 'blend', 3),

  ('recycled_polyester_staple', 'polyester',
   'Recycled Polyester Staple Yarn (GRS)', 'recycled_spun',
   'sustainable_apparel', ARRAY['recycled_fabric','sustainable_garment','rPET'],
   'USD/kg', 'staple', 3),

  ('recycled_blend_staple', 'blend',
   'Recycled Blend Yarn (GRS)', 'recycled_blend',
   'sustainable_apparel', ARRAY['recycled_fabric','sustainable_garment'],
   'USD/kg', 'blend', 3)

RETURNING slug, family, material_form;
