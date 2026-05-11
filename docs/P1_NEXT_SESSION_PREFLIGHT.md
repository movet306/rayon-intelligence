# P1 Next-Session Pre-Flight Checklist

> **Status:** Auto-generated 11 May 2026 (end of P0 closure session)
> **Reference design:** [P1_ENTITY_REFACTOR_DESIGN.md](./P1_ENTITY_REFACTOR_DESIGN.md)
> **Estimated total:** 6-8 hours over 2 sessions

This is a copy-paste runbook. Each section can be pasted directly into PowerShell.

---

## 0. Session Setup (5 min)

```powershell
cd C:\Projects\rayon-intelligence
conda activate rayon-dashboard
git status                    # should be clean
git pull origin main          # sync any remote changes
git log --oneline -5          # confirm last commit is 267b6c4 or later
```

**Last commit to verify:** `267b6c4 Regen Migration 012: add Sympatex + fix entity_type...`

---

## 1. Pre-Migration Safety: Schema Snapshot (5 min)

Capture current state before any destructive change:

```powershell
$code = @"
import os, psycopg2
if 'DATABASE_URL' not in os.environ:
    os.environ['DATABASE_URL'] = os.environ['RAYON_DATABASE_URL']
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

cur.execute('SELECT COUNT(*) FROM companies')
print(f'companies count: {cur.fetchone()[0]}')

cur.execute('SELECT COUNT(*) FROM market_signals')
print(f'market_signals count: {cur.fetchone()[0]}')

cur.execute(\"\"\"
  SELECT column_name FROM information_schema.columns
  WHERE table_name='market_signals' AND column_name IN ('company_id','entity_id')
\"\"\")
print(f'market_signals.company_id/entity_id: {[r[0] for r in cur.fetchall()]}')
"@
$pPath = "$PWD\_snapshot.py"
[System.IO.File]::WriteAllText($pPath, $code, [System.Text.UTF8Encoding]::new($false))
python $pPath
Remove-Item $pPath
```

**Expected baseline:** companies=32, market_signals=126, column=`company_id`.

---

## 2. P1 Step 1: Code Updates BEFORE Mig 010 Apply (3 h)

Migration 010 renames `companies` -> `entities` and `company_id` -> `entity_id`. The backwards-compat VIEW keeps `dashboard/server.py` working (only 2 hits) but **scrapers will break** because they do INSERTs and need the new column names.

**Files to update (from today's audit):**

| File | Hits | What to change |
|---|---|---|
| `scrapers/competitor_monitor.py` | 26 | Replace `companies` -> `entities`, `company_id` -> `entity_id` everywhere |
| `scrapers/llm_analyzer.py` | 20 | Same + rename `match_companies()` function to `match_entities()` |
| `scrapers/texhibition_scraper.py` | 11 | Same |
| `dashboard/server.py` | 2 | Optional: update for clarity, but VIEW keeps it working |
| `scrapers/telegram_reporter.py` | 1 | Same |
| `db/seed_companies.py` | 2 | DO NOT EDIT - replaced by Migration 012 |
| `dashboard/app.py` | 1 | INVESTIGATE - may be legacy/dead code |

After edits:
```powershell
git add scrapers/ dashboard/
git commit -m "Phase E P1 step 1: rename companies->entities, company_id->entity_id in scrapers"
git push origin main
```

---

## 3. Apply Migration 010 (15 min)

**Pre-flight:** Stop any running cron / scraper job. Daily scraper runs at 11:00 Istanbul - schedule this work AFTER it has completed or BEFORE it triggers.

```powershell
$code = @"
import os
if 'DATABASE_URL' not in os.environ:
    os.environ['DATABASE_URL'] = os.environ['RAYON_DATABASE_URL']
import psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
with open(r'C:\Projects\rayon-intelligence\migrations\010_rename_companies_to_entities.sql') as f:
    sql = f.read()
cur.execute(sql)
conn.commit()
print('Migration 010 applied.')
"@
$pPath = "$PWD\_apply010.py"
[System.IO.File]::WriteAllText($pPath, $code, [System.Text.UTF8Encoding]::new($false))
python $pPath
Remove-Item $pPath
```

**Verify** (run after apply):
- `SELECT COUNT(*) FROM entities;` -> 32
- `SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type;` -> all `competitor_tr`
- `SELECT COUNT(*) FROM companies;` -> 32 (via VIEW)
- Smoke-test API: `Invoke-RestMethod http://127.0.0.1:8000/api/signals` should still return signals

**Rollback if needed:**
```sql
BEGIN;
DROP VIEW IF EXISTS companies;
ALTER TABLE market_signals RENAME COLUMN entity_id TO company_id;
ALTER TABLE entities DROP CONSTRAINT IF EXISTS chk_entity_type;
ALTER TABLE entities DROP COLUMN IF EXISTS entity_type, DROP COLUMN IF EXISTS geography;
ALTER TABLE entities RENAME TO companies;
COMMIT;
```

---

## 4. Apply Migration 011 (10 min)

Adds 6 exposure layer columns. Pure additive, no rename.

```powershell
$code = @"
import os
if 'DATABASE_URL' not in os.environ:
    os.environ['DATABASE_URL'] = os.environ['RAYON_DATABASE_URL']
import psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
with open(r'C:\Projects\rayon-intelligence\migrations\011_add_exposure_fields.sql') as f:
    cur.execute(f.read())
conn.commit()
print('Migration 011 applied.')
"@
$pPath = "$PWD\_apply011.py"
[System.IO.File]::WriteAllText($pPath, $code, [System.Text.UTF8Encoding]::new($false))
python $pPath
Remove-Item $pPath
```

**Verify:** all 6 columns exist on market_signals (rayon_why_it_matters, affected_business_line, affected_material_family, commercial_exposure_type, entity_name, entity_role). All NULL initially - backfilled in step 6.

---

## 5. Apply Migration 012 (5 min)

Seeds 23 new entities. Requires Migration 010 already applied (entity_type column must exist + chk_entity_type constraint active).

```powershell
$code = @"
import os
if 'DATABASE_URL' not in os.environ:
    os.environ['DATABASE_URL'] = os.environ['RAYON_DATABASE_URL']
import psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
with open(r'C:\Projects\rayon-intelligence\migrations\012_seed_entities.sql', encoding='utf-8') as f:
    cur.execute(f.read())
conn.commit()
print('Migration 012 applied.')

cur.execute('SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type ORDER BY 2 DESC')
for row in cur.fetchall():
    print(f'  {row[0]:20s} {row[1]}')
"@
$pPath = "$PWD\_apply012.py"
[System.IO.File]::WriteAllText($pPath, $code, [System.Text.UTF8Encoding]::new($false))
python $pPath
Remove-Item $pPath
```

**Expected after apply:**
- competitor_tr: 32 (existing) + 7 (new) = 39
- supplier: 8
- competitor_intl: 4
- association: 3
- regulator: 1
- **Total entities: 55**

---

## 6. P1 Step 4-6: LLM Prompt + Backfill + Smoke Test (3 h)

See `docs/P1_ENTITY_REFACTOR_DESIGN.md` sections:
- **LLM Prompt Updates** - 6 new JSON fields in prompt schema
- **Python Code Changes** - VALID_* constants, validation with OTHER fallbacks, INSERT 21->27 columns
- **Backfill Strategy** - Phase 1 heuristic SQL (no LLM cost) + Phase 2 optional LLM reanalysis

---

## 7. Dashboard UI Update (1-2 h)

Two gaps to close:

1. **signal_priority_profile rendering** - server.py now exposes it (today's commit 50cebee), but app.v5.js doesn't render it. Add badge in signal-meta-right wrapper.
2. **Exposure fields rendering** - after Mig 011 backfill, render rayon_why_it_matters, commercial_exposure_type as primary card body content.

Cache buster bump: v6 -> v7 in index.html.

---

## 8. Smoke Tests Checklist

After ALL above complete:
- [ ] Daily scraper runs successfully (test manually before 11:00 Istanbul cron)
- [ ] Weekly Competitor Monitor (Sunday 06:00 cron) - already validated 11 May via secret fix
- [ ] Dashboard renders signal_priority_profile badges
- [ ] /api/signals returns 27 fields including the 6 new exposure ones
- [ ] No legacy 'companies' references remain (`Select-String -Path scrapers,dashboard -Pattern 'companies' -Include *.py`)
- [ ] /api/signal_stats unchanged behavior

---

## Notes from 11 May Session

- ChatGPT analysis identified 8 gaps; gap #1 (signal_priority_profile + required fields) is closed.
- The Teijin polyester +20% RISK signal is the system's first action-grade signal. Verify it still surfaces post-P1.
- LLM prompt sometimes returns OTHER for signal_priority_profile when COST/EXPORT/etc. is obvious - improve prompt examples in P1 step 4.
- 30 commit/day was sustainable but exceptional. Aim for 10-15 commits in next session.
