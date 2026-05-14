"""
İHKİB Dünyadan Haberler scraper.
Source: https://www.ihkib.org.tr/bilgi-bankasi/dunyadan-haberler
Pagination: ?p=N (up to ~23 pages, ~50 articles/page)
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

SOURCE = "ihkib"
BASE_URL = "https://www.ihkib.org.tr"
LISTING_PATH = "/bilgi-bankasi/dunyadan-haberler"
LISTING_URL = f"{BASE_URL}{LISTING_PATH}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 0.5

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


def parse_listing(soup: BeautifulSoup) -> list[dict]:
    items = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.startswith("/bilgi-bankasi/dunyadan-haberler/"):
            continue
        if href.rstrip("/").endswith("dunyadan-haberler"):
            continue
        text = link.get_text(" ", strip=True)
        m = re.search(r"HABER\s+(\d{2}\.\d{2}\.\d{4})\s+(.+)", text)
        if not m:
            continue
        date_str, title = m.group(1), m.group(2).strip()
        full_url = BASE_URL + href if href.startswith("/") else href
        items.append({"url": full_url, "title": title, "date_str": date_str})
    seen = set()
    unique = []
    for item in items:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        unique.append(item)
    return unique


def parse_article(soup: BeautifulSoup) -> dict:
    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else None
    full_text = soup.get_text(" ", strip=True)
    date_match = re.search(r"EKLENME TAR.{1,3}H.{0,2}\s+(\d{2}\.\d{2}\.\d{4})", full_text)
    date_str = date_match.group(1) if date_match else None
    paragraphs = []
    for p in soup.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if len(txt) > 50:
            paragraphs.append(txt)
    body_raw = "\n\n".join(paragraphs) if paragraphs else None
    return {"title": title, "body_raw": body_raw, "date_str": date_str}


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def insert_news_item(cur, url: str, title: str, body_raw: str, published_at: Optional[datetime]) -> bool:
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


def scrape(pages: int = 1) -> dict:
    inserted = skipped = failed = 0
    conn = get_conn()
    cur = conn.cursor()
    try:
        for page in range(1, pages + 1):
            page_url = LISTING_URL if page == 1 else f"{LISTING_URL}?p={page}"
            log.info("Listing page %d: %s", page, page_url)
            soup = fetch(page_url)
            if soup is None:
                failed += 1
                continue
            items = parse_listing(soup)
            log.info("  Found %d articles on page", len(items))
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
                date_str = parsed.get("date_str") or item.get("date_str")
                published_at = parse_date(date_str)
                if not title or not body_raw or len(body_raw) < 100:
                    log.warning("  SKIP missing/short data: %s", article_url)
                    failed += 1
                    continue
                if insert_news_item(cur, article_url, title, body_raw, published_at):
                    inserted += 1
                    log.info("  + [%s] %s", date_str, title[:70])
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
    parser = argparse.ArgumentParser(description=f"{SOURCE} scraper")
    parser.add_argument("--pages", type=int, default=1, help="Listing pages (default: 1, max ~23)")
    args = parser.parse_args()
    log.info("Starting %s scraper (pages=%d)", SOURCE, args.pages)
    result = scrape(pages=args.pages)
    print(f"\nSummary -> inserted: {result['inserted']}  skipped: {result['skipped']}  failed: {result['failed']}")


if __name__ == "__main__":
    main()