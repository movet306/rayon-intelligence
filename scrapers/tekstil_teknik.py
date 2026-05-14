"""
scrapers/tekstil_teknik.py
Scrapes article titles, URLs, and full body text from tekstilteknik.com.tr and
inserts them into the news_items table.

The site runs on JegTheme (WordPress). Listing pages follow the pattern:
  Page 1: /haberler/
  Page 2: /haberler/page/2/
  Page N: /haberler/page/N/

Usage:
    python scrapers/tekstil_teknik.py
    python scrapers/tekstil_teknik.py --pages 3
    python scrapers/tekstil_teknik.py --backfill
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
SOURCE   = "tekstil_teknik"
PIPELINE = "tekstil_teknik_scraper"
BASE_URL = "https://www.tekstilteknik.com.tr"

# Homepage serves as the article listing. Pagination: /page/N/ for N >= 2.
def listing_url(page: int) -> str:
    if page == 1:
        return f"{BASE_URL}/"
    return f"{BASE_URL}/page/{page}/"

# Article detail URLs look like: https://www.tekstilteknik.com.tr/<slug>/
# They are at the root level — exclude known non-article paths.
_EXCLUDED_PATHS = re.compile(
    r"^/(kategori|category|tag|etiket|author|yazar|page|wp-|feed|e-dergi|en|home|#)",
    re.IGNORECASE,
)
ARTICLE_URL_RE = re.compile(
    r"^https://(?:www\.)?tekstilteknik\.com\.tr/[a-z0-9][^/]+/$",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}
REQUEST_TIMEOUT = 20
PAGE_DELAY    = 1.5   # seconds between listing-page requests
ARTICLE_DELAY = 1.5   # seconds between article detail requests

# Ordered list of CSS selectors tried when extracting the article body.
# First selector that yields > 200 chars wins.
BODY_SELECTORS = [
    ".content-inner",
    ".entry-content.no-share",
    ".entry-content",
    "div[class*='entry-content']",
    "div[class*='content-inner']",
    ".jeg_content",
    "article",
    "main",
]
BODY_MAX_CHARS = 8000

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
    """Insert one article. Returns True if inserted, False if duplicate."""
    cur.execute(
        """
        INSERT INTO news_items (url, source, title, body_raw, language, scraped_at, published_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url_hash) DO NOTHING
        RETURNING id
        """,
        (url, SOURCE, title, body_raw, "tr", datetime.now(timezone.utc), published_at),
    )
    return cur.fetchone() is not None


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
    """Write one row to failed_jobs. Never rolls back the caller."""
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

def fetch_page(session: requests.Session, url: str,
               allow_homepage_redirect: bool = False) -> BeautifulSoup | None:
    """Fetch any page, return BeautifulSoup or None on error."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # Detect unexpected redirects back to homepage (e.g. article behind paywall)
        final = resp.url.rstrip("/")
        if not allow_homepage_redirect and final == BASE_URL.rstrip("/"):
            log.warning("Redirected to homepage for %s — skipping", url)
            return None
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        log.warning("Failed to fetch %s: %s", url, e)
        return None


def fetch_article_body(session: requests.Session, url: str) -> tuple[str | None, datetime | None]:
    """
    Fetch an article detail page and extract the main body text.
    Returns cleaned text (capped at BODY_MAX_CHARS) or None on failure.
    """
    soup = fetch_page(session, url, allow_homepage_redirect=False)
    if soup is None:
        return None, None

    # Parse published_at BEFORE stripping boilerplate (JSON-LD lives in <script>)
    published_at = parse_published_at(soup, url=url)

    # Strip boilerplate containers
    for tag in soup.find_all(["nav", "header", "footer", "script", "style", "aside", "form"]):
        tag.decompose()

    for selector in BODY_SELECTORS:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if len(text) > 200:
                return text[:BODY_MAX_CHARS], published_at

    log.debug("  No body selector matched for %s", url)
    return None, published_at


def extract_articles(soup: BeautifulSoup) -> list[dict]:
    """
    Extract {url, title} pairs from a JegTheme listing page.
    Targets article.jeg_post elements; falls back to any h3 with a matching link.
    """
    articles = []
    seen_urls: set[str] = set()

    # Primary: JegTheme article cards
    for card in soup.select("article.jeg_post"):
        a = card.select_one("h3.jeg_post_title a, h2.jeg_post_title a")
        if not a:
            # Fallback: any <a> inside a heading within the card
            for heading in card.find_all(["h2", "h3", "h4"]):
                a = heading.find("a", href=True)
                if a:
                    break
        if not a:
            continue

        href = a.get("href", "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = BASE_URL + href

        if not ARTICLE_URL_RE.match(href):
            continue
        # Exclude non-article paths
        path = href.replace(BASE_URL, "")
        if _EXCLUDED_PATHS.search(path):
            continue

        if href in seen_urls:
            continue
        seen_urls.add(href)

        title = a.get_text(separator=" ", strip=True)
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            continue

        articles.append({"url": href, "title": title})

    # Secondary fallback: scan all headings if primary yielded nothing
    if not articles:
        for heading in soup.find_all(["h2", "h3"]):
            a = heading.find("a", href=True)
            if not a:
                continue
            href = a["href"].strip()
            if href.startswith("/"):
                href = BASE_URL + href
            if not ARTICLE_URL_RE.match(href):
                continue
            path = href.replace(BASE_URL, "")
            if _EXCLUDED_PATHS.search(path):
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)
            title = heading.get_text(separator=" ", strip=True)
            title = re.sub(r"\s+", " ", title).strip()
            if title:
                articles.append({"url": href, "title": title})

    return articles


def is_empty_page(soup: BeautifulSoup) -> bool:
    """Return True if the listing page has no article cards (past last page)."""
    return len(soup.select("article.jeg_post")) == 0


# ---------------------------------------------------------------------------
# Backfill loop
# ---------------------------------------------------------------------------

def backfill() -> dict:
    """
    For every news_items row where body_raw IS NULL and source = SOURCE,
    fetch the article detail page and update body_raw.
    Returns {"updated": int, "skipped": int, "failed": int}.
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
        except Exception as e:
            failed += 1
            log.warning("  DB error: %s", e)
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
    Scrape up to `pages` listing pages and insert results.
    Stops early if a listing page returns no article cards.
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
        url = listing_url(page_num)
        log.info("Fetching listing page %d/%d: %s", page_num, pages, url)

        if page_num > 1:
            time.sleep(PAGE_DELAY)

        soup = fetch_page(session, url, allow_homepage_redirect=True)
        if soup is None:
            failed += 1
            record_failure(
                conn,
                url=url,
                error_message="Failed to fetch listing page",
                error_detail=f"page={page_num}",
                payload={"page": page_num, "url": url},
            )
            continue

        if is_empty_page(soup):
            log.info("  Page %d has no article cards — stopping early", page_num)
            break

        articles = extract_articles(soup)
        log.info("  Found %d articles on page %d", len(articles), page_num)

        for i, article in enumerate(articles):
            if i > 0:
                time.sleep(ARTICLE_DELAY)

            log.info("  Fetching body (%d/%d): %.70s", i + 1, len(articles), article["url"])
            body_raw, published_at = fetch_article_body(session, article["url"])
            if body_raw:
                log.debug("    Got %d chars of body text", len(body_raw))
            else:
                log.debug("    No body extracted — will store NULL")

            try:
                with conn:
                    with conn.cursor() as cur:
                        was_inserted = insert_news_item(
                            cur, article["url"], article["title"], body_raw,
                            published_at=published_at,
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

    conn.close()
    return {"inserted": inserted, "skipped": skipped, "failed": failed}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape tekstilteknik.com.tr articles"
    )
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
        if args.pages < 1:
            parser.error("--pages must be >= 1")
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
