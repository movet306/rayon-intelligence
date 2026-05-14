"""
scrapers/just_style.py
Scrapes article titles, URLs, and full body text from just-style.com and inserts
them into the news_items table.

just-style.com content is organised into sections rather than numbered
pages, so --pages maps to sections in priority order:
  1 → /news/
  2 → /news/ + /analysis/
  3 → /news/ + /analysis/ + /features/
  4 → /news/ + /analysis/ + /features/ + /comment/

Usage:
    python scrapers/just_style.py
    python scrapers/just_style.py --pages 2
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
SOURCE = "just_style"
PIPELINE = "just_style_scraper"
BASE_DOMAIN = "https://www.just-style.com"

# Sections in priority order — each counts as one "page"
SECTIONS = [
    f"{BASE_DOMAIN}/news/",
    f"{BASE_DOMAIN}/analysis/",
    f"{BASE_DOMAIN}/features/",
    f"{BASE_DOMAIN}/comment/",
]

# Article detail URLs: /(news|analysis|features|comment)/<slug>/
ARTICLE_URL_RE = re.compile(
    r"^https://www\.just-style\.com/(news|analysis|features|comment)/[^/]+/$"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_TIMEOUT = 15
SECTION_DELAY = 1.5   # seconds between section listing requests
ARTICLE_DELAY = 1.0   # seconds between article detail requests

# Ordered list of CSS selectors tried when extracting the article body.
# First selector that yields > 200 chars wins.
BODY_SELECTORS = [
    "div.article__body",
    "div.article-body",
    "div[class*='article__body']",
    "div[class*='article-body']",
    "div[class*='article-content']",
    "div[class*='body-content']",
    "div[class*='content-body']",
    "div[class*='post-content']",
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

def fetch_section(session: requests.Session, url: str) -> BeautifulSoup | None:
    """Fetch a section listing page, return BeautifulSoup or None on error."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # Detect silent redirects back to homepage
        if resp.url.rstrip("/") == BASE_DOMAIN:
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
    Failures are warnings only — callers insert with body_raw=None.
    """
    try:
        resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # just-style.com may redirect paywalled articles — detect it
        if resp.url.rstrip("/") == BASE_DOMAIN:
            log.debug("  Paywalled/redirected: %s", url)
            return None
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
    Extract {url, title} pairs from a section listing page.
    Titles are read from heading tags (h2/h3/h4) to avoid the empty-text
    issue that affects plain <a> link scraping on this site.
    """
    articles = []
    seen_urls = set()

    for heading in soup.find_all(["h2", "h3", "h4"]):
        a = heading.find("a", href=True)
        if not a:
            continue

        href = a["href"]
        # Normalise relative and protocol-relative URLs
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = BASE_DOMAIN + href

        if not ARTICLE_URL_RE.match(href):
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)

        title = heading.get_text(separator=" ", strip=True)
        # Clean up non-breaking spaces and stray unicode
        title = re.sub(r"\s+", " ", title).strip()
        if not title:
            continue

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
    Scrape up to `pages` sections and insert results.
    Returns {"inserted": int, "skipped": int, "failed": int}.
    """
    inserted = skipped = failed = 0

    try:
        conn = get_connection()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return {"inserted": 0, "skipped": 0, "failed": -1, "error": str(e)}

    session = requests.Session()
    sections_to_scrape = SECTIONS[:pages]

    for idx, section_url in enumerate(sections_to_scrape, start=1):
        log.info(
            "Fetching section %d/%d: %s", idx, len(sections_to_scrape), section_url
        )
        soup = fetch_section(session, section_url)

        if soup is None:
            failed += 1
            record_failure(
                conn,
                url=section_url,
                error_message="Failed to fetch section page",
                error_detail=f"section={section_url}",
                payload={"section_url": section_url},
            )
            continue

        articles = extract_articles(soup)
        log.info("  Found %d articles in section %d", len(articles), idx)

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
                with conn:
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

        if idx < len(sections_to_scrape):
            time.sleep(SECTION_DELAY)

    conn.close()
    return {"inserted": inserted, "skipped": skipped, "failed": failed}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape just-style.com articles")
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Number of sections to scrape, 1–4 "
            "(1=news, 2=+analysis, 3=+features, 4=+comment). Default: 1"
        ),
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
        if not 1 <= args.pages <= len(SECTIONS):
            parser.error(f"--pages must be between 1 and {len(SECTIONS)}")
        log.info("Starting %s scraper (sections=%d)", SOURCE, args.pages)
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
