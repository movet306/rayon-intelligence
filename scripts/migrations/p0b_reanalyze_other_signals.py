"""P0-B follow-up: reanalyze the 99 OTHER signals to get refined categories.

Strategy:
1. Find article IDs whose signal_category = 'OTHER' in last 30 days
2. DELETE those signals (so reanalysis doesn't create duplicates)
3. Reset news_items.relevance_score = NULL on those articles
4. Run analyze(limit=200) -- LLM rescores with new schema
5. Verify new distribution
"""
import os, sys
sys.path.insert(0, r'C:\Projects\rayon-intelligence')

if 'DATABASE_URL' not in os.environ and 'RAYON_DATABASE_URL' in os.environ:
    os.environ['DATABASE_URL'] = os.environ['RAYON_DATABASE_URL']

import psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

# Step 1: Find OTHER signal source articles (last 30d)
print("=== Step 1: Find articles producing OTHER signals ===")
cur.execute("""
    SELECT DISTINCT source_id::text
    FROM market_signals
    WHERE signal_category = 'OTHER'
      AND source_table = 'news_items'
      AND detected_at > NOW() - INTERVAL '30 days'
""")
article_ids = [row[0] for row in cur.fetchall()]
print(f"  Found {len(article_ids)} unique articles")

if not article_ids:
    print("  Nothing to do. Exiting.")
    sys.exit(0)

# Step 2: Count signals to be deleted (only OTHER, to preserve non-OTHER from same articles)
cur.execute("""
    SELECT COUNT(*)
    FROM market_signals
    WHERE signal_category = 'OTHER'
      AND source_table = 'news_items'
      AND detected_at > NOW() - INTERVAL '30 days'
""")
to_delete = cur.fetchone()[0]
print(f"  Will delete {to_delete} OTHER signals (non-OTHER from same articles preserved)")

# Step 3: DELETE old OTHER signals
print()
print("=== Step 2: DELETE old OTHER signals ===")
cur.execute("""
    DELETE FROM market_signals
    WHERE signal_category = 'OTHER'
      AND source_table = 'news_items'
      AND detected_at > NOW() - INTERVAL '30 days'
""")
print(f"  Deleted: {cur.rowcount} rows")

# Step 4: Reset relevance_score to trigger reanalysis
print()
print("=== Step 3: Reset relevance_score on those articles ===")
cur.execute("""
    UPDATE news_items
    SET relevance_score = NULL
    WHERE id::text = ANY(%s)
""", (article_ids,))
print(f"  Reset: {cur.rowcount} articles")

conn.commit()

# Step 5: Run analyze
print()
print(f"=== Step 4: Run analyze (estimated ~{len(article_ids)*8//60}-{len(article_ids)*10//60} min) ===")
from scrapers.llm_analyzer import analyze
result = analyze(limit=len(article_ids) + 10, dry_run=False)
print()
print(f"Result: {result}")
print(f"Cost: ${result.get('total_cost_usd', 0):.4f}")

# Step 6: Verify
print()
print("=== Step 5: New distribution (last 30d) ===")
cur.execute("""
    SELECT signal_category, COUNT(*) as n
    FROM market_signals
    WHERE detected_at > NOW() - INTERVAL '30 days'
    GROUP BY signal_category
    ORDER BY n DESC
""")
for cat, n in cur.fetchall():
    print(f"  {cat or '(null)':25s} {n}")

print()
print("signal_priority_profile (last 30d):")
cur.execute("""
    SELECT signal_priority_profile, COUNT(*) as n
    FROM market_signals
    WHERE detected_at > NOW() - INTERVAL '30 days'
    GROUP BY signal_priority_profile
    ORDER BY n DESC
""")
for spp, n in cur.fetchall():
    print(f"  {spp or '(null)':25s} {n}")

print()
print("Action tag distribution (last 30d, non-MONITOR):")
cur.execute("""
    SELECT action_tag, COUNT(*) as n
    FROM market_signals
    WHERE detected_at > NOW() - INTERVAL '30 days'
      AND action_tag IS NOT NULL
      AND action_tag != 'MONITOR'
    GROUP BY action_tag
    ORDER BY n DESC
""")
rows = cur.fetchall()
if rows:
    for tag, n in rows:
        print(f"  {tag:25s} {n}")
else:
    print("  (no non-MONITOR action tags)")

cur.close()
conn.close()
print()
print("Done.")