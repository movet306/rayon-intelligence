"""
scrapers/fibre2fashion.py
Scrapes article titles and URLs from fibre2fashion.com/industry-article/
and inserts them into the news_items table.

Usage:
    python scrapers/fibre2fashion.py
    python scrapers/fibre2fashion.py --pages 3

Returns exit code 0 always; summary is printed to stdout.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SOURCE = "fibre2fashion"
PIPELINE = "fibre2fashion_scraper"
BASE_URL = "https://www.fibre2fashion.com/industry-article/"
# Article detail URLs: /industry-article/{numeric-id}/{slug}
ARTICLE_URL_RE = re.compile(r"fibre2fashion\.com/industry-article/(\d+)/[^/\"'\s]+")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_TIMEOUT = 15   # seconds
PAGE_DELAY = 1.5       # seconds between page requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(url, connect_timeout=10)


def insert_news_item(cur, url: str, title: str) -> bool:
    """
    Insert one article. Returns True if inserted, False if duplicate.
    Raises on any other error (caller handles).
    """
    cur.execute(
        """
        INSERT INTO news_items (url, source, title, language, scraped_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (url_hash) DO NOTHING
        RETURNING id
        """,
        (url, SOURCE, title, "en", datetime.now(timezone.utc)),
    )
    return cur.fetchone() is not None   # None → conflict / skipped


def record_failure(conn, url: str | None, error_message: str, error_detail: str, payload: dict):
    """Write one row to failed_jobs. Uses its own savepoint so it never rolls back the caller."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO failed_jobs
                    (pipeline, job_type, url, error_message, error_detail, payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    PIPELINE,
                    "scrape",
                    url,
                    error_message[:500],
                    error_detail[:2000],
                    json.dumps(payload),
                ),
            )
        conn.commit()
    except Exception as e:
        log.warning("Could not write to failed_jobs: %s", e)


# ---------------------------------------------------------------------------
# Scraping helpers
# ---------------------------------------------------------------------------

def fetch_listing_page(session: requests.Session, url: str) -> BeautifulSoup | None:
    """Fetch a listing page, return BeautifulSoup or None on error."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        log.warning("Failed to fetch %s: %s", url, e)
        return None


def extract_articles(soup: BeautifulSoup) -> list[dict]:
    """
    Extract article {url, title} pairs from a listing page.
    Matches hrefs like /industry-article/{numeric-id}/{slug}.
    """
    articles = []
    seen_ids = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Normalise protocol-relative URLs
        if href.startswith("//"):
            href = "https:" + href

        m = ARTICLE_URL_RE.search(href)
        if not m:
            continue

        article_id = m.group(1)
        if article_id in seen_ids:
            continue
        seen_ids.add(article_id)

        title = a.get_text(strip=True)
        # Skip nav links that reuse article-style URLs (very short or empty text)
        if len(title) < 10:
            continue

        # Ensure absolute URL
        if not href.startswith("http"):
            href = "https://www.fibre2fashion.com" + href

        articles.append({"url": href, "title": title})

    return articles


# ---------------------------------------------------------------------------
# Main scrape loop
# ---------------------------------------------------------------------------

def scrape(pages: int = 1) -> dict:
    """
    Scrape `pages` listing pages and insert results.
    Returns {"inserted": int, "skipped": int, "failed": int}.
    """
    inserted = skipped = failed = 0

    try:
        conn = get_connection()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return {"inserted": 0, "skipped": 0, "failed": -1, "error": str(e)}

    session = requests.Session()

    # Build list of listing pages to scrape.
    # Page 1 = /industry-article/  ; page N = /industry-article/?page=N
    listing_urls = [BASE_URL] + [f"{BASE_URL}?page={p}" for p in range(2, pages + 1)]

    for page_num, listing_url in enumerate(listing_urls, start=1):
        log.info("Fetching listing page %d/%d: %s", page_num, pages, listing_url)
        soup = fetch_listing_page(session, listing_url)

        if soup is None:
            failed += 1
            record_failure(
                conn,
                url=listing_url,
                error_message="Failed to fetch listing page",
                error_detail=f"page={page_num}",
                payload={"listing_url": listing_url, "page": page_num},
            )
            continue

        articles = extract_articles(soup)
        log.info("  Found %d articles on page %d", len(articles), page_num)

        for article in articles:
            try:
                with conn:                          # savepoint per article
                    with conn.cursor() as cur:
                        was_inserted = insert_news_item(cur, article["url"], article["title"])

                if was_inserted:
                    inserted += 1
                    log.debug("  INSERTED %s", article["url"])
                else:
                    skipped += 1
                    log.debug("  SKIPPED  %s (duplicate)", article["url"])

            except psycopg2.Error as e:
                failed += 1
                log.warning("  DB error for %s: %s", article["url"], e)
                record_failure(
                    conn,
                    url=article["url"],
                    error_message=str(e),
                    error_detail=repr(e),
                    payload={"url": article["url"], "title": article["title"]},
                )
            except Exception as e:
                failed += 1
                log.warning("  Unexpected error for %s: %s", article["url"], e)
                record_failure(
                    conn,
                    url=article["url"],
                    error_message=str(e),
                    error_detail=repr(e),
                    payload={"url": article["url"], "title": article["title"]},
                )

        if page_num < pages:
            time.sleep(PAGE_DELAY)

    conn.close()
    return {"inserted": inserted, "skipped": skipped, "failed": failed}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape fibre2fashion.com articles")
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        metavar="N",
        help="Number of listing pages to scrape (default: 1)",
    )
    args = parser.parse_args()

    log.info("Starting %s scraper (pages=%d)", SOURCE, args.pages)
    result = scrape(pages=args.pages)

    print(
        f"\nSummary — inserted: {result['inserted']}  "
        f"skipped: {result['skipped']}  "
        f"failed: {result['failed']}"
    )

    if result.get("error"):
        print(f"Fatal error: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
