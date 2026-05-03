/**
 * Yarn Intelligence — Phase B2.2 Sheet Setup Script
 *
 * Purpose: Deploy the evidence sheet schema defined in Phase B2.1.
 *   - 6 tabs: _summary + polyester / polyamide / viscose / modal / blend
 *   - 45 columns per family tab, grouped into 5 categories
 *   - Validation rules per column (dropdowns, ranges, regex)
 *   - Derived field formulas (denier_class, repeat_count, evidence_strength,
 *     source_count_total, meets_2_of_5_rule)
 *   - Frozen 6 columns + category color grouping
 *   - _summary tab fed via QUERY from family tabs
 *   - 1 sample row per family tab for testing
 *
 * Scope:
 *   This script ONLY builds the base schema. Timestamp automation
 *   (created_at, last_updated_at, last_updated_by) is intentionally
 *   left out — it belongs to a separate second-step script after the
 *   base sheet is stable.
 *
 * Usage:
 *   1. Paste this entire file into Apps Script editor (Code.gs)
 *   2. Save (Ctrl+S)
 *   3. Run > setupEvidenceSheet
 *   4. First run will request authorization — accept
 *   5. Inspect the sheet, verify tabs, headers, validations, sample rows
 *
 * Idempotency:
 *   Running setupEvidenceSheet() twice on the same sheet will recreate
 *   the tabs from scratch (existing tabs with the target names will be
 *   deleted first). Use this to redeploy after schema changes.
 *
 * Reference:
 *   docs/yarn-intelligence/phase-b2-evidence-sheet-design.md
 *   docs/yarn-intelligence/phase-b2-evidence-sheet-schema.csv
 */

// ============================================================================
// CONFIGURATION
// ============================================================================

const FAMILY_TABS = ['polyester', 'polyamide', 'viscose', 'modal', 'blend'];
const SUMMARY_TAB = '_summary';

// Frozen columns count (from B2.1 design)
const FROZEN_COLS = 6;

// Category color grouping — light pastels for category headers
const CATEGORY_COLORS = {
  identification:   '#cfe2f3',  // light blue
  spec_attributes:  '#d9ead3',  // light green
  source_evidence:  '#fff2cc',  // light yellow
  decision_support: '#fce5cd',  // light orange
  review:           '#efefef'   // light gray
};

// Derived (formula) column indicator color — slightly muted overlay
const DERIVED_BG_TINT = '#f3f3f3';

// ============================================================================
// SCHEMA DEFINITION
// ============================================================================
// 45 columns. Each column is { name, category, type, derived, validation, formula, example, notes }

const COLUMNS = [
  // --- Identification (5) ---
  { name: 'family',              category: 'identification', type: 'enum',         derived: false },
  { name: 'subfamily',           category: 'identification', type: 'enum_family',  derived: false },
  { name: 'raw_label_examples',  category: 'identification', type: 'text',         derived: false },
  { name: 'canonical_code',      category: 'identification', type: 'text',         derived: false },
  { name: 'display_name',        category: 'identification', type: 'text',         derived: false },

  // --- Spec Attributes (13) ---
  { name: 'form',                category: 'spec_attributes', type: 'enum',        derived: false,
    enum: ['filament', 'spun', 'blend'] },
  { name: 'count_type',          category: 'spec_attributes', type: 'enum',        derived: false,
    enum: ['denier', 'Ne'] },
  { name: 'denier',              category: 'spec_attributes', type: 'int_range',   derived: false,
    range: [10, 4000] },
  { name: 'filament_count',      category: 'spec_attributes', type: 'int_range',   derived: false,
    range: [1, 500] },
  { name: 'denier_class',        category: 'spec_attributes', type: 'enum',        derived: true,
    enum: ['micro', 'fine', 'medium', 'heavy'],
    formula: '=IFERROR(IF(ISBLANK(I{ROW}),"",IF(I{ROW}<=30,"micro",IF(I{ROW}<=80,"fine",IF(I{ROW}<=150,"medium","heavy")))),"")' },
  { name: 'ne_count',            category: 'spec_attributes', type: 'decimal_range',derived: false,
    range: [5, 80] },
  { name: 'ply',                 category: 'spec_attributes', type: 'int_range',   derived: false,
    range: [1, 4] },
  { name: 'twist_direction',     category: 'spec_attributes', type: 'enum',        derived: false,
    enum: ['Z', 'S'] },
  { name: 'luster',              category: 'spec_attributes', type: 'enum',        derived: false,
    enum: ['SD', 'FD', 'BR', 'CD', 'HT', 'FR'] },
  { name: 'recycle_flag',        category: 'spec_attributes', type: 'bool',        derived: false },
  { name: 'color_state',         category: 'spec_attributes', type: 'enum',        derived: false,
    enum: ['ECRU', 'BLACK', 'NAVY', 'RED', 'ANTHRACITE', 'OTHER'] },
  { name: 'specialty_flags',     category: 'spec_attributes', type: 'text',        derived: false },
  { name: 'blend_ratio_json',    category: 'spec_attributes', type: 'text',        derived: false },

  // --- Source Evidence (11) ---
  { name: 'tier_0_internal',     category: 'source_evidence', type: 'bool',        derived: false },
  { name: 'tier_1_turkish',      category: 'source_evidence', type: 'int_range',   derived: false,
    range: [0, 999] },
  { name: 'tier_2_global',       category: 'source_evidence', type: 'int_range',   derived: false,
    range: [0, 999] },
  { name: 'tier_3_b2b',          category: 'source_evidence', type: 'int_range',   derived: false,
    range: [0, 999] },
  { name: 'tier_4_benchmark',    category: 'source_evidence', type: 'enum',        derived: false,
    enum: ['direct', 'benchmark', 'proxy', 'estimate', 'none'] },
  { name: 'source_names',        category: 'source_evidence', type: 'text',        derived: false },
  { name: 'source_types',        category: 'source_evidence', type: 'text',        derived: false },
  { name: 'evidence_urls',       category: 'source_evidence', type: 'text',        derived: false },
  { name: 'repeat_count',        category: 'source_evidence', type: 'int',         derived: true,
    formula: '=IFERROR(SUM(T{ROW}:V{ROW}),"")' },
  { name: 'evidence_strength',   category: 'source_evidence', type: 'enum',        derived: true,
    enum: ['strong', 'moderate', 'weak', 'insufficient'],
    formula: '=IFERROR(IF(OR(S{ROW}=TRUE,AND(T{ROW}>0,U{ROW}>=2)),"strong",IF(OR(T{ROW}>0,U{ROW}>=2),"moderate",IF(OR(U{ROW}=1,V{ROW}>=3),"weak","insufficient"))),"")' },
  { name: 'source_count_total',  category: 'source_evidence', type: 'int',         derived: true,
    formula: '=IFERROR(T{ROW}+U{ROW}+V{ROW}+IF(S{ROW}=TRUE,1,0)+IF(W{ROW}<>"none",1,0),"")' },

  // --- Decision Support (10) ---
  { name: 'has_commercial_use_case', category: 'decision_support', type: 'bool',     derived: false },
  { name: 'meets_2_of_5_rule',       category: 'decision_support', type: 'bool',     derived: true,
    formula: '=IFERROR((IF(T{ROW}>0,1,0)+IF(U{ROW}>=2,1,0)+IF(V{ROW}>=3,1,0)+IF(W{ROW}<>"none",1,0)+IF(AD{ROW}=TRUE,1,0))>=2,"")' },
  { name: 'market_common_candidate', category: 'decision_support', type: 'enum',     derived: false,
    enum: ['yes', 'no', 'pending'] },
  { name: 'market_common_subtype',   category: 'decision_support', type: 'enum',     derived: false,
    enum: ['mainstream', 'technical', 'niche-but-repeatable'] },
  { name: 'override_reason',         category: 'decision_support', type: 'text',     derived: false },
  { name: 'pricing_basis_candidate', category: 'decision_support', type: 'enum',     derived: false,
    enum: ['direct', 'benchmark', 'proxy', 'estimate', 'none'] },
  { name: 'primary_driver_candidate',   category: 'decision_support', type: 'text',  derived: false },
  { name: 'secondary_driver_candidate', category: 'decision_support', type: 'text',  derived: false },
  { name: 'rayon_confirmed_candidate',  category: 'decision_support', type: 'enum',  derived: false,
    enum: ['yes', 'no', 'unsure', 'pending'] },
  { name: 'active_tracked_candidate',   category: 'decision_support', type: 'enum',  derived: false,
    enum: ['yes', 'no', 'second-wave', 'pending'] },

  // --- Review (6) ---
  { name: 'status',          category: 'review', type: 'enum',     derived: false,
    enum: ['draft', 'research_filled', 'under_review', 'approved', 'rejected', 'on_hold'] },
  { name: 'reviewer_notes',  category: 'review', type: 'text',     derived: false },
  { name: 'claude_notes',    category: 'review', type: 'text',     derived: false },
  { name: 'last_updated_by', category: 'review', type: 'text',     derived: false }, // automation in B2.2-step2
  { name: 'last_updated_at', category: 'review', type: 'datetime', derived: false }, // automation in B2.2-step2
  { name: 'created_at',      category: 'review', type: 'datetime', derived: false }  // automation in B2.2-step2
];

// Family-specific subfamily enums
const SUBFAMILY_ENUMS = {
  polyester: ['FDY', 'POY', 'DTY', 'ATY', 'staple'],
  polyamide: ['FDY', 'POY', 'DTY', 'ATY', 'staple'],
  viscose:   ['filament', 'staple_ring', 'staple_vortex', 'staple_oe'],
  modal:     ['filament', 'staple_ring', 'staple_vortex', 'staple_oe'],
  blend:     ['filament_blend', 'staple_ring', 'staple_vortex', 'staple_oe']
};

// ============================================================================
// MAIN ENTRY POINT
// ============================================================================

function setupEvidenceSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  // Step 1: clean up any pre-existing target tabs (for idempotency)
  cleanupOldTabs_(ss);

  // Step 2: ensure there's at least one sheet remaining (Sheets requires it)
  ensurePlaceholderSheet_(ss);

  // Step 3: build family tabs
  FAMILY_TABS.forEach(family => buildFamilyTab_(ss, family));

  // Step 4: build _summary tab
  buildSummaryTab_(ss);

  // Step 5: remove placeholder if it was auto-created
  removePlaceholderIfPossible_(ss);

  // Step 6: reorder tabs — _summary first, then family order
  reorderTabs_(ss);

  // Step 7: activate _summary so user lands there
  ss.setActiveSheet(ss.getSheetByName(SUMMARY_TAB));

  SpreadsheetApp.flush();
  Logger.log('Evidence sheet setup complete.');
}

// ============================================================================
// CLEANUP & PLACEHOLDER
// ============================================================================

function cleanupOldTabs_(ss) {
  const targetNames = [SUMMARY_TAB, ...FAMILY_TABS];
  targetNames.forEach(name => {
    const sheet = ss.getSheetByName(name);
    if (sheet) ss.deleteSheet(sheet);
  });
}

function ensurePlaceholderSheet_(ss) {
  if (ss.getSheets().length === 0) {
    ss.insertSheet('_tmp_placeholder');
  }
}

function removePlaceholderIfPossible_(ss) {
  const ph = ss.getSheetByName('_tmp_placeholder');
  if (ph && ss.getSheets().length > 1) {
    ss.deleteSheet(ph);
  }
  // Also clean up the default 'Sheet1' / 'Sayfa1' if still empty
  const defaults = ['Sheet1', 'Sayfa1'];
  defaults.forEach(name => {
    const s = ss.getSheetByName(name);
    if (s && ss.getSheets().length > 1 && s.getLastRow() === 0) {
      ss.deleteSheet(s);
    }
  });
}

function reorderTabs_(ss) {
  const order = [SUMMARY_TAB, ...FAMILY_TABS];
  order.forEach((name, idx) => {
    const sheet = ss.getSheetByName(name);
    if (sheet) ss.setActiveSheet(sheet) && ss.moveActiveSheet(idx + 1);
  });
}

// ============================================================================
// FAMILY TAB BUILDER
// ============================================================================

function buildFamilyTab_(ss, family) {
  const sheet = ss.insertSheet(family);

  // Column widths — generous for text-heavy columns
  sheet.setColumnWidths(1, COLUMNS.length, 130);

  // Row 1: header — column names
  const headerRow = COLUMNS.map(c => c.name);
  sheet.getRange(1, 1, 1, COLUMNS.length).setValues([headerRow]);

  // Header formatting: bold, frozen, category colors
  applyHeaderFormatting_(sheet);

  // Frozen rows + columns
  sheet.setFrozenRows(1);
  sheet.setFrozenColumns(FROZEN_COLS);

  // Validation rules per column
  applyValidationRules_(sheet, family);

  // Derived field formulas (rows 2-1000 pre-filled)
  applyDerivedFormulas_(sheet);

  // Sample row in row 2
  insertSampleRow_(sheet, family);
}

function applyHeaderFormatting_(sheet) {
  const headerRange = sheet.getRange(1, 1, 1, COLUMNS.length);
  headerRange
    .setFontWeight('bold')
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle')
    .setWrap(true);

  // Apply category color per column header
  COLUMNS.forEach((col, idx) => {
    const cell = sheet.getRange(1, idx + 1);
    cell.setBackground(CATEGORY_COLORS[col.category]);

    // Derived columns get a slightly different visual marker — italic header
    if (col.derived) {
      cell.setFontStyle('italic');
    }
  });

  sheet.setRowHeight(1, 40);
}

// ============================================================================
// VALIDATION RULES
// ============================================================================

function applyValidationRules_(sheet, family) {
  // Rule applied to data rows (2 to 1000)
  const FIRST_DATA_ROW = 2;
  const LAST_DATA_ROW = 1000;
  const DATA_ROWS = LAST_DATA_ROW - FIRST_DATA_ROW + 1;

  COLUMNS.forEach((col, idx) => {
    const colNum = idx + 1;
    const range = sheet.getRange(FIRST_DATA_ROW, colNum, DATA_ROWS, 1);

    // Skip derived columns — they get formulas, not validations
    if (col.derived) return;

    let rule = null;

    if (col.type === 'enum_family' && col.name === 'subfamily') {
      const opts = SUBFAMILY_ENUMS[family];
      rule = SpreadsheetApp.newDataValidation()
        .requireValueInList(opts, true)
        .setAllowInvalid(false)
        .setHelpText(`Allowed: ${opts.join(', ')}`)
        .build();
    } else if (col.type === 'enum' && col.enum) {
      rule = SpreadsheetApp.newDataValidation()
        .requireValueInList(col.enum, true)
        .setAllowInvalid(false)
        .setHelpText(`Allowed: ${col.enum.join(', ')}`)
        .build();
    } else if (col.type === 'bool') {
      rule = SpreadsheetApp.newDataValidation()
        .requireValueInList(['TRUE', 'FALSE'], true)
        .setAllowInvalid(false)
        .build();
    } else if (col.type === 'int_range' || col.type === 'decimal_range') {
      const [min, max] = col.range;
      rule = SpreadsheetApp.newDataValidation()
        .requireNumberBetween(min, max)
        .setAllowInvalid(true)  // soft — allow empty
        .setHelpText(`Range: ${min}–${max}`)
        .build();
    }

    // For 'family' column itself, fill with the family name automatically and lock dropdown
    if (col.name === 'family') {
      rule = SpreadsheetApp.newDataValidation()
        .requireValueInList([family], true)
        .setAllowInvalid(false)
        .build();
    }

    if (rule) range.setDataValidation(rule);
  });
}

// ============================================================================
// DERIVED FORMULAS
// ============================================================================

function applyDerivedFormulas_(sheet) {
  const FIRST_DATA_ROW = 2;
  const LAST_DATA_ROW = 1000;

  COLUMNS.forEach((col, idx) => {
    if (!col.derived || !col.formula) return;
    const colNum = idx + 1;

    // Build formula array, one per row, with {ROW} replaced
    const formulas = [];
    for (let r = FIRST_DATA_ROW; r <= LAST_DATA_ROW; r++) {
      formulas.push([col.formula.replace(/\{ROW\}/g, String(r))]);
    }

    const range = sheet.getRange(FIRST_DATA_ROW, colNum, formulas.length, 1);
    range.setFormulas(formulas);
    range.setBackground(DERIVED_BG_TINT);
    range.setFontStyle('italic');
  });
}

// ============================================================================
// SAMPLE ROW
// ============================================================================

function insertSampleRow_(sheet, family) {
  const sample = buildSampleRow_(family);
  // We only set non-derived columns; derived will compute
  COLUMNS.forEach((col, idx) => {
    if (col.derived) return;
    if (sample[col.name] === undefined) return;
    sheet.getRange(2, idx + 1).setValue(sample[col.name]);
  });
}

function buildSampleRow_(family) {
  // One representative example per family — for testing only
  // These can be deleted by the user after verification
  const samples = {
    polyester: {
      family: 'polyester',
      subfamily: 'FDY',
      raw_label_examples: '%100 POLYESTER 75D/72F SD\nPES 75/72 FDY ECRU',
      canonical_code: 'PES_75D_72F_SD',
      display_name: 'PES 75D/72F SD',
      form: 'filament',
      count_type: 'denier',
      denier: 75,
      filament_count: 72,
      ply: 1,
      luster: 'SD',
      recycle_flag: false,
      color_state: 'ECRU',
      tier_0_internal: true,
      tier_1_turkish: 2,
      tier_2_global: 4,
      tier_3_b2b: 7,
      tier_4_benchmark: 'estimate',
      source_names: 'Sanko | Lenzing | Indorama | Alibaba',
      source_types: 'turkish_catalog | global_catalog | global_catalog | b2b_listing',
      evidence_urls: 'https://example.com/sanko\nhttps://example.com/lenzing',
      has_commercial_use_case: true,
      market_common_candidate: 'yes',
      market_common_subtype: 'mainstream',
      pricing_basis_candidate: 'estimate',
      primary_driver_candidate: 'polyester_fdy',
      secondary_driver_candidate: 'pta',
      rayon_confirmed_candidate: 'yes',
      active_tracked_candidate: 'yes',
      status: 'approved',
      reviewer_notes: 'Sample row — delete after verification',
      claude_notes: 'Reference example for polyester FDY mainstream'
    },
    polyamide: {
      family: 'polyamide',
      subfamily: 'FDY',
      raw_label_examples: 'PA66 470D/140F HT',
      canonical_code: 'PA66_470D_140F_HT',
      display_name: 'PA66 470D/140F HT',
      form: 'filament',
      count_type: 'denier',
      denier: 470,
      filament_count: 140,
      ply: 1,
      luster: 'HT',
      recycle_flag: false,
      color_state: 'ECRU',
      tier_0_internal: true,
      tier_1_turkish: 1,
      tier_2_global: 2,
      tier_3_b2b: 3,
      tier_4_benchmark: 'estimate',
      source_names: 'Kordsa | Indorama | Alibaba',
      source_types: 'turkish_catalog | global_catalog | b2b_listing',
      evidence_urls: 'https://example.com/kordsa',
      has_commercial_use_case: true,
      market_common_candidate: 'yes',
      market_common_subtype: 'technical',
      pricing_basis_candidate: 'estimate',
      primary_driver_candidate: 'pa66_chip',
      rayon_confirmed_candidate: 'yes',
      active_tracked_candidate: 'yes',
      status: 'approved',
      reviewer_notes: 'Sample row — delete after verification',
      claude_notes: 'Reference example for high-denier industrial PA66'
    },
    viscose: {
      family: 'viscose',
      subfamily: 'staple_ring',
      raw_label_examples: 'Viscose Ne 30/1 ring spun ecru',
      canonical_code: 'VIS_NE30_1_RING',
      display_name: 'Viscose Ne 30/1 Ring',
      form: 'spun',
      count_type: 'Ne',
      ne_count: 30,
      ply: 1,
      recycle_flag: false,
      color_state: 'ECRU',
      tier_0_internal: false,
      tier_1_turkish: 0,
      tier_2_global: 2,
      tier_3_b2b: 3,
      tier_4_benchmark: 'proxy',
      source_names: 'Lenzing | Birla | Alibaba',
      source_types: 'global_catalog | global_catalog | b2b_listing',
      evidence_urls: 'https://example.com/lenzing-viscose',
      has_commercial_use_case: true,
      market_common_candidate: 'pending',
      pricing_basis_candidate: 'proxy',
      primary_driver_candidate: '_NEW:viscose_staple',
      rayon_confirmed_candidate: 'unsure',
      active_tracked_candidate: 'pending',
      status: 'research_filled',
      claude_notes: 'New driver _NEW:viscose_staple needed — no current dim_material slug'
    },
    modal: {
      family: 'modal',
      subfamily: 'staple_ring',
      raw_label_examples: 'Modal Ne 40/1 ring spun',
      canonical_code: 'MOD_NE40_1_RING',
      display_name: 'Modal Ne 40/1 Ring',
      form: 'spun',
      count_type: 'Ne',
      ne_count: 40,
      ply: 1,
      recycle_flag: false,
      color_state: 'ECRU',
      tier_0_internal: false,
      tier_1_turkish: 0,
      tier_2_global: 1,
      tier_3_b2b: 2,
      tier_4_benchmark: 'proxy',
      source_names: 'Lenzing | Alibaba',
      source_types: 'global_catalog | b2b_listing',
      evidence_urls: 'https://example.com/lenzing-modal',
      has_commercial_use_case: true,
      market_common_candidate: 'pending',
      pricing_basis_candidate: 'proxy',
      primary_driver_candidate: '_NEW:modal_staple',
      rayon_confirmed_candidate: 'unsure',
      active_tracked_candidate: 'pending',
      status: 'research_filled',
      claude_notes: 'Modal subfamily — Lenzing brand reference; needs Turkish catalog confirmation'
    },
    blend: {
      family: 'blend',
      subfamily: 'staple_ring',
      raw_label_examples: 'PV 65/35 Ne 30/1 ring',
      canonical_code: 'PV_NE30_1_65_35',
      display_name: 'PV 65/35 Ne 30/1',
      form: 'blend',
      count_type: 'Ne',
      ne_count: 30,
      ply: 1,
      recycle_flag: false,
      color_state: 'ECRU',
      blend_ratio_json: '{"PES":65,"VIS":35}',
      tier_0_internal: false,
      tier_1_turkish: 1,
      tier_2_global: 2,
      tier_3_b2b: 4,
      tier_4_benchmark: 'estimate',
      source_names: 'Sanko | Lenzing | Indorama | Alibaba',
      source_types: 'turkish_catalog | global_catalog | global_catalog | b2b_listing',
      evidence_urls: 'https://example.com/sanko-pv',
      has_commercial_use_case: true,
      market_common_candidate: 'pending',
      market_common_subtype: 'mainstream',
      pricing_basis_candidate: 'estimate',
      primary_driver_candidate: 'polyester_fdy',
      secondary_driver_candidate: '_NEW:viscose_staple',
      rayon_confirmed_candidate: 'unsure',
      active_tracked_candidate: 'pending',
      status: 'research_filled',
      claude_notes: 'Weighted blend pricing: 0.65 * polyester_fdy + 0.35 * viscose_staple'
    }
  };
  return samples[family] || {};
}

// ============================================================================
// SUMMARY TAB
// ============================================================================

function buildSummaryTab_(ss) {
  const sheet = ss.insertSheet(SUMMARY_TAB);

  // Header columns — 10 fields per B2.1 design
  const headers = [
    'family',
    'canonical_code',
    'display_name',
    'evidence_strength',
    'meets_2_of_5_rule',
    'market_common_candidate',
    'pricing_basis_candidate',
    'rayon_confirmed_candidate',
    'active_tracked_candidate',
    'status'
  ];

  sheet.setColumnWidths(1, headers.length, 150);
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(1, 1, 1, headers.length)
    .setFontWeight('bold')
    .setBackground('#d9d9d9')
    .setHorizontalAlignment('center');
  sheet.setFrozenRows(1);

  // Stack rows from each family tab using QUERY + UNION via curly brace stacking
  // Column letters in family tabs:
  //   family = A, canonical_code = D, display_name = E,
  //   evidence_strength = AB, meets_2_of_5_rule = AE,
  //   market_common_candidate = AF, pricing_basis_candidate = AK,
  //   rayon_confirmed_candidate = AN, active_tracked_candidate = AO,
  //   status = AP
  // We build per-family ranges and stack them.
  const formula = buildSummaryStackFormula_();
  sheet.getRange(2, 1).setFormula(formula);
}

function buildSummaryStackFormula_() {
  // For each family, we need a virtual array of:
  // [family, canonical_code, display_name, evidence_strength, meets_2_of_5_rule,
  //  market_common_candidate, pricing_basis_candidate, rayon_confirmed_candidate,
  //  active_tracked_candidate, status]
  //
  // Source columns in family tab (1-based):
  //   1=A family, 4=D canonical_code, 5=E display_name,
  //   28=AB evidence_strength, 31=AE meets_2_of_5_rule,
  //   32=AF market_common_candidate, 35=AK pricing_basis_candidate,
  //   38=AN rayon_confirmed_candidate, 39=AO active_tracked_candidate,
  //   40=AP status
  //
  // We use QUERY for filtering out empty rows: WHERE D is not null

  const cols = 'A, D, E, AB, AE, AF, AK, AN, AO, AP';
  const parts = FAMILY_TABS.map(f => `QUERY(${f}!A2:AP1000, "select ${cols} where D is not null", 0)`);
  // IFERROR wrap to avoid #N/A when no data
  const wrapped = parts.map(p => `IFERROR(${p}, {"","","","","","","","","",""})`);
  return `=QUERY({${wrapped.join('; ')}}, "select * where Col2 <> ''", 0)`;
}
