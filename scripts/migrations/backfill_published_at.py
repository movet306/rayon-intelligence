"""P0-A backfill: parse published_at from URL for existing NULL articles.

Uses _date_utils.parse_published_at with url-only (URL regex /YYYY/MM/DD/ fallback).
HTML re-fetch is NOT attempted -- if URL doesn't contain a date, that article
stays NULL. The cleanly-scraped articles going forward will have proper
published_at via the patched scrapers.

This script is idempotent: WHERE published_at IS NULL filter means re-runs
are no-ops for already-filled rows.
"""
import os
import sys
from pathlib import Path
import psycopg2

# Helper module is in scrapers/ -- add to path
SCRAPERS_DIR = Path(__file__).resolve().parent.parent.parent / "scrapers"
sys.path.insert(0, str(SCRAPERS_DIR))
from _date_utils import parse_published_at  # noqa: E402


def main():
    db_url = os.environ.get("RAYON_DATABASE_URL") or os.environ["DATABASE_URL"]
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM news_items WHERE published_at IS NULL")
    null_before = cur.fetchone()[0]
    print(f"news_items with published_at IS NULL: {null_before}")

    cur.execute("""
        SELECT id, url FROM news_items
        WHERE published_at IS NULL
        ORDER BY scraped_at DESC
    """)
    rows = cur.fetchall()

    updated = 0
    by_source = {}
    for row_id, item_url in rows:
        dt = parse_published_at(url=item_url)
        if dt:
            cur.execute(
                "UPDATE news_items SET published_at = %s WHERE id = %s",
                (dt, row_id)
            )
            updated += 1

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM news_items WHERE published_at IS NULL")
    null_after = cur.fetchone()[0]

    fill_rate = (null_before - null_after) / null_before * 100 if null_before > 0 else 0
    print()
    print(f"Updated:  {updated}")
    print(f"NULL after backfill: {null_after}")
    print(f"Fill rate from URL regex: {fill_rate:.1f}%")

    # Per-source breakdown
    print()
    print("=== Fill rate by source ===")
    cur.execute("""
        SELECT source,
               COUNT(*) FILTER (WHERE published_at IS NOT NULL) AS filled,
               COUNT(*) AS total
        FROM news_items GROUP BY source ORDER BY source
    """)
    for source, filled, total in cur.fetchall():
        pct = filled / total * 100 if total > 0 else 0
        print(f"  {source:15s} {filled:>4} / {total:>4}  ({pct:>5.1f}%)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()