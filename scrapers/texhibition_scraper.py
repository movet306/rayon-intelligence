"""
scrapers/texhibition_scraper.py
Scrapes the exhibitor directory from texhibitionist.com and stores results
in the fair_exhibitors table.  Then cross-references against the entities
table to emit market_signals with signal_type='fair_participation'.

The site uses Laravel/Livewire and serves static HTML with pagination via
?page=N query parameter.  Each listing page has ~15 exhibitors; detail pages
provide full_name, website, and certificates.

Usage:
    python scrapers/texhibition_scraper.py                # listing only, all pages
    python scrapers/texhibition_scraper.py --details      # also fetch detail pages
    python scrapers/texhibition_scraper.py --fair "Texhibition Istanbul" --year 2026
    python scrapers/texhibition_scraper.py --pages 2      # first 2 listing pages only

Fair info (as of 2026):
    Texhibition Istanbul — 9-11 September 2026, Istanbul Expo Center
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
PIPELINE     = "texhibition_scraper"
LISTING_BASE = "https://www.texhibitionist.com/en/katilimcilar"
DETAIL_BASE  = "https://www.texhibitionist.com/en/katilimcilar/"

DEFAULT_FAIR = "Texhibition Istanbul"
DEFAULT_YEAR = 2026
DEFAULT_COUNTRY = "TR"

REQUEST_DELAY   = 1.5   # seconds between requests
REQUEST_TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

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


def create_table_if_missing(conn):
    """Ensure fair_exhibitors table exists (idempotent)."""
    ddl = """
    CREATE TABLE IF NOT EXISTS fair_exhibitors (
        id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        fair_name       TEXT        NOT NULL,
        fair_year       INTEGER     NOT NULL,
        name            TEXT        NOT NULL,
        full_name       TEXT,
        slug            TEXT        NOT NULL,
        country         TEXT        NOT NULL DEFAULT 'TR',
        categories      TEXT[]      NOT NULL DEFAULT '{}',
        booth           TEXT,
        website         TEXT,
        certificates    TEXT[]      NOT NULL DEFAULT '{}',
        export_markets  TEXT,
        detail_url      TEXT,
        scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (fair_name, fair_year, slug)
    );
    CREATE INDEX IF NOT EXISTS fair_exhibitors_fair_idx
        ON fair_exhibitors (fair_name, fair_year);
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute(ddl)


UPSERT_SQL = """
INSERT INTO fair_exhibitors
    (fair_name, fair_year, name, full_name, slug, country, categories,
     booth, website, certificates, export_markets, detail_url, scraped_at)
VALUES
    (%(fair_name)s, %(fair_year)s, %(name)s, %(full_name)s, %(slug)s,
     %(country)s, %(categories)s, %(booth)s, %(website)s,
     %(certificates)s, %(export_markets)s, %(detail_url)s, %(scraped_at)s)
ON CONFLICT (fair_name, fair_year, slug) DO UPDATE SET
    name           = EXCLUDED.name,
    full_name      = EXCLUDED.full_name,
    categories     = EXCLUDED.categories,
    booth          = EXCLUDED.booth,
    website        = COALESCE(EXCLUDED.website, fair_exhibitors.website),
    certificates   = CASE
                       WHEN array_length(EXCLUDED.certificates, 1) > 0
                       THEN EXCLUDED.certificates
                       ELSE fair_exhibitors.certificates
                     END,
    export_markets = COALESCE(EXCLUDED.export_markets, fair_exhibitors.export_markets),
    scraped_at     = EXCLUDED.scraped_at
RETURNING id, xmax
"""


def upsert_exhibitor(conn, row: dict) -> tuple[str, str]:
    """Insert or update one exhibitor. Returns (id, 'inserted'|'updated')."""
    with conn:
        with conn.cursor() as cur:
            cur.execute(UPSERT_SQL, row)
            result = cur.fetchone()
            exhibitor_id = str(result[0])
            action = "inserted" if result[1] == 0 else "updated"
    return exhibitor_id, action


def record_failure(conn, url: str | None, error_message: str, error_detail: str, payload: dict):
    try:
        with conn:
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
    except Exception as e:
        log.warning("Could not write to failed_jobs: %s", e)


def find_matching_company(conn, exhibitor_name: str) -> tuple[str, str] | None:
    """
    Return (entity_id, company_name) if any row in entities matches
    the exhibitor name via case-insensitive substring or equality.
    Returns None if no match.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name
            FROM   entities
            WHERE  lower(name) = lower(%(n)s)
               OR  lower(%(n)s) LIKE '%%' || lower(name) || '%%'
               OR  lower(name)  LIKE '%%' || lower(%(n)s) || '%%'
            LIMIT 1
            """,
            {"n": exhibitor_name},
        )
        row = cur.fetchone()
    return (str(row[0]), row[1]) if row else None


def emit_fair_participation_signal(
    conn, entity_id: str, company_name: str,
    exhibitor_id: str, fair_name: str, fair_year: int, booth: str | None
):
    """Insert a market_signal for a company found exhibiting at the fair."""
    title = f"{company_name} exhibiting at {fair_name} {fair_year}"
    body = f"Booth: {booth}" if booth else None
    tags = [f"fair:{fair_name}", f"year:{fair_year}"]

    # Deduplicate: skip if we already have a signal for this company+fair+year
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM market_signals
            WHERE  signal_type = 'fair_participation'
              AND  entity_id  = %s
              AND  tags @> %s::text[]
            LIMIT 1
            """,
            (entity_id, tags),
        )
        if cur.fetchone():
            return False   # already exists

    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO market_signals
                    (signal_type, severity, title, body, entity_id, tags)
                VALUES ('fair_participation', 'info', %s, %s, %s, %s)
                """,
                (title, body, entity_id, tags),
            )
    log.info("  [SIGNAL] %s — %s %d %s", company_name, fair_name, fair_year, booth or "")
    return True


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def fetch(session: requests.Session, url: str) -> requests.Response | None:
    """Fetch a page; return Response or None on error."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        log.warning("  Request failed for %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Listing page parsing
# ---------------------------------------------------------------------------

def parse_listing_page(html: str, fair_name: str, fair_year: int) -> list[dict]:
    """
    Parse one listing page.  Returns list of partial exhibitor dicts
    (no detail-page fields yet).
    """
    soup = BeautifulSoup(html, "lxml")
    now = datetime.now(timezone.utc)
    results = []

    for a in soup.select('a[href*="/en/katilimcilar/"]'):
        href = a.get("href", "")
        # Exclude the back-link (just /en/katilimcilar with no slug)
        slug = href.rstrip("/").split("/")[-1]
        if not slug or slug == "katilimcilar":
            continue

        item = a.select_one("div.item")
        if not item:
            continue

        title_el    = item.select_one(".title")
        category_el = item.select_one(".category")
        location_el = item.select_one(".location")

        name = title_el.get_text(strip=True) if title_el else slug.upper()
        if not name:
            continue

        categories_raw = category_el.get_text(strip=True) if category_el else ""
        categories = [c.strip() for c in categories_raw.split(",") if c.strip()]

        booth = location_el.get_text(strip=True) if location_el else None

        results.append({
            "fair_name":      fair_name,
            "fair_year":      fair_year,
            "name":           name,
            "full_name":      None,
            "slug":           slug,
            "country":        DEFAULT_COUNTRY,
            "categories":     categories,
            "booth":          booth,
            "website":        None,
            "certificates":   [],
            "export_markets": None,
            "detail_url":     href,
            "scraped_at":     now,
        })

    return results


def get_last_page(html: str) -> int:
    """Extract the highest page number from pagination links."""
    soup = BeautifulSoup(html, "lxml")
    max_page = 1
    for a in soup.select('.pagination a[href*="page="]'):
        m = re.search(r"page=(\d+)", a.get("href", ""))
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page


# ---------------------------------------------------------------------------
# Detail page parsing
# ---------------------------------------------------------------------------

def parse_detail_page(html: str) -> dict:
    """
    Parse exhibitor detail page.
    Returns dict with keys: full_name, website, certificates, export_markets.
    All values may be None/empty list.
    """
    soup = BeautifulSoup(html, "lxml")
    section = soup.select_one("section.exhibitors.sub.detail")
    if not section:
        return {}

    info = section.select_one(".info")
    if not info:
        return {}

    full_name_el = info.select_one(".title")
    full_name = full_name_el.get_text(strip=True) if full_name_el else None

    # Key-value pairs in div.company-contact
    kv = {}
    for item in info.select("div.company-contact div.item"):
        key_el   = item.select_one(".key")
        value_el = item.select_one(".value")
        if key_el and value_el:
            k = key_el.get_text(strip=True).rstrip(":").strip().lower()
            v = value_el.get_text(strip=True)
            if v and v != "--":
                kv[k] = v

    website        = kv.get("web site")
    export_markets = kv.get("export markets")

    # Certificates: div.title inside section.photo.certificate
    certs = []
    cert_section = soup.select_one("section.photo.certificate")
    if cert_section:
        certs = [
            t.get_text(strip=True)
            for t in cert_section.select("div.title")
            if t.get_text(strip=True)
        ]

    return {
        "full_name":      full_name,
        "website":        website,
        "certificates":   certs,
        "export_markets": export_markets,
    }


# ---------------------------------------------------------------------------
# Main scrape function
# ---------------------------------------------------------------------------

def scrape(
    fair_name: str = DEFAULT_FAIR,
    fair_year: int = DEFAULT_YEAR,
    fetch_details: bool = False,
    max_pages: int | None = None,
) -> dict:
    """
    Scrape exhibitor listing (and optionally detail pages).
    Returns {"inserted": int, "updated": int, "signals": int, "failed": int}.
    """
    inserted = updated = signals = failed = 0

    try:
        conn = get_connection()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return {"inserted": 0, "updated": 0, "signals": 0, "failed": -1, "error": str(e)}

    create_table_if_missing(conn)
    session = requests.Session()

    # --- Step 1: determine total pages ---
    log.info("Fetching listing page 1 to discover pagination ...")
    resp = fetch(session, LISTING_BASE)
    if resp is None:
        conn.close()
        return {"inserted": 0, "updated": 0, "signals": 0, "failed": 1,
                "error": "Could not fetch listing page 1"}

    total_pages = get_last_page(resp.text)
    if max_pages:
        total_pages = min(total_pages, max_pages)

    log.info("Total listing pages: %d", total_pages)

    # --- Step 2: collect all exhibitors from listing pages ---
    all_exhibitors: list[dict] = []

    page1_items = parse_listing_page(resp.text, fair_name, fair_year)
    all_exhibitors.extend(page1_items)
    log.info("  Page 1/%d — %d exhibitors", total_pages, len(page1_items))

    for page_num in range(2, total_pages + 1):
        time.sleep(REQUEST_DELAY)
        url = f"{LISTING_BASE}?page={page_num}"
        resp = fetch(session, url)
        if resp is None:
            failed += 1
            record_failure(conn, url, "Listing page fetch failed", f"page={page_num}", {"page": page_num})
            continue
        items = parse_listing_page(resp.text, fair_name, fair_year)
        all_exhibitors.extend(items)
        log.info("  Page %d/%d — %d exhibitors (running total: %d)",
                 page_num, total_pages, len(items), len(all_exhibitors))

    log.info("Listing complete: %d exhibitors across %d pages", len(all_exhibitors), total_pages)

    # --- Step 3: optionally enrich with detail pages ---
    if fetch_details:
        log.info("Fetching detail pages for %d exhibitors ...", len(all_exhibitors))
        for i, ex in enumerate(all_exhibitors):
            time.sleep(REQUEST_DELAY)
            detail_url = ex.get("detail_url") or DETAIL_BASE + ex["slug"]
            log.debug("  [%d/%d] %s", i + 1, len(all_exhibitors), detail_url)
            resp = fetch(session, detail_url)
            if resp is None:
                failed += 1
                record_failure(conn, detail_url, "Detail page fetch failed",
                               f"slug={ex['slug']}", {"slug": ex["slug"]})
                continue
            detail = parse_detail_page(resp.text)
            if detail.get("full_name"):
                ex["full_name"] = detail["full_name"]
            if detail.get("website"):
                ex["website"] = detail["website"]
            if detail.get("certificates"):
                ex["certificates"] = detail["certificates"]
            if detail.get("export_markets"):
                ex["export_markets"] = detail["export_markets"]

    # --- Step 4: upsert into DB and cross-reference ---
    log.info("Upserting %d exhibitors into fair_exhibitors ...", len(all_exhibitors))
    for ex in all_exhibitors:
        try:
            exhibitor_id, action = upsert_exhibitor(conn, ex)
            if action == "inserted":
                inserted += 1
            else:
                updated += 1
            log.debug("  [%s] %s (%s)", action, ex["name"], ex.get("booth", ""))

            # Cross-reference with entities table
            match = find_matching_company(conn, ex["name"])
            if match:
                entity_id, company_name = match
                emitted = emit_fair_participation_signal(
                    conn, entity_id, company_name,
                    exhibitor_id, fair_name, fair_year, ex.get("booth"),
                )
                if emitted:
                    signals += 1

        except psycopg2.Error as e:
            failed += 1
            log.warning("  DB error for %s: %s", ex["name"], e)
            record_failure(conn, ex.get("detail_url"), str(e), repr(e),
                           {"slug": ex["slug"], "name": ex["name"]})
        except Exception as e:
            failed += 1
            log.warning("  Unexpected error for %s: %s", ex["name"], e)

    conn.close()
    return {"inserted": inserted, "updated": updated, "signals": signals, "failed": failed}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape Texhibition Istanbul exhibitor directory"
    )
    parser.add_argument(
        "--fair",
        default=DEFAULT_FAIR,
        help=f"Fair name to store (default: {DEFAULT_FAIR!r})",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=DEFAULT_YEAR,
        help=f"Fair edition year (default: {DEFAULT_YEAR})",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Also fetch each exhibitor detail page (slower; adds full_name, website, certs)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=None,
        metavar="N",
        help="Limit to first N listing pages (default: all)",
    )
    args = parser.parse_args()

    log.info(
        "Starting %s (fair=%r, year=%d, details=%s, pages=%s)",
        PIPELINE, args.fair, args.year,
        args.details, args.pages or "all",
    )

    result = scrape(
        fair_name=args.fair,
        fair_year=args.year,
        fetch_details=args.details,
        max_pages=args.pages,
    )

    print(
        f"\nSummary — inserted: {result['inserted']}  "
        f"updated: {result['updated']}  "
        f"signals: {result['signals']}  "
        f"failed: {result['failed']}"
    )

    if result.get("error"):
        print(f"Fatal error: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
