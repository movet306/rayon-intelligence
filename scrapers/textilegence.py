"""
scrapers/textilegence.py
Scrapes English-language articles from textilegence.com and inserts them
into the news_items table.

textilegence.com runs on WordPress with the REST API enabled. Rather than
scraping HTML listing pages (which always return the same 56 cached articles
regardless of page number), this scraper uses the WP REST API:

  GET /wp-json/wp/v2/posts?lang=en&per_page=PER_PAGE&page=N

Pagination headers  X-WP-Total / X-WP-TotalPages  are used to detect
the last page. As of writing, the English edition has ~2400 articles
across ~799 API pages.

Body text is extracted from the content.rendered HTML field (the same
full-article body shown on the detail page) — no detail-page fetches
required. The --backfill mode back-fills body_raw for rows with NULL
bodies by calling the article URL directly.

Usage:
    python scrapers/textilegence.py              # last 1 API page (3 articles)
    python scrapers/textilegence.py --pages 5    # 5 API pages × 3 = up to 15 articles
    python scrapers/textilegence.py --pages 50   # larger initial ingest
    python scrapers/textilegence.py --backfill
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
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SOURCE   = "textilegence"
PIPELINE = "textilegence_scraper"
BASE_URL = "https://www.textilegence.com"
API_URL  = f"{BASE_URL}/wp-json/wp/v2/posts"

PER_PAGE      = 20       # posts per API request (max 100, keep moderate)
REQUEST_DELAY = 1.5      # seconds between API page requests
REQUEST_TIMEOUT = 20
BODY_MAX_CHARS  = 8000

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# CSS selectors used in --backfill mode to extract body from detail pages
BODY_SELECTORS = [
    ".td-post-content",
    ".entry-content",
    "div[class*='post-content']",
    "div[class*='entry-content']",
    "article",
]

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


def insert_news_item(
    cur, url: str, title: str, body_raw: str | None,
    published_at: datetime | None = None,
) -> bool:
    """Insert one article. Returns True if inserted, False if duplicate."""
    cur.execute(
        """
        INSERT INTO news_items (url, source, title, body_raw, language, scraped_at, published_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url_hash) DO NOTHING
        RETURNING id
        """,
        (url, SOURCE, title, body_raw, "en", datetime.now(timezone.utc), published_at),
    )
    return cur.fetchone() is not None


def fetch_items_needing_backfill(cur) -> list[dict]:
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


def record_failure(conn, url: str | None, error_message: str,
                   error_detail: str, payload: dict):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO failed_jobs
                    (pipeline, job_type, url, error_message, error_detail, payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    PIPELINE, "scrape", url,
                    error_message[:500], error_detail[:2000],
                    json.dumps(payload),
                ),
            )
        conn.commit()
    except Exception as e:
        log.warning("Could not write to failed_jobs: %s", e)


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

def html_to_text(html: str) -> str:
    """Strip HTML tags from a WP content.rendered block → plain text."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "figure", "aside"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:BODY_MAX_CHARS]


def clean_title(html_title: str) -> str:
    """Decode HTML entities in WP title.rendered."""
    return BeautifulSoup(html_title, "html.parser").get_text(strip=True)


# ---------------------------------------------------------------------------
# API fetching
# ---------------------------------------------------------------------------

def fetch_api_page(session: requests.Session,
                   page: int) -> tuple[list[dict], int] | None:
    """
    Fetch one page of posts from the WP REST API.
    Returns (posts_list, total_pages) or None on error.
    """
    params = {
        "lang":     "en",
        "per_page": PER_PAGE,
        "page":     page,
        "status":   "publish",
        "_fields":  "id,link,date,title,content,excerpt",
    }
    try:
        resp = session.get(
            API_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 400:
            # WP returns 400 when page > total_pages
            return [], 0
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("API request failed (page %d): %s", page, e)
        return None

    try:
        posts = resp.json()
    except ValueError as e:
        log.warning("JSON parse error (page %d): %s", page, e)
        return None

    # WP REST API sometimes returns an error object instead of a list
    # (e.g. {"code":"rest_forbidden","message":"..."}) — treat as empty page
    if not isinstance(posts, list):
        log.warning("Unexpected API response type (page %d): %s — body: %.200s",
                    page, type(posts).__name__, str(posts))
        return [], 0

    total_pages = int(resp.headers.get("X-WP-TotalPages", 0))
    return posts, total_pages


def extract_article(post: dict) -> dict | None:
    """
    Convert a WP REST API post object into {url, title, body_raw}.
    Returns None if the post is missing essential fields.
    """
    if not isinstance(post, dict):
        log.warning("Skipping non-dict post item: %r", post)
        return None

    url = post.get("link", "").strip()
    if not url:
        return None
    # Only keep English articles (URL contains /en/)
    if "/en/" not in url:
        return None

    raw_title = post.get("title", {}).get("rendered", "").strip()
    if not raw_title:
        return None
    title = clean_title(raw_title)

    content_html = post.get("content", {}).get("rendered", "")
    body_raw = html_to_text(content_html) if content_html else None

    return {
        "url": url,
        "title": title,
        "body_raw": body_raw,
        "published_at": parse_wp_date(post.get("date")),
    }


# ---------------------------------------------------------------------------
# Backfill (fetch body from detail page for NULL rows)
# ---------------------------------------------------------------------------

def fetch_body_from_page(session: requests.Session, url: str) -> str | None:
    """Fetch article body from the HTML detail page (used in --backfill)."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("  Body fetch failed for %s: %s", url, e)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "aside"]):
        tag.decompose()

    for selector in BODY_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if len(text) > 200:
                return text[:BODY_MAX_CHARS]

    return None


def backfill() -> dict:
    """Back-fill body_raw for rows where it is NULL."""
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
            time.sleep(REQUEST_DELAY)

        log.info("Backfilling (%d/%d): %.70s", i + 1, len(items), item["url"])
        body_raw = fetch_body_from_page(session, item["url"])

        if body_raw is None:
            skipped += 1
            continue

        try:
            with conn:
                with conn.cursor() as cur:
                    update_body_raw(cur, item["id"], body_raw)
            updated += 1
        except Exception as e:
            failed += 1
            log.warning("  DB error: %s", e)
            record_failure(
                conn, url=item["url"],
                error_message=str(e), error_detail=repr(e),
                payload={"news_item_id": item["id"], "url": item["url"]},
            )

    conn.close()
    return {"updated": updated, "skipped": skipped, "failed": failed}


# ---------------------------------------------------------------------------
# Main scrape loop
# ---------------------------------------------------------------------------

def scrape(pages: int = 1) -> dict:
    """
    Fetch `pages` API pages (newest-first) and insert into news_items.
    Stops early if the API signals no more content (400 response or 0 posts).
    Returns {"inserted": int, "skipped": int, "failed": int}.
    """
    inserted = skipped = failed = 0

    try:
        conn = get_connection()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return {"inserted": 0, "skipped": 0, "failed": -1, "error": str(e)}

    session = requests.Session()

    for page_num in range(1, pages + 1):
        if page_num > 1:
            time.sleep(REQUEST_DELAY)

        log.info("Fetching API page %d/%d ...", page_num, pages)
        result = fetch_api_page(session, page_num)

        if result is None:
            failed += 1
            record_failure(
                conn, url=None,
                error_message="API request failed",
                error_detail=f"page={page_num}",
                payload={"page": page_num},
            )
            continue

        posts, total_pages = result

        if not posts:
            log.info("  No posts returned — stopping early (past last page)")
            break

        log.info("  %d posts  (total API pages: %s)", len(posts), total_pages or "?")

        for post in posts:
            article = extract_article(post)
            if not article:
                continue

            try:
                with conn:
                    with conn.cursor() as cur:
                        was_inserted = insert_news_item(
                            cur, article["url"], article["title"], article["body_raw"],
                            published_at=article.get("published_at"),
                        )
                if was_inserted:
                    inserted += 1
                    log.debug("  INSERTED  %s", article["url"])
                else:
                    skipped += 1
                    log.debug("  SKIPPED   %s (duplicate)", article["url"])

            except psycopg2.Error as e:
                failed += 1
                log.warning("  DB error for %s: %s", article["url"], e)
                record_failure(
                    conn, url=article["url"],
                    error_message=str(e), error_detail=repr(e),
                    payload={"url": article["url"], "title": article.get("title", "")},
                )
            except Exception as e:
                failed += 1
                log.warning("  Unexpected error for %s: %s", article["url"], e)
                record_failure(
                    conn, url=article["url"],
                    error_message=str(e), error_detail=repr(e),
                    payload={"url": article["url"]},
                )

    conn.close()
    return {"inserted": inserted, "skipped": skipped, "failed": failed}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape textilegence.com English articles via WordPress REST API"
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        metavar="N",
        help=(
            f"Number of API pages to fetch (each page = {PER_PAGE} articles). "
            "Default: 1.  The English edition has ~799 pages total."
        ),
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Fetch body_raw for existing rows where body_raw IS NULL",
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
        if args.pages < 1:
            parser.error("--pages must be >= 1")
        log.info("Starting %s scraper (pages=%d, per_page=%d)", SOURCE, args.pages, PER_PAGE)
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
