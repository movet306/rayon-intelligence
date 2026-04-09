"""
scrapers/just_style.py
Scrapes article titles and URLs from just-style.com and inserts them
into the news_items table.

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
SECTION_DELAY = 1.5   # seconds between section requests

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
    """Insert one article. Returns True if inserted, False if duplicate."""
    cur.execute(
        """
        INSERT INTO news_items (url, source, title, language, scraped_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (url_hash) DO NOTHING
        RETURNING id
        """,
        (url, SOURCE, title, "en", datetime.now(timezone.utc)),
    )
    return cur.fetchone() is not None


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

        for article in articles:
            try:
                with conn:
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
    args = parser.parse_args()

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
