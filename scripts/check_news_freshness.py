"""Check freshness of both news_items and market_signals."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

print("=" * 60)
print("NEWS_ITEMS (raw scraped articles)")
print("=" * 60)
cur.execute("""
    SELECT MAX(scraped_at)::date AS last_scrape,
           COUNT(*) AS total
    FROM news_items
""")
row = cur.fetchone()
print(f"Last scrape: {row[0]}   Total: {row[1]}")

cur.execute("""
    SELECT scraped_at::date AS d, source, COUNT(*) AS n
    FROM news_items
    WHERE scraped_at >= NOW() - INTERVAL '7 days'
    GROUP BY 1, 2 ORDER BY 1 DESC, 3 DESC
""")
print("\nLast 7 days by source:")
for d, src, n in cur.fetchall():
    print(f"  {d}  {src:25s} {n}")

print("\n" + "=" * 60)
print("MARKET_SIGNALS (LLM-analyzed signals)")
print("=" * 60)
cur.execute("""
    SELECT MAX(detected_at)::date AS last_detected,
           COUNT(*) AS total
    FROM market_signals
""")
row = cur.fetchone()
print(f"Last detected: {row[0]}   Total: {row[1]}")

cur.execute("""
    SELECT detected_at::date AS d, COUNT(*) AS n
    FROM market_signals
    WHERE detected_at >= NOW() - INTERVAL '7 days'
    GROUP BY 1 ORDER BY 1 DESC
""")
print("\nLast 7 days:")
for d, n in cur.fetchall():
    print(f"  {d}: {n} signals")

cur.execute("""
    SELECT signal_type, COUNT(*)
    FROM market_signals
    WHERE detected_at >= NOW() - INTERVAL '7 days'
    GROUP BY signal_type
    ORDER BY 2 DESC
""")
print("\nLast 7 days by signal_type:")
for t, n in cur.fetchall():
    print(f"  {t}: {n}")

conn.close()
