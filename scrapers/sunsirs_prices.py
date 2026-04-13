"""
scrapers/sunsirs_prices.py
Scrapes daily fiber, yarn, and raw-material prices from SunSirs
(www.sunsirs.com/uk/) and inserts them into the price_signals table.

SunSirs protects pages with a lightweight JS cookie challenge (HW_CHECK).
This scraper detects the challenge, extracts the cookie, and retries — no
headless browser required.

Two page types exist on SunSirs; both are handled automatically:
  frodetail  — futures + spot data: columns [Commodity, Spot price, Dominant contract, Date]
  prodetail  — spot price only:     columns [Commodity, Sectors, Price, Date]

Each page returns the last 6 trading days. All rows are upserted; the
UNIQUE(material, source, period) constraint silently skips duplicates.

Prices are stored in RMB/ton as published. Use the RMB_USD_RATE env var
(see .env.example) for downstream USD conversions.

Usage:
    python scrapers/sunsirs_prices.py            # scrape all commodities
    python scrapers/sunsirs_prices.py --all      # same
    python scrapers/sunsirs_prices.py --dry-run  # parse only, no DB writes
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone, date

import psycopg2
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SOURCE   = "sunsirs"
PIPELINE = "sunsirs_prices_scraper"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.sunsirs.com/uk/",
}
REQUEST_TIMEOUT   = 20
REQUEST_DELAY     = 2.0   # seconds between commodity page requests
CHALLENGE_WAIT    = 0.9   # seconds to wait after setting the HW_CHECK cookie
MAX_RETRIES       = 3

# ---------------------------------------------------------------------------
# Commodity list
# Correct URLs discovered from https://www.sunsirs.com/uk/sectors-16.html
#
# Format: (material_key, url, unit)
# The user-provided URLs for several commodities pointed to stale/wrong pages;
# confirmed live URLs are used here instead.
# ---------------------------------------------------------------------------
BASE = "https://www.sunsirs.com/uk/"

COMMODITIES = [
    # material_key                url                            unit
    ("polyester_staple_fiber",   BASE + "frodetail-976.html",   "RMB/ton"),  # spot + futures
    ("polyester_fdy",            BASE + "prodetail-1005.html",  "RMB/ton"),
    ("polyester_poy",            BASE + "prodetail-1006.html",  "RMB/ton"),
    ("polyester_dty",            BASE + "prodetail-1007.html",  "RMB/ton"),
    ("polyamide_fdy",            BASE + "prodetail-911.html",   "RMB/ton"),  # nylon
    ("cotton_lint",              BASE + "prodetail-344.html",   "RMB/ton"),
    ("cotton_yarn",              BASE + "prodetail-904.html",   "RMB/ton"),
    ("rayon_yarn",               BASE + "prodetail-946.html",   "RMB/ton"),
    ("polyester_yarn",           BASE + "prodetail-1241.html",  "RMB/ton"),
    ("pa6_chip",                 BASE + "prodetail-102.html",   "RMB/ton"),
    ("pa66_chip",                BASE + "prodetail-1224.html",  "RMB/ton"),
    ("pta",                      BASE + "prodetail-356.html",   "RMB/ton"),  # polyester raw material
    ("adipic_acid",              BASE + "prodetail-837.html",   "RMB/ton"),  # pa66 raw material
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


INSERT_SQL = """
INSERT INTO price_signals (material, price_usd, unit, source, period, scraped_at)
VALUES (%(material)s, %(price_usd)s, %(unit)s, %(source)s, %(period)s, %(scraped_at)s)
ON CONFLICT (material, source, period) DO NOTHING
"""


def insert_rows(conn, rows: list[dict]) -> tuple[int, int]:
    """Insert rows. Returns (inserted, skipped_duplicates)."""
    inserted = skipped = 0
    for row in rows:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(INSERT_SQL, row)
                    if cur.rowcount:
                        inserted += 1
                    else:
                        skipped += 1
        except psycopg2.Error as e:
            log.warning("DB error for %s/%s: %s", row["material"], row["period"], e)
    return inserted, skipped


def record_failure(conn, material: str, url: str, error_message: str,
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
                    PIPELINE,
                    f"scrape_{material}",
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
# HTTP + challenge bypass
# ---------------------------------------------------------------------------

def fetch_page(session: requests.Session, url: str) -> requests.Response | None:
    """
    Fetch a SunSirs page, handling the HW_CHECK JS cookie challenge.
    Returns the Response with the real page content, or None on failure.
    """
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("  Request error (attempt %d): %s", attempt + 1, e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(1.0)
            continue

        html = resp.text

        # Detect JS cookie challenge: small page (~600 bytes) with HW_CHECK setter
        m = re.search(r'var _0x2 = "([a-f0-9]+)"', html)
        if m:
            cookie_val = m.group(1)
            log.debug("  [attempt %d] JS challenge detected — setting HW_CHECK cookie", attempt + 1)
            session.cookies.set("HW_CHECK", cookie_val, domain="www.sunsirs.com", path="/")
            time.sleep(CHALLENGE_WAIT)
            continue

        return resp   # real content

    log.warning("  Failed to bypass JS challenge after %d attempts: %s", MAX_RETRIES, url)
    return None


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def parse_price_table(soup: BeautifulSoup, material: str, unit: str) -> list[dict]:
    """
    Extract price rows from a SunSirs commodity page.

    Two table formats:
      frodetail: [Commodity, Spot price, Dominant contract, Date] → col 1 = spot price
      prodetail: [Commodity, Sectors, Price, Date]                → col 2 = price

    Returns list of DB-ready dicts.
    """
    table = soup.find("table")
    if not table:
        log.warning("  No table found for %s", material)
        return []

    now = datetime.now(timezone.utc)
    rows = []

    # Detect format from header row
    header_row = table.find("tr")
    if not header_row:
        return []
    headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

    # frodetail: "spot price" in headers at col 1
    # prodetail: "sectors" in headers at col 1, "price" at col 2
    is_frodetail = any("spot" in h for h in headers)

    date_col  = 3   # always col index 3
    price_col = 1 if is_frodetail else 2

    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 4:
            continue   # header or short row

        price_str = cells[price_col]
        date_str  = cells[date_col]

        # Validate date
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            continue
        try:
            period = date.fromisoformat(date_str)
        except ValueError:
            continue

        # Validate price
        try:
            price_val = float(price_str.replace(",", ""))
        except ValueError:
            continue

        if price_val <= 0:
            continue

        rows.append({
            "material":   material,
            "price_usd":  price_val,   # stored as-is in RMB; unit col clarifies
            "unit":       unit,
            "source":     SOURCE,
            "period":     period,
            "scraped_at": now,
        })

    return rows


# ---------------------------------------------------------------------------
# Main scrape loop
# ---------------------------------------------------------------------------

def scrape(dry_run: bool = False) -> dict:
    """Scrape all COMMODITIES. Returns {"inserted": int, "skipped": int, "failed": int}."""
    total_inserted = total_skipped = total_failed = 0

    try:
        conn = get_connection()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return {"inserted": 0, "skipped": 0, "failed": -1, "error": str(e)}

    session = requests.Session()

    for i, (material, url, unit) in enumerate(COMMODITIES):
        if i > 0:
            time.sleep(REQUEST_DELAY)

        log.info("Fetching %s ...", material)

        resp = fetch_page(session, url)
        if resp is None:
            total_failed += 1
            record_failure(
                conn,
                material=material,
                url=url,
                error_message="Failed to fetch page after retries",
                error_detail=f"url={url}",
                payload={"material": material, "url": url},
            )
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        price_rows = parse_price_table(soup, material, unit)

        if not price_rows:
            total_failed += 1
            log.warning("  No price rows parsed for %s", material)
            record_failure(
                conn,
                material=material,
                url=url,
                error_message="No price rows parsed from table",
                error_detail=f"url={url} response_len={len(resp.text)}",
                payload={"material": material, "url": url},
            )
            continue

        log.info("  Parsed %d rows  (latest: %s = %.2f %s)",
                 len(price_rows),
                 price_rows[0]["period"],
                 price_rows[0]["price_usd"],
                 unit)

        if dry_run:
            for r in price_rows:
                log.info("  [DRY-RUN] %s  %s  %.2f %s",
                         r["material"], r["period"], r["price_usd"], r["unit"])
            total_inserted += len(price_rows)
            continue

        ins, skp = insert_rows(conn, price_rows)
        total_inserted += ins
        total_skipped  += skp
        log.info("  Inserted: %d  Already present: %d", ins, skp)

    conn.close()
    return {"inserted": total_inserted, "skipped": total_skipped, "failed": total_failed}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape fiber/yarn prices from SunSirs into price_signals"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scrape all commodities (default behavior; flag provided for explicitness)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse data, print rows, but do not write to DB",
    )
    args = parser.parse_args()

    log.info(
        "Starting %s (%d commodities%s)",
        PIPELINE,
        len(COMMODITIES),
        ", DRY-RUN" if args.dry_run else "",
    )

    result = scrape(dry_run=args.dry_run)

    print(
        f"\nSummary — inserted: {result['inserted']}  "
        f"already_present: {result['skipped']}  "
        f"failed: {result['failed']}"
    )

    if result.get("error"):
        print(f"Fatal error: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
