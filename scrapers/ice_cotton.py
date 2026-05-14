"""
scrapers/ice_cotton.py — ICE Cotton No.2 front-month futures via Yahoo Finance.

Symbol   : CT=F  (Cotton No. 2 continuous front-month on ICE, Yahoo Finance ticker)
Unit     : USc/lb  → stored as-is in price_signals; build_price_metrics converts to USD/ton.
Material : cotton_lint_futures  (distinct from sunsirs cotton_lint = China domestic spot)

IMPORTANT: ICE Cotton is a GLOBAL FUTURES benchmark.
           SunSirs cotton_lint is CHINA DOMESTIC SPOT in RMB/ton.
           These use DIFFERENT material slugs and must NOT be mixed in any chart or analysis.
           cotton_lint_futures — global futures (this scraper)
           cotton_lint         — China domestic spot (sunsirs)

Conversion reference:
    1 USc/lb  = USD 0.01 / lb
    1 lb      = 0.000453592 metric ton  → 1 metric ton = 2204.62 lb
    1 USc/lb  = 0.01 * 2204.62 = USD 22.0462 / metric ton

Usage:
    python scrapers/ice_cotton.py
"""

import logging
import os
from datetime import date, datetime, timezone

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

PIPELINE          = "ice_cotton"
YAHOO_SYMBOL      = "CT=F"         # ICE Cotton No.2 continuous front-month
YAHOO_RANGE       = "6mo"          # 6 months of daily history
YAHOO_INTERVAL    = "1d"

USc_LB_TO_USD_TON = 0.01 * 2204.62   # 22.0462 USD/ton per USc/lb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def usc_lb_to_usd_ton(usc_lb: float) -> float:
    """Convert USc/lb futures price to USD/metric ton."""
    return round(usc_lb * USc_LB_TO_USD_TON, 4)


def fetch_and_store() -> dict:
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{YAHOO_SYMBOL}"
        f"?interval={YAHOO_INTERVAL}&range={YAHOO_RANGE}"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    log.info("Fetching %s (%s %s) from Yahoo Finance...", YAHOO_SYMBOL, YAHOO_RANGE, YAHOO_INTERVAL)
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    chart   = resp.json()["chart"]["result"][0]
    timestamps = chart["timestamp"]
    closes     = chart["indicators"]["quote"][0]["close"]

    log.info("Received %d raw rows from Yahoo Finance", len(timestamps))

    # Build (date, price) pairs — skip None (non-trading days / partial sessions)
    rows = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        obs_date  = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        rows.append((obs_date, float(close)))

    log.info("Valid trading rows: %d", len(rows))

    conn = psycopg2.connect(os.environ["RAYON_DATABASE_URL"])
    cur  = conn.cursor()

    inserted = skipped = 0
    for obs_date, settle_usc in rows:
        cur.execute(
            """
            INSERT INTO price_signals
                (material, source, period, price_usd, unit, frequency, semantic_level)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (material, source, period) DO NOTHING
            """,
            (
                "cotton_lint_futures",  # distinct slug — global futures vs sunsirs china spot
                "ice_cotton",           # source — must stay separate in analysis
                obs_date,
                settle_usc,             # USc/lb — converted at metrics build time
                "USc/lb",
                "daily",
                "commodity",
            ),
        )
        if cur.rowcount > 0:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()

    # Human-readable summary — use most recent non-None row
    latest_date, latest_usc = rows[-1]
    latest_usd_ton = usc_lb_to_usd_ton(latest_usc)

    print(f"\nICE Cotton No.2 ({YAHOO_SYMBOL} via Yahoo Finance)")
    print(f"  Inserted : {inserted} new rows")
    print(f"  Skipped  : {skipped} already present")
    print(f"  Latest   : {latest_date}  "
          f"{latest_usc:.2f} USc/lb  =  ${latest_usd_ton:,.0f} USD/ton")

    return {
        "inserted":        inserted,
        "skipped":         skipped,
        "latest_date":     str(latest_date),
        "latest_usc":      latest_usc,
        "latest_usd_ton":  latest_usd_ton,
    }


if __name__ == "__main__":
    fetch_and_store()
