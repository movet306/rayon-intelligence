"""
scrapers/tender_ingestion/ekap_downloader.py

Phase F1 Step 9b: Production EKAP bulletin downloader.

PURE ACQUISITION LAYER. Downloads ZIPs from EKAP via Playwright. Does NOT
parse PDFs or write to DB. Returns Path objects; downstream modules handle
parsing and DB writes.

Architecture (per ChatGPT critique synthesis):
  - Acquisition only -- no parsing
  - Tek browser, tek context, sequential downloads for 4 procurement types
  - Persistent state (cookies/session) with weekly refresh policy
  - Idempotent (skips if ZIP already exists and is valid)
  - Retry with exponential backoff (3 attempts, 3s/6s/12s delays)
  - File verification (size >= 100KB sanity threshold)
  - Headless by default; EKAP_DOWNLOAD_HEADFUL=1 to debug visually

ZIP naming standard:
  EKAP_YYYY-MM-DD_TYPE.zip  (ISO date, e.g. EKAP_2026-05-12_MAL.zip)

Usage as CLI:
    python -m scrapers.tender_ingestion.ekap_downloader
    python -m scrapers.tender_ingestion.ekap_downloader --date 2026-05-12 --types MAL,HIZMET
    python -m scrapers.tender_ingestion.ekap_downloader --headful  # debug

Usage as library:
    from scrapers.tender_ingestion.ekap_downloader import download_bulletins
    results = download_bulletins(target_date=date(2026, 5, 12), types=['MAL'])
    # results: {'MAL': Path('data/tender_bulletins/EKAP_2026-05-12_MAL.zip')}
    # On failure: {'MAL': None}
"""
import argparse
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

URL = "https://ekap.kik.gov.tr/ekap/ilan/bultenindirme.aspx"
BULLETIN_DIR = Path("data/tender_bulletins")
STATE_FILE = Path("data/ekap_state.json")

# EKAP dropdown value mapping
TYPE_MAP = {
    "MAL":         "1",
    "YAPIM":       "2",
    "HIZMET":      "3",
    "DANISMANLIK": "4",
}

# Sanity threshold: real bulletin ZIPs are MB-sized.
# Anything under 100KB is almost certainly an error page misdelivered as ZIP.
MIN_ZIP_SIZE_BYTES = 100_000

# State refresh: discard persisted cookies/session weekly to avoid stale state.
STATE_REFRESH_DAYS = 7

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)

# Button selector (Bülten İndir, exact Turkish text). Kept here as constant so
# if EKAP changes the label we know exactly which selector needs updating.
BUTTON_SELECTOR = "text=B\u00fclten \u0130ndir"


def standardized_filename(date_iso: str, type_str: str) -> str:
    """EKAP_2026-05-12_MAL.zip (ISO date for sortable filenames)."""
    return f"EKAP_{date_iso}_{type_str.upper()}.zip"


def with_retry(fn, max_attempts: int = 3, base_delay: float = 3.0, what: str = ""):
    """Run fn() with exponential backoff. Re-raises the last exception on final failure."""
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"  [{what}] attempt {attempt}/{max_attempts} failed: "
                    f"{type(e).__name__}: {e}. Retry in {delay:.0f}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"  [{what}] all {max_attempts} attempts failed")
    raise last_exc


def state_age_days() -> Optional[int]:
    """Days since storage state file was last updated. None if no state file."""
    if not STATE_FILE.exists():
        return None
    mtime = STATE_FILE.stat().st_mtime
    age_seconds = time.time() - mtime
    return int(age_seconds // 86400)


def should_refresh_state() -> bool:
    """Weekly refresh policy."""
    age = state_age_days()
    return age is None or age >= STATE_REFRESH_DAYS


def _download_one_attempt(context, date_tr: str, type_str: str, target_path: Path) -> Path:
    """Single attempt to download one ZIP. Raises on any failure."""
    page = context.new_page()
    try:
        logger.info(f"  Loading bultenindirme.aspx...")
        page.goto(URL, wait_until="networkidle", timeout=30000)

        logger.info(f"  Selecting type {type_str} (value={TYPE_MAP[type_str]})")
        page.select_option('select[name$="ddlstBxIhaleTur"]', value=TYPE_MAP[type_str])
        page.wait_for_load_state("networkidle", timeout=15000)

        logger.info(f"  Filling date {date_tr} (via JS to avoid jQuery datepicker popup)")
        # jQuery datepicker on EKAP date input intercepts pointer events when opened
        # by page.fill() in headless mode. Set value via JS + dispatch change event,
        # then explicitly hide the datepicker overlay before clicking the download button.
        page.evaluate("""(value) => {
            const inp = document.querySelector('input[name$="etBultenTarihi"]');
            inp.focus();
            inp.value = value;
            inp.dispatchEvent(new Event('input', {bubbles: true}));
            inp.dispatchEvent(new Event('change', {bubbles: true}));
            inp.blur();
        }""", date_tr)
        page.evaluate("""() => {
            const dp = document.getElementById('ui-datepicker-div');
            if (dp) { dp.style.display = 'none'; dp.style.visibility = 'hidden'; }
        }""")
        page.wait_for_load_state("networkidle", timeout=15000)

        logger.info(f"  Locating B\u00fclten \u0130ndir button")
        button = page.query_selector(BUTTON_SELECTOR)
        if not button:
            # Take a screenshot for debugging if button missing
            screenshot_path = BULLETIN_DIR / f"DEBUG_button_missing_{type_str}_{int(time.time())}.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)
            raise RuntimeError(
                f"'B\u00fclten \u0130ndir' button not found. "
                f"Screenshot: {screenshot_path}"
            )

        logger.info(f"  Clicking and awaiting download")
        with page.expect_download(timeout=60000) as dl_info:
            # force=True bypasses Playwright's actionability check
            # (which would otherwise wait for any overlay to disappear)
            button.click(force=True)
        download = dl_info.value

        target_path.parent.mkdir(parents=True, exist_ok=True)
        download.save_as(str(target_path))

        # Verify size
        size = target_path.stat().st_size
        if size < MIN_ZIP_SIZE_BYTES:
            try:
                target_path.unlink()
            except OSError:
                pass
            raise RuntimeError(
                f"Downloaded file too small ({size:,} bytes < {MIN_ZIP_SIZE_BYTES:,}), "
                f"likely an error page or empty response"
            )

        logger.info(f"  OK: saved {target_path.name} ({size:,} bytes)")
        return target_path
    finally:
        page.close()


def download_one_type(context, date_tr: str, type_str: str, target_path: Path) -> Path:
    """Download one ZIP with idempotency check + retry."""
    if target_path.exists() and target_path.stat().st_size >= MIN_ZIP_SIZE_BYTES:
        logger.info(
            f"  Already have {target_path.name} "
            f"({target_path.stat().st_size:,} bytes), skipping download"
        )
        return target_path

    return with_retry(
        lambda: _download_one_attempt(context, date_tr, type_str, target_path),
        max_attempts=3,
        base_delay=3.0,
        what=type_str,
    )


def download_bulletins(
    target_date: Optional[date] = None,
    types: Optional[list] = None,
    headless: Optional[bool] = None,
) -> dict:
    """Download EKAP bulletins for given date and types.

    Args:
        target_date: bulletin publication date. Defaults to today (Istanbul).
        types: list of procurement type strings (uppercase). Defaults to all 4.
        headless: True for invisible Chrome (production). False to watch (debug).
                  If None, reads EKAP_DOWNLOAD_HEADFUL env var.

    Returns:
        dict {type_str: Path or None}. None indicates failure for that type.
    """
    # Lazy import: only require playwright when actually downloading.
    from playwright.sync_api import sync_playwright

    target_date = target_date or date.today()
    date_iso = target_date.strftime("%Y-%m-%d")
    date_tr = target_date.strftime("%d.%m.%Y")
    types = types or list(TYPE_MAP.keys())

    if headless is None:
        headless = os.environ.get("EKAP_DOWNLOAD_HEADFUL") != "1"

    logger.info(
        f"=== EKAP downloader: date={date_iso} ({date_tr}), "
        f"types={types}, headless={headless} ==="
    )

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)

        # Persistent state with weekly refresh
        state_kwargs = {}
        if STATE_FILE.exists() and not should_refresh_state():
            logger.info(
                f"  Reusing persisted state from {STATE_FILE} "
                f"(age: {state_age_days()} days)"
            )
            state_kwargs["storage_state"] = str(STATE_FILE)
        elif STATE_FILE.exists():
            logger.info(f"  State age >= {STATE_REFRESH_DAYS} days, refreshing")
        else:
            logger.info(f"  No prior state; fresh context")

        context = browser.new_context(
            locale="tr-TR",
            timezone_id="Europe/Istanbul",
            user_agent=USER_AGENT,
            accept_downloads=True,
            **state_kwargs,
        )

        for type_str in types:
            if type_str not in TYPE_MAP:
                logger.warning(f"Unknown procurement type: {type_str}, skipping")
                results[type_str] = None
                continue

            target_path = BULLETIN_DIR / standardized_filename(date_iso, type_str)
            logger.info(f"--- {type_str} ---")
            try:
                path = download_one_type(context, date_tr, type_str, target_path)
                results[type_str] = path
            except Exception as e:
                logger.error(f"  FAILED: {type(e).__name__}: {e}")
                results[type_str] = None

        # Persist state for next run (preserves cookies/session)
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(STATE_FILE))
            logger.info(f"  Persisted state to {STATE_FILE}")
        except Exception as e:
            logger.warning(f"  Could not persist state: {e}")

        browser.close()

    success = sum(1 for v in results.values() if v is not None)
    logger.info(f"=== Completed: {success}/{len(types)} successful ===")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        help="Bulletin date in YYYY-MM-DD format. Defaults to today (Istanbul).",
    )
    parser.add_argument(
        "--types",
        help="Comma-separated procurement types (case-insensitive). "
             "Choices: MAL,HIZMET,YAPIM,DANISMANLIK. Defaults to all 4.",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Show browser window (debug). Default headless.",
    )
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else date.today()
    types = [t.strip().upper() for t in args.types.split(",")] if args.types else None
    headless = not args.headful

    results = download_bulletins(target_date=target_date, types=types, headless=headless)

    print("\n=== Results ===")
    for k, v in results.items():
        if v:
            print(f"  {k:12s}: {v.name} ({v.stat().st_size:,} bytes)")
        else:
            print(f"  {k:12s}: FAILED")

    n_failed = sum(1 for v in results.values() if v is None)
    sys.exit(n_failed)


if __name__ == "__main__":
    main()
