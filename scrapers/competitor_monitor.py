"""
scrapers/competitor_monitor.py
Fetches each competitor homepage, detects content changes via SHA-256 hash,
and writes market_signals when a change is found.

Logic per company:
  - No previous snapshot → store snapshot, no signal (baseline)
  - Hash unchanged       → update checked_at, no signal
  - Hash changed         → store new snapshot + write market_signals row

Usage:
    python scrapers/competitor_monitor.py
    python scrapers/competitor_monitor.py --timeout 20
"""

import argparse
import hashlib
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
PIPELINE = "competitor_monitor"

# Keywords to extract from page text (Turkish + English)
KEYWORDS = re.compile(
    r"\b(new|launch|launched|launching|certificate|certificat\w+|export|exports|"
    r"yeni|ihracat|sertifika|sertifikas\w+|ihraç|lansman|duyur\w+)\b",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
}
BETWEEN_REQUESTS_DELAY = 2.0   # seconds between company fetches
MAX_SUMMARY_LENGTH = 1000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Page processing
# ---------------------------------------------------------------------------

def fetch_page(url: str, timeout: int) -> requests.Response | None:
    """Fetch a URL, return Response or None on error."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        log.warning("Fetch failed for %s: %s", url, e)
        return None


def extract_text(html: str) -> str:
    """
    Parse HTML and return normalised plain text: title + meta description +
    visible body text, with whitespace collapsed.
    """
    soup = BeautifulSoup(html, "html.parser")

    parts = []

    # Page title
    if soup.title and soup.title.string:
        parts.append(soup.title.string.strip())

    # Meta description
    meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if meta and meta.get("content"):
        parts.append(meta["content"].strip())

    # Body text (strip scripts/styles)
    for tag in soup(["script", "style", "noscript", "svg", "img"]):
        tag.decompose()
    body_text = soup.get_text(separator=" ")
    parts.append(body_text)

    combined = " ".join(parts)
    return re.sub(r"\s+", " ", combined).strip()


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_summary(text: str) -> str:
    """
    Return sentences/fragments that contain at least one monitored keyword.
    Capped at MAX_SUMMARY_LENGTH characters.
    """
    sentences = re.split(r"(?<=[.!?])\s+|(?<=\n)", text)
    hits = [s.strip() for s in sentences if KEYWORDS.search(s) and len(s.strip()) > 10]
    summary = " | ".join(hits)
    return summary[:MAX_SUMMARY_LENGTH] if summary else ""


def normalise_url(website: str) -> str:
    """Ensure website has an https:// scheme."""
    website = website.strip()
    if not website.startswith(("http://", "https://")):
        return "https://" + website
    return website


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(url, connect_timeout=10)


def get_companies(cur) -> list[dict]:
    cur.execute(
        """
        SELECT id, name, website
        FROM companies
        WHERE website IS NOT NULL
        ORDER BY name
        """
    )
    return cur.fetchall()


def get_latest_snapshot(cur, company_id: str) -> dict | None:
    cur.execute(
        """
        SELECT id, content_hash, checked_at
        FROM competitor_snapshots
        WHERE company_id = %s
        ORDER BY checked_at DESC
        LIMIT 1
        """,
        (company_id,),
    )
    return cur.fetchone()


def insert_snapshot(cur, company_id: str, url: str, content_hash: str, summary: str):
    cur.execute(
        """
        INSERT INTO competitor_snapshots
            (company_id, url, content_hash, content_summary, checked_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (company_id, url, content_hash, summary, datetime.now(timezone.utc)),
    )


def insert_market_signal(cur, company_id: str, company_name: str, url: str, summary: str):
    cur.execute(
        """
        INSERT INTO market_signals
            (signal_type, severity, title, body, source_table, company_id, detected_at, tags)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            "website_change",
            "info",
            f"Website content changed: {company_name}",
            (
                f"Homepage content hash changed for {company_name} ({url}).\n\n"
                f"Keyword matches:\n{summary}" if summary else
                f"Homepage content hash changed for {company_name} ({url})."
            ),
            "competitor_snapshots",
            company_id,
            datetime.now(timezone.utc),
            ["website_change", "competitor"],
        ),
    )


def record_failure(conn, url: str | None, error_message: str, error_detail: str, payload: dict):
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
                    "scrape",
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
# Main monitor loop
# ---------------------------------------------------------------------------

def monitor(request_timeout: int = 15) -> dict:
    """
    Check all companies with a website. Returns a summary dict.
    """
    baselines = changed = unchanged = failed = 0

    try:
        conn = get_connection()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return {"baselines": 0, "changed": 0, "unchanged": 0, "failed": -1, "error": str(e)}

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        companies = get_companies(cur)

    log.info("Checking %d companies", len(companies))

    for idx, company in enumerate(companies, start=1):
        company_id = str(company["id"])
        name = company["name"]
        url = normalise_url(company["website"])

        log.info("[%d/%d] %s — %s", idx, len(companies), name, url)

        # --- Fetch page ---
        resp = fetch_page(url, request_timeout)
        if resp is None:
            failed += 1
            record_failure(
                conn,
                url=url,
                error_message=f"Failed to fetch homepage for {name}",
                error_detail=f"company_id={company_id}",
                payload={"company_id": company_id, "name": name, "url": url},
            )
            continue

        # --- Process content ---
        try:
            text = extract_text(resp.text)
            content_hash = compute_hash(text)
            summary = extract_summary(text)
        except Exception as e:
            failed += 1
            log.warning("Content processing failed for %s: %s", name, e)
            record_failure(
                conn,
                url=url,
                error_message=f"Content processing error: {e}",
                error_detail=repr(e),
                payload={"company_id": company_id, "name": name, "url": url},
            )
            continue

        # --- Compare with last snapshot and write to DB ---
        try:
            with conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    previous = get_latest_snapshot(cur, company_id)

                    if previous is None:
                        # First check — store baseline, no signal
                        insert_snapshot(cur, company_id, url, content_hash, summary)
                        baselines += 1
                        log.info("  BASELINE stored")

                    elif previous["content_hash"] == content_hash:
                        # No change — update timestamp only
                        cur.execute(
                            """
                            UPDATE competitor_snapshots
                            SET checked_at = %s
                            WHERE id = %s
                            """,
                            (datetime.now(timezone.utc), previous["id"]),
                        )
                        unchanged += 1
                        log.info("  UNCHANGED")

                    else:
                        # Content changed — new snapshot + market signal
                        insert_snapshot(cur, company_id, url, content_hash, summary)
                        insert_market_signal(cur, company_id, name, url, summary)
                        changed += 1
                        log.info("  CHANGED — signal written")
                        if summary:
                            log.info("  Keywords: %s", summary[:200])

        except psycopg2.Error as e:
            failed += 1
            log.warning("  DB error for %s: %s", name, e)
            record_failure(
                conn,
                url=url,
                error_message=str(e),
                error_detail=repr(e),
                payload={"company_id": company_id, "name": name, "url": url},
            )
        except Exception as e:
            failed += 1
            log.warning("  Unexpected error for %s: %s", name, e)
            record_failure(
                conn,
                url=url,
                error_message=str(e),
                error_detail=repr(e),
                payload={"company_id": company_id, "name": name, "url": url},
            )

        if idx < len(companies):
            time.sleep(BETWEEN_REQUESTS_DELAY)

    conn.close()
    return {"baselines": baselines, "changed": changed, "unchanged": unchanged, "failed": failed}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Monitor competitor homepages for changes")
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        metavar="SEC",
        help="HTTP request timeout in seconds (default: 15)",
    )
    args = parser.parse_args()

    log.info("Starting %s", PIPELINE)
    result = monitor(request_timeout=args.timeout)

    print(
        f"\nSummary — baselines: {result['baselines']}  "
        f"changed: {result['changed']}  "
        f"unchanged: {result['unchanged']}  "
        f"failed: {result['failed']}"
    )

    if result.get("error"):
        print(f"Fatal error: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
