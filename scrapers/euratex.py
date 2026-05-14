"""
EURATEX news scraper.
Source: https://euratex.eu/news/
Pagination: /news/page/N/ (up to ~21 pages, ~210 article history)
Platform: WordPress 6.9.4
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

SOURCE = "euratex"
BASE_URL = "https://euratex.eu"
LISTING_URL = f"{BASE_URL}/news/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 0.5

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger(SOURCE)


def get_conn():
    url = os.environ.get("RAYON_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Neither RAYON_DATABASE_URL nor DATABASE_URL is set")
    return psycopg2.connect(url)


def fetch(url: str) -> Optional[BeautifulSoup]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        r.encoding = "utf-8"
        return BeautifulSoup(r.text, "html.parser")
    except requests.RequestException as e:
        log.error("fetch failed: %s -> %s", url, e)
        return None


def parse_date(text: str) -> Optional[datetime]:
    """Parse date from EURATEX article opening, e.g.:
    'Brussels, 11 March 2026 -' or 'Brussels 17/01/2026 -' or 'Paris, 5 February 2026 -'
    """
    if not text:
        return None
    sample = text[:500].lower()
    # DD/MM/YYYY format
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', sample)
    if m:
        try:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= d <= 31 and 1 <= mo <= 12:
                return datetime(y, mo, d, tzinfo=timezone.utc)
        except ValueError:
            pass
    months = '|'.join(MONTH_MAP.keys())
    m = re.search(rf'(\d{{1,2}})\s+({months})\s+(\d{{4}})', sample)
    if m:
        try:
            return datetime(int(m.group(3)), MONTH_MAP[m.group(2)], int(m.group(1)), tzinfo=timezone.utc)
        except (ValueError, KeyError):
            pass
    return None


def parse_listing(soup: BeautifulSoup) -> list[dict]:
    """Extract article URLs from WordPress listing.
    H3 tags with anchors to /news/ or /position-paper/ articles.
    """
    items = []
    seen = set()
    for h3 in soup.find_all("h3"):
        link = h3.find("a", href=True)
        if not link:
            continue
        href = link["href"]
        if not ("/news/" in href or "/position-paper/" in href):
            continue
        if href.rstrip("/") in (LISTING_URL.rstrip("/"), f"{BASE_URL}/position-paper"):
            continue
        if href in seen:
            continue
        seen.add(href)
        title = link.get_text(strip=True)
        items.append({"url": href, "title": title})
    return items


def parse_article(soup: BeautifulSoup) -> dict:
    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else None
    body_parts = []
    container = soup.find("article") or soup.find("main") or soup
    for p in container.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if len(txt) > 50:
            body_parts.append(txt)
    body_raw = "\n\n".join(body_parts) if body_parts else None
    date = parse_date(body_raw) if body_raw else None
    return {"title": title, "body_raw": body_raw, "published_at": date}


def insert_news_item(cur, url, title, body_raw, published_at):
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


def scrape(pages: int = 1) -> dict:
    inserted = skipped = failed = 0
    conn = get_conn()
    cur = conn.cursor()
    try:
        for page in range(1, pages + 1):
            page_url = LISTING_URL if page == 1 else f"{BASE_URL}/news/page/{page}/"
            log.info("Listing page %d: %s", page, page_url)
            soup = fetch(page_url)
            if soup is None:
                failed += 1
                continue
            items = parse_listing(soup)
            log.info("  Found %d articles", len(items))
            for item in items:
                article_url = item["url"]
                cur.execute("SELECT 1 FROM news_items WHERE url = %s LIMIT 1", (article_url,))
                if cur.fetchone():
                    skipped += 1
                    continue
                time.sleep(SLEEP_BETWEEN_REQUESTS)
                article_soup = fetch(article_url)
                if article_soup is None:
                    failed += 1
                    continue
                parsed = parse_article(article_soup)
                title = parsed.get("title") or item.get("title")
                body_raw = parsed.get("body_raw")
                published_at = parsed.get("published_at")
                if not title or not body_raw or len(body_raw) < 100:
                    log.warning("  SKIP missing/short: %s", article_url)
                    failed += 1
                    continue
                if insert_news_item(cur, article_url, title, body_raw, published_at):
                    inserted += 1
                    date_disp = published_at.strftime("%Y-%m-%d") if published_at else "no-date"
                    log.info("  + [%s] %s", date_disp, title[:70])
                else:
                    skipped += 1
            conn.commit()
            time.sleep(SLEEP_BETWEEN_REQUESTS)
    except Exception as e:
        conn.rollback()
        log.error("Fatal: %s", e)
        raise
    finally:
        cur.close()
        conn.close()
    return {"inserted": inserted, "skipped": skipped, "failed": failed}


def main():
    parser = argparse.ArgumentParser(description=f"{SOURCE} scraper - EURATEX news")
    parser.add_argument("--pages", type=int, default=1, help="Listing pages (default: 1, max ~21)")
    args = parser.parse_args()
    log.info("Starting %s scraper (pages=%d)", SOURCE, args.pages)
    result = scrape(pages=args.pages)
    print(f"\nSummary -> inserted: {result['inserted']}  skipped: {result['skipped']}  failed: {result['failed']}")


if __name__ == "__main__":
    main()