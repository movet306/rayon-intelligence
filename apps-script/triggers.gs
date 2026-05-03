/**
 * Yarn Intelligence — Phase B2.2-step2 Timestamp Triggers
 *
 * Purpose: Automate timestamp fields on edit:
 *   - last_updated_at  → set to current ISO timestamp on every qualifying edit
 *   - last_updated_by  → set to mapped role on every qualifying edit
 *   - created_at       → set ONCE on first qualifying edit of a row, then frozen
 *
 * Scope:
 *   - Runs only on family tabs (polyester, polyamide, viscose, modal, blend)
 *   - Skips _summary tab
 *   - Skips header row (row 1)
 *   - Skips edits to the 3 timestamp columns themselves (avoids feedback loops)
 *   - Skips edits to derived (formula) columns
 *   - Single-row edits/pastes: supported
 *   - Multi-row pastes: ignored (no-op) for now
 *
 * Trigger setup:
 *   This script defines two functions:
 *     - onEdit(e)        — Sheets simple trigger, auto-fires on edits
 *     - installTriggers_ — manual installer for installable trigger version (optional)
 *
 *   Simple onEdit(e) does NOT have access to e.user.getEmail() reliably
 *   in all cases. To get editor email, an INSTALLABLE trigger is required.
 *   We install one via installTriggers_().
 *
 * Usage:
 *   1. Save this file in the same Apps Script project as setup-evidence-sheet.gs
 *      (named triggers.gs, separate file)
 *   2. Run installTriggers_ ONCE (manually) to set up the installable trigger
 *   3. After that, every edit on a family tab automatically updates timestamps
 *
 * Reference:
 *   docs/yarn-intelligence/phase-b2-evidence-sheet-design.md (Section 2 → Review category)
 */

// ============================================================================
// CONFIGURATION
// ============================================================================

// Family tabs that should trigger timestamp updates
const TRIGGER_FAMILY_TABS = ['polyester', 'polyamide', 'viscose', 'modal', 'blend'];

// Column indices (1-based) for timestamp fields in the 45-column schema
// These match the column order in setup-evidence-sheet.gs COLUMNS array
const COL_LAST_UPDATED_BY = 43;  // AQ
const COL_LAST_UPDATED_AT = 44;  // AR
const COL_CREATED_AT      = 45;  // AS

// Derived (formula) column indices — edits to these never trigger timestamps
// (they shouldn't fire onEdit anyway, but defensive guard)
const DERIVED_COL_INDICES = [
  10,  // J  denier_class
  27,  // AA repeat_count
  28,  // AB evidence_strength
  29,  // AC source_count_total
  31   // AE meets_2_of_5_rule
];

// Email to role mapping
// Extend this when more editors join (e.g., agent service accounts)
const EDITOR_EMAIL_MAP = {
  'mertovet306@gmail.com': 'mert'
};

// Default role when email is not mapped
const UNKNOWN_EDITOR_ROLE = 'unknown_editor';

// Timestamp format — ISO-like without timezone suffix
// Format follows Apps Script Utilities.formatDate() pattern
const TIMESTAMP_FORMAT = "yyyy-MM-dd'T'HH:mm:ss";

// ============================================================================
// MAIN TRIGGER HANDLER
// ============================================================================

/**
 * Installable onEdit handler.
 * This function is bound via installTriggers_() to fire on every edit.
 *
 * Behavior:
 *   - Filters out edits that should not update timestamps
 *   - Updates last_updated_at + last_updated_by on every qualifying edit
 *   - Sets created_at only if it is currently empty
 */
function onEditHandler(e) {
  try {
    if (!e || !e.range) return;

    const sheet = e.range.getSheet();
    const sheetName = sheet.getName();

    // Skip _summary and any non-family tab
    if (TRIGGER_FAMILY_TABS.indexOf(sheetName) === -1) return;

    const editedRow = e.range.getRow();
    const editedCol = e.range.getColumn();
    const numRows = e.range.getNumRows();

    // Skip header row edits
    if (editedRow === 1) return;

    // Skip multi-row paste — for now, no-op (decision per design doc)
    if (numRows > 1) return;

    // Skip if edit is in any of the 3 timestamp columns themselves
    // (prevents feedback loop when this very script writes timestamps)
    if (editedCol === COL_LAST_UPDATED_BY ||
        editedCol === COL_LAST_UPDATED_AT ||
        editedCol === COL_CREATED_AT) {
      return;
    }

    // Skip if edit is in a derived (formula) column — defensive
    if (DERIVED_COL_INDICES.indexOf(editedCol) !== -1) return;

    // All filters passed — proceed with timestamp update
    updateTimestamps_(sheet, editedRow, e);

  } catch (err) {
    // Apps Script onEdit failures are silent by default; log for debugging
    Logger.log('onEditHandler error: ' + err.message);
  }
}

// ============================================================================
// TIMESTAMP UPDATE LOGIC
// ============================================================================

/**
 * Apply timestamp updates to a single row.
 *
 * @param {Sheet} sheet - The sheet where the edit occurred
 * @param {number} row - The 1-based row index that was edited
 * @param {Object} e - The onEdit event object
 */
function updateTimestamps_(sheet, row, e) {
  const now = new Date();
  const timestamp = Utilities.formatDate(
    now,
    sheet.getParent().getSpreadsheetTimeZone(),
    TIMESTAMP_FORMAT
  );

  const editorRole = resolveEditorRole_(e);

  // Always update last_updated_at and last_updated_by
  sheet.getRange(row, COL_LAST_UPDATED_AT).setValue(timestamp);
  sheet.getRange(row, COL_LAST_UPDATED_BY).setValue(editorRole);

  // Set created_at only if currently empty (frozen on first write)
  const createdAtCell = sheet.getRange(row, COL_CREATED_AT);
  const currentCreatedAt = createdAtCell.getValue();
  if (currentCreatedAt === '' || currentCreatedAt === null || currentCreatedAt === undefined) {
    createdAtCell.setValue(timestamp);
  }
}

/**
 * Resolve the editor's role from the edit event.
 * Falls back to UNKNOWN_EDITOR_ROLE if email is not in the map.
 */
function resolveEditorRole_(e) {
  let email = '';

  // e.user.getEmail() works for installable triggers when the user is in
  // the same domain or has explicitly granted access
  try {
    if (e && e.user && typeof e.user.getEmail === 'function') {
      email = e.user.getEmail();
    }
  } catch (err) {
    email = '';
  }

  // Fallback: ActiveUser
  if (!email) {
    try {
      email = Session.getActiveUser().getEmail();
    } catch (err) {
      email = '';
    }
  }

  if (!email) return UNKNOWN_EDITOR_ROLE;
  return EDITOR_EMAIL_MAP[email] || UNKNOWN_EDITOR_ROLE;
}

// ============================================================================
// TRIGGER INSTALLATION
// ============================================================================

/**
 * One-time installation of the installable onEdit trigger.
 * Run this manually after pasting the script.
 *
 * Idempotent: removes any existing onEditHandler triggers before installing
 * a fresh one. Safe to re-run after schema or behavior changes.
 */
function installTriggers_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  // Remove any existing triggers pointing to onEditHandler
  const existing = ScriptApp.getProjectTriggers();
  let removed = 0;
  existing.forEach(t => {
    if (t.getHandlerFunction() === 'onEditHandler') {
      ScriptApp.deleteTrigger(t);
      removed++;
    }
  });

  // Install fresh installable onEdit trigger
  ScriptApp.newTrigger('onEditHandler')
    .forSpreadsheet(ss)
    .onEdit()
    .create();

  Logger.log('Installed onEditHandler trigger. Removed ' + removed + ' old triggers.');
}

/**
 * Public installer — exposed for menu/manual run.
 */
function installTriggers() {
  installTriggers_();
}

/**
 * Public uninstaller — for cleanup if needed.
 */
function uninstallTriggers() {
  const existing = ScriptApp.getProjectTriggers();
  let removed = 0;
  existing.forEach(t => {
    if (t.getHandlerFunction() === 'onEditHandler') {
      ScriptApp.deleteTrigger(t);
      removed++;
    }
  });
  Logger.log('Removed ' + removed + ' onEditHandler triggers.');
}
