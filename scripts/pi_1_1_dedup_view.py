"""
pi_1_1_dedup_view.py - Apply v_active_signals migration and switch endpoint.

Two-step patch:

  Step 1: Run migrations/2026_04_29_pi_1_1_active_signals_view.sql against
          the live database. CREATE OR REPLACE VIEW is idempotent — safe
          to run multiple times.

  Step 2: Update dashboard/server.py so /api/price_intelligence_signals
          reads from v_active_signals (deduped) instead of
          price_intelligence_signals (raw).

Data safety:
  - The view is computed on read; raw table is untouched.
  - Reversal: DROP VIEW v_active_signals + revert the FROM clause.
  - The endpoint also keeps the same WHERE/ORDER clauses, but the view
    already filters last-14d and dedupes, so the effective behavior is
    "show the latest active signals, one per pattern".

Idempotent:
  - SQL: CREATE OR REPLACE VIEW
  - Python edit: detects whether server.py already points to v_active_signals
"""
import os
import sys
import time
from pathlib import Path

import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

REPO = Path(__file__).resolve().parent.parent
SQL = REPO / "migrations" / "2026_04_29_pi_1_1_active_signals_view.sql"
SERVER = REPO / "dashboard" / "server.py"
INDEX = REPO / "dashboard" / "static" / "index.html"


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: apply SQL migration
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 70)
print("Step 1: Apply v_active_signals view migration")
print("=" * 70)

if not SQL.exists():
    print(f"[X] Migration file missing: {SQL}")
    sys.exit(1)

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("[X] DATABASE_URL not set in environment or .env")
    sys.exit(1)

sql_text = SQL.read_text(encoding="utf-8")

with psycopg2.connect(db_url) as conn:
    with conn.cursor() as cur:
        cur.execute(sql_text)
    conn.commit()
    print("[OK]  Migration applied: CREATE OR REPLACE VIEW v_active_signals")

    # Verify the view is healthy and show before/after counts
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM price_intelligence_signals "
            "WHERE suppressed = FALSE AND signal_date >= NOW() - INTERVAL '14 days'"
        )
        raw_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM v_active_signals")
        view_count = cur.fetchone()[0]
        print(f"      Raw rows (last 14d, not suppressed): {raw_count}")
        print(f"      View rows (deduped):                 {view_count}")
        if raw_count > 0:
            saved = 100 * (raw_count - view_count) / raw_count
            print(f"      Reduction:                           {saved:.1f}%")


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: switch endpoint to read from view
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("Step 2: Switch /api/price_intelligence_signals endpoint to v_active_signals")
print("=" * 70)

src = SERVER.read_text(encoding="utf-8")

# The exact line we want to change. Anchored to the FROM clause inside the
# specific endpoint, identifiable because it's preceded by "suppressed".
OLD_FROM = "        FROM price_intelligence_signals\n"
NEW_FROM = "        FROM v_active_signals\n"

# We expect this exact string to appear ONCE in the file (inside the price
# intelligence signals endpoint). If it appears multiple times we must be
# more specific to avoid mis-edits.
occurrences = src.count(OLD_FROM)

if "FROM v_active_signals" in src:
    print("[skip] endpoint already reads from v_active_signals")
elif occurrences == 1:
    src = src.replace(OLD_FROM, NEW_FROM)
    SERVER.write_text(src, encoding="utf-8")
    print("[OK]  server.py: endpoint switched to FROM v_active_signals")
elif occurrences == 0:
    print("[X]  Could not find the expected FROM clause to swap.")
    print("     The endpoint may have been edited; inspect server.py around")
    print("     /api/price_intelligence_signals manually.")
    sys.exit(1)
else:
    print(f"[X]  Expected exactly one occurrence of the FROM clause to swap,")
    print(f"     found {occurrences}. Aborting to avoid mis-edits.")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: bump cache buster on app.v5.js (UI doesn't change, but signal feed
# response shape is identical and clients should fetch fresh /api/* calls)
# ─────────────────────────────────────────────────────────────────────────────
import re
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m:
    old_v = m.group(1)
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    INDEX.write_text(html, encoding="utf-8")
    print(f"[OK]  index.html: cache buster bumped {old_v} -> {ts}")


print()
print("Done.")
print()
print("Verify:")
print("  1. Restart uvicorn (Ctrl+C, then re-run uvicorn command)")
print("  2. curl test:")
print("       Invoke-RestMethod http://localhost:8000/api/price_intelligence_signals |"
      " Measure-Object | Select Count")
print(f"     Expected ~9 rows (down from {raw_count if 'raw_count' in dir() else '~30+'})")
print("  3. Browser: Ctrl+Shift+R on Price Intelligence")
print("     Feed should show one card per distinct signal pattern.")
print()
print("Reversal:")
print("  - DROP VIEW v_active_signals;")
print("  - Revert the FROM clause in server.py")
