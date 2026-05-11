"""Phase E P0-C: reclassify TDU Savunma from competitor to customer.

Memory note from previous session: TDU Savunma is actually a customer of
Rayon Tekstil, not a competitor. Was likely auto-classified into the
competitor monitor list during initial seeding.
"""
import os, psycopg2

conn = psycopg2.connect(os.environ['RAYON_DATABASE_URL'])
cur = conn.cursor()

# 1) Diagnostic: find TDU Savunma's current state
print('=== TDU Savunma search ===')
cur.execute("""
    SELECT id, name, category, country, notes
    FROM companies
    WHERE LOWER(name) LIKE '%tdu%'
       OR LOWER(name) LIKE '%savunma%'
    ORDER BY name
""")
rows = cur.fetchall()
if not rows:
    print('  No match found -- aborting')
    raise SystemExit(1)

for row in rows:
    print(f'  {row}')

# 2) Show category distribution
print()
print('=== Current category distribution ===')
cur.execute("""
    SELECT category, COUNT(*) AS n
    FROM companies
    GROUP BY category
    ORDER BY n DESC
""")
for cat, n in cur.fetchall():
    print(f'  {cat or "(null)":15s} {n}')

# 3) UPDATE if needed
print()
print('=== Applying reclassification ===')
cur.execute("""
    UPDATE companies
    SET category = 'customer'
    WHERE LOWER(name) LIKE '%tdu%'
       OR LOWER(name) LIKE '%savunma%'
    RETURNING id, name, category
""")
updated = cur.fetchall()
for row in updated:
    print(f'  Updated: {row}')

if not updated:
    print('  No rows updated -- already customer or name mismatch')

conn.commit()

# 4) Verify
print()
print('=== Verify post-update ===')
cur.execute("""
    SELECT name, category
    FROM companies
    WHERE LOWER(name) LIKE '%tdu%'
       OR LOWER(name) LIKE '%savunma%'
""")
for row in cur.fetchall():
    print(f'  {row}')

cur.close()
conn.close()
print()
print('Done.')