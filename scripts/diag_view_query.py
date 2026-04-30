"""
diag_view_query.py - Isolate where the 500 error originates.

Tests three queries separately:
  1. SELECT * FROM v_active_signals  (view alone)
  2. SELECT ... FROM v_active_signals ORDER BY ...  (endpoint exact query)
  3. The endpoint's full SQL string

Whichever fails first shows where the bug is.
"""
import os
import sys
import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("[X] DATABASE_URL not set"); sys.exit(1)

conn = psycopg2.connect(db_url)
cur = conn.cursor()

print("=" * 70)
print("Test 1: bare view query")
print("=" * 70)
try:
    cur.execute("SELECT COUNT(*) FROM v_active_signals")
    print(f"[OK] count = {cur.fetchone()[0]}")
except Exception as e:
    print(f"[X] {type(e).__name__}: {e}")
    conn.rollback()

print()
print("=" * 70)
print("Test 2: view with select-all and limit")
print("=" * 70)
try:
    cur.execute("SELECT * FROM v_active_signals LIMIT 2")
    rows = cur.fetchall()
    print(f"[OK] {len(rows)} rows")
    cols = [d[0] for d in cur.description]
    print(f"[OK] columns: {cols}")
except Exception as e:
    print(f"[X] {type(e).__name__}: {e}")
    conn.rollback()

print()
print("=" * 70)
print("Test 3: endpoint's exact SQL")
print("=" * 70)
sql = """
    SELECT
        id,
        signal_date::text        AS signal_date,
        signal_type,
        chain,
        material_slug,
        upstream_slug,
        downstream_slug,
        severity,
        time_horizon,
        confidence_tier,
        value_pct::float         AS value_pct,
        explanation,
        business_implication,
        turkey_lag_min,
        turkey_lag_max,
        suppressed
    FROM v_active_signals
    ORDER BY
        CASE severity
            WHEN 'critical' THEN 1
            WHEN 'high'     THEN 2
            WHEN 'medium'   THEN 3
            ELSE 4
        END,
        signal_date DESC
"""
try:
    cur.execute(sql)
    rows = cur.fetchall()
    print(f"[OK] {len(rows)} rows returned by endpoint SQL")
    if rows:
        print(f"     first row severity: {rows[0][7]}")
        print(f"     last row severity:  {rows[-1][7]}")
except Exception as e:
    print(f"[X] {type(e).__name__}: {e}")
    conn.rollback()

cur.close()
conn.close()
