"""P0-D.1 backfill: 23 articles set to NULL for re-analysis under new 0.20 threshold.

Date: 8 May 2026 (Phase E P0-D.1)
Context: Diagnostic revealed 23 articles with relevance_score >= 0.20 that
were not promoted to market_signals (17 stuck at 0.40 from system inception
on 2026-04-09, 6 in the 0.20-0.24 band that fell below old 0.25 threshold).

Strategy: Set relevance_score=NULL for these candidates so the next
llm_analyzer.py run picks them up via fetch_unanalyzed() and re-promotes
under the new RELEVANCE_THRESHOLD=0.20.

Idempotent: WHERE clause filters to articles NOT already in market_signals,
so re-running this script is safe (no double-count, no overwrites).
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
            WHERE n.relevance_score >= 0.20 AND m.id IS NULL
        )
        RETURNING id
    """)
    nulled = len(cur.fetchall())
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM news_items WHERE relevance_score IS NULL")
    pending = cur.fetchone()[0]

    print(f"Set NULL: {nulled} articles")
    print(f"Total NULL pending re-analyze: {pending}")
    print(f"Estimated LLM cost: ~${pending * 0.0004:.4f}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()