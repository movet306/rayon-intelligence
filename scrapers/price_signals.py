"""
scrapers/price_signals.py
Scrapes fiber/commodity monthly prices from IndexMundi and stores them in
the price_signals table.

Sources scraped:
  IndexMundi — Cotton       (USD/kg,  World Bank / Cotton Outlook A Index)
  IndexMundi — Coarse Wool  (USc/kg,  World Bank)
  IndexMundi — Fine Wool    (USc/kg,  World Bank)

Deduplication is enforced at the DB level via UNIQUE(material, source, period).
New months are inserted; existing rows are silently skipped (ON CONFLICT DO NOTHING).

Usage:
    python scrapers/price_signals.py           # scrape last 12 months
    python scrapers/price_signals.py --months 24
    python scrapers/price_signals.py --dry-run
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
SOURCE   = "indexmundi"
PIPELINE = "price_signals_scraper"
BASE_URL = "https://www.indexmundi.com/commodities/"

REQUEST_DELAY   = 2.0    # seconds between requests — IndexMundi rate-limits aggressively
REQUEST_TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.indexmundi.com/",
}

# Each entry: (material key stored in DB, IndexMundi slug, unit label)
# Unit comes from the page H1 but we hardcode it here for reliability.
COMMODITIES = [
    ("cotton",      "cotton",      "USD/kg"),
    ("coarse_wool", "coarse-wool", "USc/kg"),
    ("fine_wool",   "fine-wool",   "USc/kg"),
]

# Month abbreviation → month number (IndexMundi uses English 3-letter abbrevs)
MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5,  "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
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
    url = os.environ.get("RAYON_DATABASE_URL")
    if not url:
        raise RuntimeError("RAYON_DATABASE_URL environment variable is not set")
    return psycopg2.connect(url, connect_timeout=10)


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS price_signals (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    material   TEXT        NOT NULL,
    price_usd  NUMERIC(14,4),
    unit       TEXT        NOT NULL,
    source     TEXT        NOT NULL,
    period     DATE        NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (material, source, period)
);
CREATE INDEX IF NOT EXISTS price_signals_period_idx   ON price_signals (period);
CREATE INDEX IF NOT EXISTS price_signals_material_idx ON price_signals (material);
"""

INSERT_SQL = """
INSERT INTO price_signals (material, price_usd, unit, source, period, scraped_at)
VALUES (%(material)s, %(price_usd)s, %(unit)s, %(source)s, %(period)s, %(scraped_at)s)
ON CONFLICT (material, source, period) DO NOTHING
"""


def ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
    conn.commit()


def insert_price_rows(conn, rows: list[dict], dry_run: bool = False) -> tuple[int, int]:
    """
    Insert price rows. Returns (inserted_count, skipped_count).
    skipped = ON CONFLICT DO NOTHING (row already exists).
    """
    inserted = skipped = 0
    for row in rows:
        if dry_run:
            log.info("  [DRY-RUN] %s  %s  %s %s  period=%s",
                     row["material"], row["price_usd"], row["unit"],
                     row["source"], row["period"])
            inserted += 1
            continue
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


def record_failure(conn, material: str, error_message: str, error_detail: str, payload: dict):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO failed_jobs
                    (pipeline, job_type, error_message, error_detail, payload)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    PIPELINE,
                    f"scrape_{material}",
                    error_message[:500],
                    error_detail[:2000],
                    json.dumps(payload),
                ),
            )
        conn.commit()
    except Exception as e:
        log.warning("Could not write to failed_jobs: %s", e)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_month_str(month_str: str) -> date | None:
    """
    Parse IndexMundi month string like "Mar 2025" → date(2025, 3, 1).
    Returns None on parse failure.
    """
    m = re.match(r"^([A-Za-z]{3})\s+(\d{4})$", month_str.strip())
    if not m:
        return None
    month_num = MONTH_MAP.get(m.group(1))
    if not month_num:
        return None
    return date(int(m.group(2)), month_num, 1)


def fetch_commodity_prices(session: requests.Session, slug: str, months: int) -> list[dict] | None:
    """
    Fetch the IndexMundi commodity page and extract the gvPrices table.
    Returns list of {month_str, price_raw} dicts, or None on error.
    """
    url = f"{BASE_URL}?commodity={slug}&months={months}"
    try:
        resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("  Request failed for %s: %s", slug, e)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Find the price table by id (more reliable than class due to CDN caching variance)
    table = soup.find("table", id="gvPrices")
    if not table:
        # Fallback: try class
        table = soup.find("table", class_="tblData")
    if not table:
        log.warning("  No price table found for %s (page: %d bytes)", slug, len(resp.text))
        return None

    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue   # header row or malformed
        month_str = cells[0].get_text(strip=True)
        price_str = cells[1].get_text(strip=True)
        if month_str and price_str and price_str != "-":
            rows.append({"month_str": month_str, "price_raw": price_str})

    return rows


def build_price_rows(raw_rows: list[dict], material: str, unit: str) -> list[dict]:
    """
    Convert raw {month_str, price_raw} into DB-ready dicts.
    Skips rows with unparseable month or price.
    """
    now = datetime.now(timezone.utc)
    result = []
    for row in raw_rows:
        period = parse_month_str(row["month_str"])
        if period is None:
            log.debug("  Skipping unparseable month: %r", row["month_str"])
            continue
        try:
            price = float(row["price_raw"].replace(",", ""))
        except ValueError:
            log.debug("  Skipping unparseable price: %r", row["price_raw"])
            continue
        result.append({
            "material":  material,
            "price_usd": price,
            "unit":      unit,
            "source":    SOURCE,
            "period":    period,
            "scraped_at": now,
        })
    return result


# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------

def scrape(months: int = 12, dry_run: bool = False) -> dict:
    """
    Scrape all COMMODITIES for the last `months` months and upsert to DB.
    Returns {"inserted": int, "skipped": int, "failed": int}.
    """
    total_inserted = total_skipped = total_failed = 0

    try:
        conn = get_connection()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return {"inserted": 0, "skipped": 0, "failed": -1, "error": str(e)}

    if not dry_run:
        ensure_table(conn)

    session = requests.Session()

    for i, (material, slug, unit) in enumerate(COMMODITIES):
        if i > 0:
            time.sleep(REQUEST_DELAY)

        log.info("Fetching %s (%s, last %d months)...", material, slug, months)

        raw_rows = fetch_commodity_prices(session, slug, months)
        if raw_rows is None:
            total_failed += 1
            record_failure(
                conn,
                material=material,
                error_message="Failed to fetch or parse price table",
                error_detail=f"slug={slug} months={months}",
                payload={"material": material, "slug": slug},
            )
            continue

        price_rows = build_price_rows(raw_rows, material, unit)
        log.info("  Parsed %d price rows", len(price_rows))
        for r in price_rows[:3]:
            log.info("    %s  %.4f %s", r["period"], r["price_usd"], r["unit"])

        ins, skp = insert_price_rows(conn, price_rows, dry_run=dry_run)
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
        description="Scrape fiber/commodity prices from IndexMundi into price_signals"
    )
    parser.add_argument(
        "--months",
        type=int,
        default=12,
        metavar="N",
        help="How many months of history to fetch (default: 12)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse data, print rows, but do not write to DB",
    )
    args = parser.parse_args()

    log.info(
        "Starting %s (months=%d%s)",
        PIPELINE, args.months, ", DRY-RUN" if args.dry_run else "",
    )

    result = scrape(months=args.months, dry_run=args.dry_run)

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
