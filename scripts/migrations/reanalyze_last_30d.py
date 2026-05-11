"""P0-D.3 backfill: reset relevance_score for non-promoted articles in last 30 days.

Date: 11 May 2026 (Phase E P0-D.3)
Context: After P0-D.2 prompt revision (commit before this), existing
news_items from last 30 days were scored under the OLD prompt and most
were filtered out. Reset their relevance_score=NULL so the next daily
run re-analyzes them under the NEW Rayon-aware prompt.

Strategy: Only touch articles NOT promoted to market_signals.
This preserves all 122 existing market_signals rows.

Idempotent: Filter 'WHERE m.id IS NULL AND relevance_score IS NOT NULL'
means re-running this is a no-op (already-NULLed articles are skipped).

Cost estimate: ~300 articles * ~$0.0004 = ~$0.12 one-time LLM cost
on next daily run.
"""
import os
import psycopg2


def main():
    url = os.environ.get("RAYON_DATABASE_URL") or os.environ["DATABASE_URL"]
    conn = psycopg2.connect(url)
    cur = conn.cursor()

    cur.execute("""
        UPDATE news_items SET relevance_score = NULL
        WHERE id IN (
            SELECT n.id FROM news_items n
            LEFT JOIN market_signals m ON m.source_id = n.id
            WHERE n.scraped_at >= NOW() - INTERVAL '30 days'
              AND m.id IS NULL
              AND n.relevance_score IS NOT NULL
        )
        RETURNING id
    """)
    nulled = len(cur.fetchall())
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM news_items WHERE relevance_score IS NULL")
    pending = cur.fetchone()[0]

    print(f"Set NULL: {nulled} articles")
    print(f"Total pending re-analyze: {pending}")
    print(f"Estimated LLM cost: ~${pending * 0.0004:.4f}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()