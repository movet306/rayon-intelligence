"""
TIM (Turkish Exporters Assembly) news scraper.
Source: https://tim.org.tr/tr/haberler
Pagination: ?page=N (~17 pages, ~30-35 articles total; site shows 2 per page).
HTML: <a class="card has-image" title="..." href="/tr/{slug}"> inside <div class="list-news">.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

SOURCE = "tim"
BASE_URL = "https://tim.org.tr"
LISTING_URL = f"{BASE_URL}/tr/haberler"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
}
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 0.5

TR_MONTHS = {
    "ocak": 1, "\u015fubat": 2, "mart": 3, "nisan": 4, "may\u0131s": 5, "haziran": 6,
    "temmuz": 7, "a\u011fustos": 8, "eyl\u00fcl": 9, "ekim": 10, "kas\u0131m": 11, "aral\u0131k": 12,
}

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger(SOURCE)


def get_conn():
    return psycopg2.connect(os.environ["RAYON_DATABASE_URL"])


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
    """Parse Turkish date 'DD Month YYYY' from anywhere in text."""
    if not text:
        return None
    months_pattern = "|".join(TR_MONTHS.keys())
    m = re.search(rf"(\d{{1,2}})\s+({months_pattern})\s+(\d{{4}})", text.lower())
    if m:
        try:
            day = int(m.group(1))
            month = TR_MONTHS[m.group(2)]
            year = int(m.group(3))
            return datetime(year, month, day, tzinfo=timezone.utc)
        except (ValueError, KeyError):
            pass
    return None


def parse_listing(soup: BeautifulSoup) -> list[dict]:
    """Extract TIM article URLs. TIM uses <a class="card has-image"> cards."""
    items = []
    seen = set()
    for link in soup.find_all("a", class_="card", href=True):
        href = link["href"]
        if any(ext in href.lower() for ext in [".pdf", ".jpg", ".png", ".docx", ".xlsx"]):
            continue
        if href.startswith("http"):
            if BASE_URL not in href:
                continue
            full_url = href
        elif href.startswith("/"):
            full_url = f"{BASE_URL}{href}"
        else:
            continue
        clean_url = full_url.split("?")[0].rstrip("/")
        if clean_url in seen:
            continue
        seen.add(clean_url)
        text = link.get_text(strip=True)
        title_attr = link.get("title", "").strip()
        title = title_attr if title_attr else text
        date = parse_date(text)
        items.append({"url": full_url, "title": title, "date_hint": date})
    return items


def parse_article(soup: BeautifulSoup) -> dict:
    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else None
    container = soup.find("article") or soup.find("main") or soup
    body_parts = []
    for p in container.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if len(txt) > 50:
            body_parts.append(txt)
    body_raw = "\n\n".join(body_parts) if body_parts else None
    return {"title": title, "body_raw": body_raw}


def insert_news_item(cur, url, title, body_raw, published_at):
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
            page_url = LISTING_URL if page == 1 else f"{LISTING_URL}?page={page}"
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
                published_at = item.get("date_hint")
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
    parser = argparse.ArgumentParser(description=f"{SOURCE} scraper - TIM (Turkish Exporters Assembly) news")
    parser.add_argument("--pages", type=int, default=1, help="Listing pages (default: 1, max ~17)")
    args = parser.parse_args()
    log.info("Starting %s scraper (pages=%d)", SOURCE, args.pages)
    result = scrape(pages=args.pages)
    print(f"\nSummary -> inserted: {result['inserted']}  skipped: {result['skipped']}  failed: {result['failed']}")


if __name__ == "__main__":
    main()