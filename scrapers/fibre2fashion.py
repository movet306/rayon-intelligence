"""
scrapers/fibre2fashion.py
Scrapes article titles, URLs, and full body text from fibre2fashion.com/industry-article/
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

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from _date_utils import parse_published_at, parse_wp_date  # noqa: E402

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
PAGE_DELAY    = 1.5    # seconds between listing page requests
ARTICLE_DELAY = 1.0    # seconds between article detail requests

# Ordered list of CSS selectors tried when extracting the article body.
# First selector that yields > 200 chars wins.
BODY_SELECTORS = [
    "div.artcle-dtl-cnt",          # fibre2fashion primary content div
    "div.artcle-detail-cnt",
    "div[class*='artcle-dtl']",
    "div[class*='article-detail']",
    "div[class*='article-body']",
    "div[class*='article-content']",
    "div[class*='artdetail']",
    "article",
    "main",
]
BODY_MAX_CHARS = 8000   # cap stored body size

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
    url = os.environ.get("RAYON_DATABASE_URL")
    if not url:
        raise RuntimeError("RAYON_DATABASE_URL environment variable is not set")
    return psycopg2.connect(url, connect_timeout=10)


def insert_news_item(
    cur, url: str, title: str, body_raw: str | None,
    published_at: datetime | None = None,
) -> bool:
    """
    Insert one article. Returns True if inserted, False if duplicate.
    Raises on any other error (caller handles).
    """
    cur.execute(
        """
        INSERT INTO news_items (url, source, title, body_raw, language, scraped_at, published_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url_hash) DO NOTHING
        RETURNING id
        """,
        (url, SOURCE, title, body_raw, "en", datetime.now(timezone.utc), published_at),
    )
    return cur.fetchone() is not None   # None → conflict / skipped


def fetch_items_needing_backfill(cur) -> list[dict]:
    """Return id + url for rows where body_raw IS NULL for this source."""
    cur.execute(
        """
        SELECT id, url
        FROM   news_items
        WHERE  body_raw IS NULL
          AND  source = %s
        ORDER  BY scraped_at ASC
        """,
        (SOURCE,),
    )
    return [{"id": str(row[0]), "url": row[1]} for row in cur.fetchall()]


def update_body_raw(cur, item_id: str, body_raw: str):
    cur.execute(
        "UPDATE news_items SET body_raw = %s WHERE id = %s",
        (body_raw, item_id),
    )


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


def fetch_article_body(session: requests.Session, url: str) -> tuple[str | None, datetime | None]:
    """
    Fetch an article detail page and extract the main body text.
    Returns cleaned text (capped at BODY_MAX_CHARS) or None on failure.
    Failures are warnings only — callers insert with body_raw=None.
    """
    try:
        resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("  Body fetch failed for %s: %s", url, e)
        return None, None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Parse published_at BEFORE stripping boilerplate (JSON-LD lives in <script>)
    published_at = parse_published_at(soup, url=url)

    # Strip boilerplate containers before extracting text
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "aside", "form"]):
        tag.decompose()

    for selector in BODY_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator="\n", strip=True)
            # Collapse runs of blank lines
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if len(text) > 200:
                return text[:BODY_MAX_CHARS], published_at

    log.debug("  No body selector matched for %s", url)
    return None, published_at


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
# Backfill loop
# ---------------------------------------------------------------------------

def backfill() -> dict:
    """
    For every news_items row where body_raw IS NULL and source = SOURCE,
    fetch the article detail page and update body_raw.
    Returns {"updated": int, "skipped": int, "failed": int}.
    Skipped = body fetch returned nothing (paywall, 404, no selector match).
    """
    updated = skipped = failed = 0

    try:
        conn = get_connection()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return {"updated": 0, "skipped": 0, "failed": -1, "error": str(e)}

    with conn.cursor() as cur:
        items = fetch_items_needing_backfill(cur)

    log.info("Found %d articles needing body backfill", len(items))

    session = requests.Session()

    for i, item in enumerate(items):
        if i > 0:
            time.sleep(ARTICLE_DELAY)

        log.info("Backfilling (%d/%d): %.70s", i + 1, len(items), item["url"])
        body_raw = fetch_article_body(session, item["url"])

        if body_raw is None:
            skipped += 1
            log.debug("  No body extracted — skipping")
            continue

        log.debug("  Got %d chars", len(body_raw))

        try:
            with conn:
                with conn.cursor() as cur:
                    update_body_raw(cur, item["id"], body_raw)
            updated += 1
        except psycopg2.Error as e:
            failed += 1
            log.warning("  DB error: %s", e)
            record_failure(
                conn,
                url=item["url"],
                error_message=str(e),
                error_detail=repr(e),
                payload={"news_item_id": item["id"], "url": item["url"]},
            )
        except Exception as e:
            failed += 1
            log.warning("  Unexpected error: %s", e)
            record_failure(
                conn,
                url=item["url"],
                error_message=str(e),
                error_detail=repr(e),
                payload={"news_item_id": item["id"], "url": item["url"]},
            )

    conn.close()
    return {"updated": updated, "skipped": skipped, "failed": failed}


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

        for i, article in enumerate(articles):
            # Polite delay between article detail requests (skip before first)
            if i > 0:
                time.sleep(ARTICLE_DELAY)

            log.info("  Fetching body (%d/%d): %.70s", i + 1, len(articles), article["url"])
            body_raw, published_at = fetch_article_body(session, article["url"])
            if body_raw:
                log.debug("    Got %d chars of body text", len(body_raw))
            else:
                log.debug("    No body extracted — will store NULL")

            try:
                with conn:                          # savepoint per article
                    with conn.cursor() as cur:
                        was_inserted = insert_news_item(
                            cur, article["url"], article["title"], body_raw,
                            published_at=published_at,
                        )

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
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Fetch body_raw for existing rows where body_raw IS NULL (ignores --pages)",
    )
    args = parser.parse_args()

    if args.backfill:
        log.info("Starting %s backfill", SOURCE)
        result = backfill()
        print(
            f"\nBackfill summary — updated: {result['updated']}  "
            f"skipped: {result['skipped']}  "
            f"failed: {result['failed']}"
        )
    else:
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
