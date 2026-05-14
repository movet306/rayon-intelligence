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

── BACKFILL NOTES ──────────────────────────────────────────────────────────────
SunSirs restricts their English pages to the latest 6 trading days per request.
Confirmed via exhaustive investigation (2025-04-13):
  • No date-range query parameters accepted (starttime, endtime, start, end, etc.)
  • No pagination API (prodetail-{id}-{N}.html returns chart images, not data)
  • No JSON/REST endpoint available without VIP login
  • Wayback Machine (web.archive.org) has ~4-5 archived snapshots per commodity
    per year — each yields 6 rows

--backfill mode therefore uses ALL available Wayback Machine CDX snapshots
(typically going back ~12 months) plus the current live page. Expected yield:
  ~25-40 unique daily prices per commodity (not 90+)

For fuller historical depth, a paid SunSirs/100ppi.com VIP account is required.
────────────────────────────────────────────────────────────────────────────────

Usage:
    python scrapers/sunsirs_prices.py                 # scrape latest 6 rows/commodity
    python scrapers/sunsirs_prices.py --all           # same
    python scrapers/sunsirs_prices.py --dry-run       # parse only, no DB writes
    python scrapers/sunsirs_prices.py --backfill      # fetch all Wayback snapshots
    python scrapers/sunsirs_prices.py --backfill --lookback-days 730   # 2-year CDX window
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone, date, timedelta

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

# Backfill constants
WAYBACK_CDX_URL       = "http://web.archive.org/cdx/search/cdx"
WAYBACK_FETCH_BASE    = "https://web.archive.org/web"
WAYBACK_REQUEST_DELAY = 3.0   # be polite to archive.org
WAYBACK_TIMEOUT       = 30
BACKFILL_LOOKBACK_DAYS_DEFAULT = 548   # ~18 months — covers most Wayback snapshots

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
    ("polyester_staple_fiber",   BASE + "prodetail-976.html",   "RMB/ton"),  # spot (was frodetail; futures page stopped updating Apr 30)
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
# Exchange rate helper
# ---------------------------------------------------------------------------

def get_rmb_usd_rate() -> float:
    """
    Fetch live CNY→USD rate from frankfurter.app (no API key required).
    Falls back to 0.138 if the request fails.
    """
    try:
        resp = requests.get(
            "https://api.frankfurter.app/latest?from=CNY&to=USD",
            timeout=5,
        )
        rate = resp.json()["rates"]["USD"]
        log.info("Live CNY/USD rate: %.6f", rate)
        return float(rate)
    except Exception as exc:
        log.warning("Could not fetch live CNY/USD rate (%s) — using fallback 0.138", exc)
        return 0.138


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_connection():
    url = os.environ.get("RAYON_DATABASE_URL")
    if not url:
        raise RuntimeError("RAYON_DATABASE_URL environment variable is not set")
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

def _find_price_table(soup: BeautifulSoup):
    """
    Return the first HTML <table> that contains a SunSirs price format.

    SunSirs price tables (both frodetail and prodetail) always have:
      - A header row whose last cell contains 'date' or 'Date'
      - Data rows whose last cell matches YYYY-MM-DD

    This function scans ALL tables in the document so it works correctly
    on both live pages and Wayback Machine snapshots (which inject their
    own navigation tables before the price table).
    """
    date_pat = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if len(trs) < 3:          # need header + at least 2 data rows
            continue
        # Check header row
        header_cells = [th.get_text(strip=True).lower()
                        for th in trs[0].find_all(["th", "td"])]
        if len(header_cells) < 3:
            continue
        if "date" not in header_cells[-1]:
            continue
        # Confirm at least one data row with a valid date in last column
        has_data = any(
            len(td_list := tr.find_all("td")) >= 4
            and date_pat.match(td_list[-1].get_text(strip=True))
            for tr in trs[1:]
        )
        if has_data:
            return table
    return None


def parse_price_table(soup: BeautifulSoup, material: str, unit: str) -> list[dict]:
    """
    Extract price rows from a SunSirs commodity page.

    Two table formats:
      frodetail: [Commodity, Spot price, Dominant contract, Date] → col 1 = spot price
      prodetail: [Commodity, Sectors, Price, Date]                → col 2 = price

    Works on both live pages and Wayback Machine snapshots.
    Returns list of DB-ready dicts.
    """
    table = _find_price_table(soup)
    if not table:
        log.warning("  No price table found for %s", material)
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
# Backfill helpers — Wayback Machine CDX + snapshot fetching
# ---------------------------------------------------------------------------

def cdx_get_snapshots(url: str, lookback_days: int) -> list[str]:
    """
    Query the Wayback Machine CDX API for all 200-status archived snapshots
    of `url` within the last `lookback_days` days.
    Returns a list of 14-digit timestamp strings (e.g. '20260119180946').
    """
    from_dt = (date.today() - timedelta(days=lookback_days)).strftime("%Y%m%d")
    to_dt   = date.today().strftime("%Y%m%d")
    params = {
        "url":    url,
        "output": "json",
        "from":   from_dt,
        "to":     to_dt,
        "fl":     "timestamp,statuscode",
        "filter": "statuscode:200",
        "limit":  "1000",
    }
    try:
        resp = requests.get(WAYBACK_CDX_URL, params=params, timeout=WAYBACK_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.warning("  CDX query failed for %s: %s", url, e)
        return []

    if not data or len(data) < 2:
        return []

    # Deduplicate: keep one snapshot per calendar day
    seen_dates: set[str] = set()
    timestamps: list[str] = []
    for row in data[1:]:   # skip header
        ts = row[0]        # '20260119180946'
        day = ts[:8]
        if day not in seen_dates:
            seen_dates.add(day)
            timestamps.append(ts)

    return timestamps


def fetch_wayback_snapshot(session: requests.Session, timestamp: str,
                           original_url: str) -> requests.Response | None:
    """
    Fetch a single Wayback Machine snapshot.  Does NOT retry the HW_CHECK
    challenge because archive.org serves the raw cached HTML directly.
    """
    wb_url = f"{WAYBACK_FETCH_BASE}/{timestamp}/{original_url}"
    try:
        resp = session.get(wb_url, headers=HEADERS, timeout=WAYBACK_TIMEOUT)
        if resp.status_code == 200:
            return resp
        log.debug("  Wayback %s HTTP %s", timestamp, resp.status_code)
    except requests.RequestException as e:
        log.warning("  Wayback fetch error (%s): %s", timestamp, e)
    return None


def backfill_commodity(session: requests.Session, material: str, url: str,
                       unit: str, lookback_days: int, dry_run: bool,
                       conn) -> dict:
    """
    Fetch all Wayback Machine snapshots + the live page for one commodity.
    Returns {"new_dates": int, "inserted": int, "skipped": int, "snapshots": int}.
    """
    log.info("Backfill %s  (lookback=%d days)", material, lookback_days)

    # ── Step 1: CDX lookup ────────────────────────────────────────────────────
    timestamps = cdx_get_snapshots(url, lookback_days)
    log.info("  CDX found %d unique-day snapshots", len(timestamps))

    # ── Step 2: Collect all price rows across snapshots ───────────────────────
    all_rows: dict[date, dict] = {}   # keyed by period date for dedup

    def _ingest(html: str, label: str) -> int:
        """Parse HTML, add rows to all_rows. Returns count added."""
        added = 0
        soup  = BeautifulSoup(html, "html.parser")
        rows  = parse_price_table(soup, material, unit)
        for r in rows:
            if r["period"] not in all_rows:
                all_rows[r["period"]] = r
                added += 1
        return added

    # Live page first
    log.info("  Fetching live page ...")
    live_resp = fetch_page(session, url)
    if live_resp:
        n = _ingest(live_resp.text, "live")
        log.info("  Live page: %d new dates", n)
    else:
        log.warning("  Live page fetch failed")
    time.sleep(REQUEST_DELAY)

    # Wayback snapshots
    for i, ts in enumerate(timestamps):
        time.sleep(WAYBACK_REQUEST_DELAY)
        snap_resp = fetch_wayback_snapshot(session, ts, url)
        if snap_resp is None:
            log.debug("  Snapshot %s: fetch failed", ts)
            continue
        n = _ingest(snap_resp.text, ts)
        log.debug("  Snapshot %s: %d new dates  (total so far: %d)", ts, n, len(all_rows))

    # ── Step 3: Insert into DB ────────────────────────────────────────────────
    unique_rows = list(all_rows.values())
    unique_rows.sort(key=lambda r: r["period"])

    log.info("  Total unique dates collected: %d  (range: %s → %s)",
             len(unique_rows),
             unique_rows[0]["period"] if unique_rows else "—",
             unique_rows[-1]["period"] if unique_rows else "—")

    if dry_run or not unique_rows:
        return {
            "new_dates": len(unique_rows),
            "inserted": len(unique_rows) if dry_run else 0,
            "skipped": 0,
            "snapshots": len(timestamps),
        }

    # Reconnect before inserting — the Wayback fetches can take several minutes,
    # and Railway's PostgreSQL closes idle connections after ~5 minutes.
    try:
        conn.close()
    except Exception:
        pass
    try:
        fresh_conn = get_connection()
    except Exception as e:
        log.error("  DB reconnect failed: %s", e)
        return {
            "new_dates": len(unique_rows),
            "inserted": 0,
            "skipped": 0,
            "snapshots": len(timestamps),
        }

    inserted, skipped = insert_rows(fresh_conn, unique_rows)
    try:
        fresh_conn.close()
    except Exception:
        pass

    return {
        "new_dates": len(unique_rows),
        "inserted": inserted,
        "skipped": skipped,
        "snapshots": len(timestamps),
    }


def backfill(lookback_days: int = BACKFILL_LOOKBACK_DAYS_DEFAULT,
             dry_run: bool = False) -> dict:
    """
    Run backfill for all COMMODITIES.
    Each commodity reconnects to the DB just before inserting, so long Wayback
    fetches don't cause idle connection timeouts.
    Returns per-material stats dict.
    """
    # Quick connectivity check
    try:
        conn_test = get_connection()
        conn_test.close()
    except Exception as e:
        log.error("DB connection check failed: %s", e)
        return {}

    session = requests.Session()
    results: dict[str, dict] = {}

    for i, (material, url, unit) in enumerate(COMMODITIES):
        if i > 0:
            time.sleep(REQUEST_DELAY)
        # Pass None for conn — backfill_commodity creates its own fresh connection
        stats = backfill_commodity(
            session, material, url, unit, lookback_days, dry_run, conn=None
        )
        results[material] = stats

    return results


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
    parser.add_argument(
        "--backfill",
        action="store_true",
        help=(
            "Fetch all available Wayback Machine (archive.org) snapshots of each "
            "commodity page plus the current live page, then insert all unique "
            "date/price rows into the DB. "
            "SunSirs only exposes the last 6 trading days per request — no historical "
            "API exists without a paid VIP account. Backfill typically yields "
            "~25-40 unique daily prices per commodity depending on Wayback coverage."
        ),
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=BACKFILL_LOOKBACK_DAYS_DEFAULT,
        metavar="N",
        help=(
            f"How many days back to search in the Wayback Machine CDX index "
            f"(default: {BACKFILL_LOOKBACK_DAYS_DEFAULT} = ~18 months). "
            "Larger values take longer but may find older snapshots."
        ),
    )
    args = parser.parse_args()

    # ── Backfill mode ──────────────────────────────────────────────────────────
    if args.backfill:
        log.info(
            "Starting BACKFILL — %d commodities, lookback=%d days%s",
            len(COMMODITIES),
            args.lookback_days,
            ", DRY-RUN" if args.dry_run else "",
        )
        log.info(
            "NOTE: SunSirs exposes only 6 rows/page. Backfill uses Wayback Machine "
            "snapshots. Expect ~25-40 unique dates per commodity, not 90+."
        )

        results = backfill(lookback_days=args.lookback_days, dry_run=args.dry_run)

        print()
        print("─" * 70)
        print(f"{'BACKFILL RESULTS':^70}")
        print("─" * 70)
        print(f"{'Material':<35} {'Snapshots':>9} {'Dates':>7} {'Inserted':>9} {'Skipped':>8}")
        print("─" * 70)

        total_inserted = total_skipped = total_dates = 0
        for material, stats in results.items():
            ins  = stats.get("inserted", 0)
            skp  = stats.get("skipped", 0)
            snps = stats.get("snapshots", 0)
            dts  = stats.get("new_dates", 0)
            total_inserted += ins
            total_skipped  += skp
            total_dates    += dts
            label = "DRY-RUN" if args.dry_run else ""
            print(f"  {material:<33} {snps:>9} {dts:>7} {ins:>9} {skp:>8}  {label}")

        print("─" * 70)
        print(f"  {'TOTAL':<33} {'':>9} {total_dates:>7} {total_inserted:>9} {total_skipped:>8}")
        print()
        print("  NOTE: 'Dates' = unique calendar dates found across live + Wayback")
        print("        'Inserted' = new rows written to price_signals")
        print("        'Skipped' = rows already present (UNIQUE constraint)")
        print()
        print("  SunSirs restricts data to last 6 trading days per page.")
        print("  For deeper history, a paid 100ppi.com VIP account is needed.")
        return

    # ── Normal scrape mode ─────────────────────────────────────────────────────
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
