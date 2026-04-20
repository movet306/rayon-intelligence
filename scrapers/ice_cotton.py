"""
scrapers/ice_cotton.py — ICE Cotton No.2 front-month futures via Nasdaq Data Link.

Dataset  : CHRIS/ICE_CT1  (continuous contract, Settle price = column index 4)
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
from datetime import date, timezone, datetime

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

PIPELINE = "ice_cotton"
DATASET  = "CHRIS/ICE_CT1"   # Cotton No.2 continuous contract
ROWS     = 90                 # fetch last 90 trading days

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
    api_key = os.environ.get("NASDAQ_API_KEY")
    if not api_key:
        raise RuntimeError("NASDAQ_API_KEY not set — add it to .env (free key from data.nasdaq.com)")

    url = f"https://data.nasdaq.com/api/v3/datasets/{DATASET}.json"
    params = {
        "api_key":      api_key,
        "rows":         ROWS,
        "column_index": 4,     # column 4 = Settle price in USc/lb
    }

    log.info("Fetching %s (last %d rows)…", DATASET, ROWS)
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()

    dataset = resp.json()["dataset"]
    raw_rows = dataset["data"]   # [[date_str, settle_usc], ...]
    log.info("Received %d rows from Nasdaq Data Link", len(raw_rows))

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur  = conn.cursor()

    inserted = skipped = 0
    for row in raw_rows:
        obs_date   = date.fromisoformat(row[0])
        settle_usc = float(row[1])

        # Store raw USc/lb in price_usd (unit='USc/lb' marks this source's native unit).
        # build_price_metrics.py converts to USD/ton using the unit field.
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
                settle_usc,      # USc/lb — converted at metrics build time
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

    # Human-readable summary
    latest_row     = raw_rows[0]
    latest_date    = latest_row[0]
    latest_usc     = float(latest_row[1])
    latest_usd_ton = usc_lb_to_usd_ton(latest_usc)

    print(f"\nICE Cotton No.2 (CHRIS/ICE_CT1)")
    print(f"  Inserted : {inserted} new rows")
    print(f"  Skipped  : {skipped} already present")
    print(f"  Latest   : {latest_date}  "
          f"{latest_usc:.2f} USc/lb  =  ${latest_usd_ton:,.0f} USD/ton")

    return {"inserted": inserted, "skipped": skipped,
            "latest_date": latest_date, "latest_usc": latest_usc,
            "latest_usd_ton": latest_usd_ton}


if __name__ == "__main__":
    fetch_and_store()
