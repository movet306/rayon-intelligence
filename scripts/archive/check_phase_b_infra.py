"""Phase B infra verification — actual queries with correct columns."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

print("=" * 70)
print("1) price_signals — cotton & ICE presence")
print("=" * 70)

cur.execute("""
    SELECT material,
           MAX(period)     AS last_period,
           MAX(scraped_at) AS last_scraped,
           COUNT(*)        AS rows
    FROM price_signals
    WHERE material ILIKE '%cotton%'
       OR material ILIKE '%ice%'
       OR material ILIKE '%pamuk%'
    GROUP BY material
    ORDER BY material
""")
rows = cur.fetchall()
if not rows:
    print("  ⚠ No cotton/ICE rows found in price_signals")
else:
    for mat, last_p, last_s, n in rows:
        print(f"  {mat:30s} last_period={last_p}  last_scraped={last_s}  rows={n}")

print("\n" + "=" * 70)
print("2) price_signals — today's scraping activity")
print("=" * 70)

cur.execute("""
    SELECT material, source, COUNT(*) AS n, MAX(scraped_at) AS latest
    FROM price_signals
    WHERE scraped_at >= CURRENT_DATE
    GROUP BY material, source
    ORDER BY material
""")
rows = cur.fetchall()
if not rows:
    print("  ⚠ No rows scraped today")
else:
    print(f"  Today's scrape: {len(rows)} distinct (material, source) pairs")
    for mat, src, n, latest in rows:
        print(f"    {mat:30s} [{src:15s}] rows={n}  latest={latest}")

print("\n" + "=" * 70)
print("3) price_metrics_daily — cotton presence")
print("=" * 70)

cur.execute("""
    SELECT material,
           MAX(metric_date)     AS last_date,
           MAX(confidence_tier) AS tier,
           COUNT(*)             AS rows
    FROM price_metrics_daily
    WHERE material ILIKE '%cotton%'
       OR material ILIKE '%ice%'
       OR material ILIKE '%pamuk%'
    GROUP BY material
    ORDER BY material
""")
rows = cur.fetchall()
if not rows:
    print("  ⚠ No cotton metrics rows")
else:
    for mat, last, tier, n in rows:
        print(f"  {mat:30s} last={last}  tier={tier}  rows={n}")

print("\n" + "=" * 70)
print("4) price_intelligence_signals — today check")
print("=" * 70)

cur.execute("""
    SELECT signal_date, signal_type, material_slug, severity,
           LEFT(explanation, 70) AS expl
    FROM price_intelligence_signals
    ORDER BY signal_date DESC, created_at DESC
""")
rows = cur.fetchall()
for d, t, mat, sev, expl in rows:
    print(f"  {d}  [{sev:8s}]  {t:15s}  {mat:20s}  {expl}")

conn.close()
print("\n" + "=" * 70)
print("DONE")
print("=" * 70)