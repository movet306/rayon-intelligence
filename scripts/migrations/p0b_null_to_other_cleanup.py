"""Phase E P0-B step 3/3: legacy NULL -> OTHER cleanup.

Brings existing data into compliance with new no-nulls policy after
P0-B steps 1-2 deployed new schema + prompt + validation.

Idempotent: safe to re-run.
"""
import os, psycopg2

if 'DATABASE_URL' not in os.environ and 'RAYON_DATABASE_URL' in os.environ:
    os.environ['DATABASE_URL'] = os.environ['RAYON_DATABASE_URL']

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

cur.execute("UPDATE market_signals SET signal_category = 'OTHER' WHERE signal_category IS NULL")
print(f"signal_category: {cur.rowcount} rows updated")

cur.execute("UPDATE market_signals SET signal_priority_profile = 'OTHER' WHERE signal_priority_profile IS NULL")
print(f"signal_priority_profile: {cur.rowcount} rows updated")

conn.commit()
cur.close()
conn.close()
print("Cleanup complete.")