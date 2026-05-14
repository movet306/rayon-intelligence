"""
scrapers/trade_flows.py
Fetches Turkey's monthly textile export data from the UN Comtrade API
and inserts it into the trade_flows table.

─────────────────────────────────────────────────────
API KEY (free)
─────────────────────────────────────────────────────
Register at https://comtradeapi.un.org/ → "Get API Key" (free tier).
Free tier: 500 requests / day, 500 rows / response.

Set the key in .env:
    COMTRADE_API_KEY=<your-subscription-key>

Without a key the scraper falls back to the public preview endpoint
(same 500-row cap, no daily limit stated — suitable for testing).

─────────────────────────────────────────────────────
Target HS codes (4-digit, woven/knit fabric + upstream yarn)
─────────────────────────────────────────────────────
  5407  Woven fabrics of synthetic filament yarn (polyester/nylon wovens)
  6006  Other knitted or crocheted fabrics
  5512  Woven fabrics of synthetic staple fibers, ≥ 85 %
  5515  Other woven fabrics of synthetic staple fibers
  6001  Pile fabrics, knitted or crocheted
  5402  Synthetic filament yarn (upstream)
  5509  Yarn of synthetic staple fibers (upstream)

─────────────────────────────────────────────────────
Usage
─────────────────────────────────────────────────────
  python scrapers/trade_flows.py             # last 12 months
  python scrapers/trade_flows.py --months 6  # last 6 months
  python scrapers/trade_flows.py --months 24 # back-fill 2 years
  python scrapers/trade_flows.py --dry-run   # parse only, no DB writes
"""

import argparse
import json
import logging
import os
import sys
import time
from calendar import monthrange
from datetime import date, datetime, timezone
from dateutil.relativedelta import relativedelta

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SOURCE    = "comtrade"
PIPELINE  = "comtrade_trade_flows"

REPORTER_ISO2  = "TR"
REPORTER_CODE  = 792           # UN M49 / ISO 3166-1 numeric for Turkey
FLOW_CODE      = "X"           # X = exports
FLOW_DIRECTION = "export"      # matches trade_flow_direction enum

PUBLIC_URL = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
AUTH_URL   = "https://comtradeapi.un.org/data/v1/get/C/M/HS"

REQUEST_DELAY   = 1.5          # seconds between API calls
REQUEST_TIMEOUT = 30

# HS codes relevant to Rayon Tekstil
HS_CODES = ["5407", "6006", "5512", "5515", "6001", "5402", "5509", "5510", "5903"]

HS_DESCRIPTIONS = {
    "5407": "Woven fabrics of synthetic filament yarn",
    "6006": "Other knitted or crocheted fabrics",
    "5512": "Woven fabrics of synthetic staple fibers (>=85%)",
    "5515": "Other woven fabrics of synthetic staple fibers",
    "6001": "Pile fabrics, knitted or crocheted",
    "5402": "Synthetic filament yarn (not retail)",
    "5509": "Yarn of synthetic staple fibers (not retail)",
    "5510": "Yarn of artificial staple fibers (viscose/modal/lyocell)",
    "5903": "Textile fabrics impregnated, coated, covered or laminated with plastics",
}

# UN M49 numeric code → ISO 3166-1 alpha-2
# Covers Turkey's main trading partners; extend as needed.
M49_TO_ISO2: dict[int, str | None] = {
    0:    None,   # World aggregate → partner_country = NULL
    8:    "AL",   # Albania
    12:   "DZ",   # Algeria
    31:   "AZ",   # Azerbaijan
    36:   "AU",   # Australia
    40:   "AT",   # Austria
    50:   "BD",   # Bangladesh
    56:   "BE",   # Belgium
    64:   "BT",   # Bhutan
    68:   "BO",   # Bolivia
    76:   "BR",   # Brazil
    100:  "BG",   # Bulgaria
    104:  "MM",   # Myanmar
    112:  "BY",   # Belarus
    116:  "KH",   # Cambodia
    120:  "CM",   # Cameroon
    124:  "CA",   # Canada
    144:  "LK",   # Sri Lanka
    152:  "CL",   # Chile
    156:  "CN",   # China
    170:  "CO",   # Colombia
    191:  "HR",   # Croatia
    196:  "CY",   # Cyprus
    203:  "CZ",   # Czech Republic
    208:  "DK",   # Denmark
    218:  "EC",   # Ecuador
    818:  "EG",   # Egypt (numeric 818)
    233:  "EE",   # Estonia
    231:  "ET",   # Ethiopia
    246:  "FI",   # Finland
    250:  "FR",   # France
    276:  "DE",   # Germany
    288:  "GH",   # Ghana
    300:  "GR",   # Greece
    348:  "HU",   # Hungary
    356:  "IN",   # India
    360:  "ID",   # Indonesia
    364:  "IR",   # Iran
    368:  "IQ",   # Iraq
    372:  "IE",   # Ireland
    376:  "IL",   # Israel
    380:  "IT",   # Italy
    388:  "JM",   # Jamaica
    392:  "JP",   # Japan
    400:  "JO",   # Jordan
    398:  "KZ",   # Kazakhstan
    404:  "KE",   # Kenya
    408:  "KP",   # North Korea
    410:  "KR",   # South Korea
    414:  "KW",   # Kuwait
    417:  "KG",   # Kyrgyzstan
    422:  "LB",   # Lebanon
    428:  "LV",   # Latvia
    440:  "LT",   # Lithuania
    442:  "LU",   # Luxembourg
    434:  "LY",   # Libya
    458:  "MY",   # Malaysia
    484:  "MX",   # Mexico
    498:  "MD",   # Moldova
    504:  "MA",   # Morocco
    528:  "NL",   # Netherlands
    554:  "NZ",   # New Zealand
    566:  "NG",   # Nigeria
    578:  "NO",   # Norway
    586:  "PK",   # Pakistan
    604:  "PE",   # Peru
    608:  "PH",   # Philippines
    616:  "PL",   # Poland
    620:  "PT",   # Portugal
    642:  "RO",   # Romania
    643:  "RU",   # Russia
    682:  "SA",   # Saudi Arabia
    694:  "SL",   # Sierra Leone
    703:  "SK",   # Slovakia
    705:  "SI",   # Slovenia
    710:  "ZA",   # South Africa
    724:  "ES",   # Spain
    752:  "SE",   # Sweden
    756:  "CH",   # Switzerland
    760:  "SY",   # Syria
    762:  "TJ",   # Tajikistan
    764:  "TH",   # Thailand
    788:  "TN",   # Tunisia
    795:  "TM",   # Turkmenistan
    804:  "UA",   # Ukraine
    784:  "AE",   # United Arab Emirates
    826:  "GB",   # United Kingdom
    840:  "US",   # United States (numeric 840)
    842:  "US",   # United States (Comtrade uses 842)
    860:  "UZ",   # Uzbekistan
    862:  "VE",   # Venezuela
    704:  "VN",   # Vietnam
    887:  "YE",   # Yemen
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
    return psycopg2.connect(
        url,
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )


def ensure_hs_description_column(conn):
    """Add hs_description column to trade_flows if it doesn't exist yet."""
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'trade_flows' AND column_name = 'hs_description'
            """)
            if not cur.fetchone():
                cur.execute("ALTER TABLE trade_flows ADD COLUMN hs_description TEXT")
                log.info("Added hs_description column to trade_flows")


INSERT_SQL = """
INSERT INTO trade_flows
    (source, reporter_country, partner_country, hs_code, hs_description,
     flow_direction, period, period_type, value_usd, quantity_kg, scraped_at)
VALUES
    (%(source)s, %(reporter_country)s, %(partner_country)s, %(hs_code)s, %(hs_description)s,
     %(flow_direction)s::trade_flow_direction, %(period)s, %(period_type)s::period_granularity,
     %(value_usd)s, %(quantity_kg)s, %(scraped_at)s)
ON CONFLICT (source, reporter_country, partner_country, hs_code, flow_direction, period, period_type)
    DO UPDATE SET
        value_usd      = EXCLUDED.value_usd,
        quantity_kg    = EXCLUDED.quantity_kg,
        hs_description = EXCLUDED.hs_description,
        scraped_at     = EXCLUDED.scraped_at
RETURNING id, xmax
"""


def upsert_row(conn, row: dict) -> str:
    """Insert/update one trade flow row. Returns 'inserted' or 'updated'."""
    with conn:
        with conn.cursor() as cur:
            cur.execute(INSERT_SQL, row)
            result = cur.fetchone()
            return "inserted" if result[1] == 0 else "updated"


def record_failure(conn, url: str | None, error_message: str,
                   error_detail: str, payload: dict):
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO failed_jobs
                        (pipeline, job_type, url, error_message, error_detail, payload)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (PIPELINE, "scrape", url,
                     error_message[:500], error_detail[:2000],
                     json.dumps(payload)),
                )
    except Exception as e:
        log.warning("Could not write to failed_jobs: %s", e)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def build_session(api_key: str | None) -> requests.Session:
    session = requests.Session()
    if api_key:
        session.headers["Ocp-Apim-Subscription-Key"] = api_key
    return session


def api_url(api_key: str | None) -> str:
    return AUTH_URL if api_key else PUBLIC_URL


def fetch_comtrade(
    session: requests.Session,
    url: str,
    hs_code: str,
    period: str,
) -> list[dict] | None:
    """
    Fetch one (HS code, period) page from Comtrade.
    Returns list of raw API rows, or None on failure.
    period format: 'YYYYMM' (single month).
    """
    params = {
        "reporterCode": str(REPORTER_CODE),
        "period":       period,
        "flowCode":     FLOW_CODE,
        "cmdCode":      hs_code,
        "includeDesc":  "true",
    }
    try:
        resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 401:
            log.error("API authentication failed — check COMTRADE_API_KEY")
            return None
        if resp.status_code == 429:
            log.warning("Rate limited (429) — backing off 60s")
            time.sleep(60)
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("  Request failed (HS=%s, period=%s): %s", hs_code, period, e)
        return None

    try:
        body = resp.json()
    except ValueError as e:
        log.warning("  JSON parse error: %s", e)
        return None

    count = body.get("count", 0)
    rows  = body.get("data", [])

    if count == 500:
        log.warning(
            "  [HS %s %s] Response capped at 500 rows — some partners may be missing. "
            "Register a free API key at comtradeapi.un.org for full coverage.",
            hs_code, period,
        )

    return rows


# ---------------------------------------------------------------------------
# Data processing
# ---------------------------------------------------------------------------

def aggregate_rows(raw_rows: list[dict]) -> list[dict]:
    """
    Filter and deduplicate raw Comtrade rows to one entry per partner.

    Comtrade stores data at multiple granularities (by mode of transport,
    customs procedure, 2nd partner, etc.).  The clean aggregate row for each
    (HS code, partnerCode) is identified by:
        motCode = 0   (all modes of transport combined)
        customsCode = 'C00'   (standard total)

    Within that filter there can still be two rows per partner due to
    partner2Code variations; we take the one with partner2Code == 0 first,
    falling back to the max primaryValue row.
    """
    # Filter to aggregate-mode rows only
    candidates = [
        r for r in raw_rows
        if r.get("motCode") == 0 and r.get("customsCode") == "C00"
    ]

    # Deduplicate: group by (cmdCode, partnerCode), prefer partner2Code==0
    from collections import defaultdict
    best: dict[tuple, dict] = {}
    for r in candidates:
        key = (r.get("cmdCode", ""), r.get("partnerCode", -1))
        existing = best.get(key)
        if existing is None:
            best[key] = r
        else:
            # Prefer partner2Code == 0 (no re-export component)
            if r.get("partner2Code") == 0 and existing.get("partner2Code") != 0:
                best[key] = r
            elif (r.get("partner2Code") == existing.get("partner2Code") and
                  (r.get("primaryValue") or 0) > (existing.get("primaryValue") or 0)):
                best[key] = r

    return list(best.values())


def row_to_db(raw: dict, period_date: date, scraped_at: datetime) -> dict | None:
    """
    Convert one clean Comtrade row to a trade_flows INSERT dict.
    Returns None if the row should be skipped.
    """
    cmd_code   = str(raw.get("cmdCode", "")).strip()
    partner_id = raw.get("partnerCode", -1)

    if not cmd_code:
        return None

    # Keep only our target HS codes
    if cmd_code not in HS_CODES:
        return None

    # Map numeric partner code → ISO alpha-2 (None = world aggregate)
    if partner_id not in M49_TO_ISO2:
        # Unknown partner — skip to avoid data quality issues
        return None
    partner_iso2 = M49_TO_ISO2[partner_id]   # may be None (world)

    value_usd  = raw.get("primaryValue") or raw.get("fobvalue")
    net_wgt    = raw.get("netWgt")

    return {
        "source":           SOURCE,
        "reporter_country": REPORTER_ISO2,
        "partner_country":  partner_iso2,
        "hs_code":          cmd_code,
        "hs_description":   HS_DESCRIPTIONS.get(cmd_code),
        "flow_direction":   FLOW_DIRECTION,
        "period":           period_date,
        "period_type":      "monthly",
        "value_usd":        float(value_usd) if value_usd is not None else None,
        "quantity_kg":      float(net_wgt) if net_wgt is not None else None,
        "scraped_at":       scraped_at,
    }


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

def find_latest_available_period(session: requests.Session, url: str) -> str | None:
    """
    Probe the API to find the most recent period with data for Turkey.
    Comtrade data typically lags 9–15 months behind the current date.
    Probes from 3 months ago back to 24 months ago.
    """
    today = date.today()
    for lag in range(3, 25):
        cursor = date(today.year, today.month, 1) - relativedelta(months=lag)
        period = cursor.strftime("%Y%m")
        try:
            resp = session.get(
                url,
                params={
                    "reporterCode": str(REPORTER_CODE),
                    "period":       period,
                    "flowCode":     FLOW_CODE,
                    "cmdCode":      HS_CODES[0],    # probe with first HS code
                },
                timeout=REQUEST_TIMEOUT,
            )
            data = resp.json().get("data", [])
            if data:
                log.info("Latest available Comtrade period: %s (lag ~%d months)", period, lag)
                return period
        except Exception:
            pass
        time.sleep(0.5)

    return None


def months_back(n: int, latest_period: str | None = None) -> list[str]:
    """
    Return list of period strings 'YYYYMM' for n months ending at latest_period
    (most recent first).  If latest_period is None, falls back to last complete month.
    """
    if latest_period:
        year, month = int(latest_period[:4]), int(latest_period[4:6])
        cursor = date(year, month, 1)
    else:
        today = date.today()
        cursor = date(today.year, today.month, 1) - relativedelta(months=1)

    periods = []
    for _ in range(n):
        periods.append(cursor.strftime("%Y%m"))
        cursor -= relativedelta(months=1)
    return periods   # newest first


def period_to_date(period_str: str) -> date:
    """'YYYYMM' → first day of that month as a date object."""
    return date(int(period_str[:4]), int(period_str[4:6]), 1)


# ---------------------------------------------------------------------------
# Main scrape loop
# ---------------------------------------------------------------------------

def scrape(months: int = 12, dry_run: bool = False) -> dict:
    """
    Fetch `months` months of Turkey export data for all HS codes.
    Returns {"inserted": int, "updated": int, "failed": int, "skipped": int}.
    """
    inserted = updated = failed = skipped = 0
    api_key  = os.environ.get("COMTRADE_API_KEY")
    url      = api_url(api_key)
    scraped_at = datetime.now(timezone.utc)

    if not api_key:
        log.warning(
            "COMTRADE_API_KEY not set — using public preview endpoint. "
            "Responses are capped at 500 rows; some trading partners may be missing. "
            "Register free at https://comtradeapi.un.org/ for complete coverage."
        )

    try:
        conn = get_connection()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return {"inserted": 0, "updated": 0, "failed": -1, "skipped": 0,
                "error": str(e)}

    ensure_hs_description_column(conn)
    session = build_session(api_key)

    # Probe for latest available period (Comtrade lags 9-15 months)
    latest = find_latest_available_period(session, url)
    if latest is None:
        log.warning("Could not detect latest Comtrade period — using 13-month lag fallback")
    periods = months_back(months, latest_period=latest)

    log.info(
        "Fetching %d months (%s \u2192 %s) for %d HS codes",
        len(periods), periods[-1], periods[0], len(HS_CODES),
    )

    # Iterate: outer = HS code, inner = period (so we can pause between codes)
    for hs_code in HS_CODES:
        # Refresh DB connection at start of each HS (prevent idle timeout in long backfills)
        try:
            conn.close()
        except Exception:
            pass
        conn = get_connection()
        log.info("  DB connection refreshed for HS %s", hs_code)

        for i, period in enumerate(periods):
            if i > 0:
                time.sleep(REQUEST_DELAY)

            log.info("Fetching HS %s  period=%s ...", hs_code, period)
            raw_rows = fetch_comtrade(session, url, hs_code, period)

            if raw_rows is None:
                failed += 1
                if not dry_run:
                    record_failure(
                        conn, url=url,
                        error_message="Comtrade API request failed",
                        error_detail=f"hs_code={hs_code} period={period}",
                        payload={"hs_code": hs_code, "period": period},
                    )
                continue

            clean = aggregate_rows(raw_rows)
            period_date = period_to_date(period)

            log.info(
                "  %d raw rows → %d clean aggregate rows",
                len(raw_rows), len(clean),
            )

            for raw in clean:
                db_row = row_to_db(raw, period_date, scraped_at)
                if db_row is None:
                    skipped += 1
                    continue

                if dry_run:
                    partner = db_row["partner_country"] or "WORLD"
                    log.info(
                        "  [DRY-RUN] HS=%s period=%s partner=%s val=$%s wgt=%s",
                        db_row["hs_code"], period, partner,
                        f"{db_row['value_usd']:,.0f}" if db_row["value_usd"] else "N/A",
                        f"{db_row['quantity_kg']:,.0f}" if db_row["quantity_kg"] else "N/A",
                    )
                    inserted += 1
                    continue

                try:
                    action = upsert_row(conn, db_row)
                    if action == "inserted":
                        inserted += 1
                    else:
                        updated += 1
                except psycopg2.Error as e:
                    failed += 1
                    log.warning(
                        "  DB error (HS=%s period=%s partner=%s): %s",
                        db_row["hs_code"], period,
                        db_row.get("partner_country", "?"), e,
                    )
                except Exception as e:
                    failed += 1
                    log.warning("  Unexpected error: %s", e)

        # Brief pause between HS codes
        time.sleep(REQUEST_DELAY)

    conn.close()
    return {"inserted": inserted, "updated": updated, "failed": failed,
            "skipped": skipped}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Turkey textile export data from UN Comtrade API "
            "and store in trade_flows table."
        )
    )
    parser.add_argument(
        "--months",
        type=int,
        default=12,
        metavar="N",
        help="Number of complete months to back-fill (default: 12)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse data, print rows, but do not write to DB",
    )
    args = parser.parse_args()

    if args.months < 1:
        parser.error("--months must be >= 1")

    log.info("Starting %s (months=%d%s)", PIPELINE, args.months,
             ", DRY-RUN" if args.dry_run else "")
    result = scrape(months=args.months, dry_run=args.dry_run)

    print(
        f"\nSummary — inserted: {result['inserted']}  "
        f"updated: {result['updated']}  "
        f"skipped: {result['skipped']}  "
        f"failed: {result['failed']}"
    )

    if result.get("error"):
        print(f"Fatal error: {result['error']}")
        sys.exit(1)

    if result["failed"] and result["failed"] > result["inserted"] + result["updated"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
