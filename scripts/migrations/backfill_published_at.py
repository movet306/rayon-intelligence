"""P0-A backfill v2: re-fetch HTML for NULL published_at articles.

URL-only backfill (v1) yielded 0% because news sites use slug-based URLs.
This v2 fetches each article's HTML and extracts published_at from
meta tags / JSON-LD / <time> elements.

Sleeps 0.5s between requests to be polite to source servers.
Total runtime: ~336 articles * 1.5s = ~8 minutes.
"""
import os
import sys
import time
from pathlib import Path
import psycopg2
import requests

SCRAPERS_DIR = Path(__file__).resolve().parent.parent.parent / "scrapers"
sys.path.insert(0, str(SCRAPERS_DIR))
from _date_utils import parse_published_at  # noqa: E402


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
}
REQUEST_TIMEOUT = 15
SLEEP_BETWEEN = 0.5


def main():
    db_url = os.environ.get("RAYON_DATABASE_URL") or os.environ["DATABASE_URL"]
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM news_items WHERE published_at IS NULL")
    null_before = cur.fetchone()[0]
    print(f"Articles to backfill: {null_before}")
    if null_before == 0:
        print("Nothing to do.")
        return

    cur.execute("""
        SELECT id, url, source FROM news_items
        WHERE published_at IS NULL
        ORDER BY source, scraped_at DESC
    """)
    rows = cur.fetchall()

    session = requests.Session()
    updated = 0
    failed = 0
    no_date = 0
    by_source_ok = {}
    by_source_fail = {}

    print(f"\nProcessing (sleep {SLEEP_BETWEEN}s between)...")
    for i, (row_id, item_url, source) in enumerate(rows, 1):
        if i == 1 or i % 25 == 0 or i == len(rows):
            print(f"  [{i:>4}/{len(rows)}]  updated={updated}  no_date={no_date}  failed={failed}")
        try:
            resp = session.get(item_url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()
            dt = parse_published_at(resp.text, url=item_url)
            if dt:
                cur.execute(
                    "UPDATE news_items SET published_at = %s WHERE id = %s",
                    (dt, row_id),
                )
                conn.commit()
                updated += 1
                by_source_ok[source] = by_source_ok.get(source, 0) + 1
            else:
                no_date += 1
        except Exception:
            failed += 1
            by_source_fail[source] = by_source_fail.get(source, 0) + 1
        time.sleep(SLEEP_BETWEEN)

    cur.execute("SELECT COUNT(*) FROM news_items WHERE published_at IS NULL")
    null_after = cur.fetchone()[0]
    fill_rate = (null_before - null_after) / null_before * 100 if null_before > 0 else 0

    print()
    print("=== Result ===")
    print(f"  Updated:  {updated}")
    print(f"  No date:  {no_date}  (HTML fetched but no parseable date)")
    print(f"  Failed:   {failed}  (network/HTTP error)")
    print(f"  NULL after: {null_after}")
    print(f"  Fill rate: {fill_rate:.1f}%")

    print()
    print("=== Backfilled per source ===")
    for source in sorted(set(list(by_source_ok.keys()) + list(by_source_fail.keys()))):
        ok_n = by_source_ok.get(source, 0)
        fail_n = by_source_fail.get(source, 0)
        print(f"  {source:15s} backfilled={ok_n:>4}  fetch_errors={fail_n}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()