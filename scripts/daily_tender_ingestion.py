"""
scripts/daily_tender_ingestion.py

Phase F1 daily orchestrator: download EKAP MAL bulletin, parse + score,
log to bulletin_ingestion_log.

Called from:
- GitHub Actions cron (11:00 UTC = 14:00 IST daily)
- Manual: python -m scripts.daily_tender_ingestion
- Backfill: python -m scripts.daily_tender_ingestion --date 2026-05-12
"""
import argparse
import hashlib
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path

import psycopg2

from scrapers.tender_ingestion.ekap_downloader import download_bulletins
from scrapers.tender_ingestion.tender_bulletin_scraper import process_zip

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def sha256sum(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def log_to_db(cur, bulletin_date, procurement_type, status, **kwargs):
    cur.execute(
        """
        INSERT INTO bulletin_ingestion_log (
            source, bulletin_date, procurement_type, status,
            file_path, file_size_bytes, file_sha256,
            error_message, tender_count, completed_at, duration_seconds
        )
        VALUES ('ekap', %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        ON CONFLICT (source, bulletin_date, procurement_type) DO UPDATE SET
            status            = EXCLUDED.status,
            file_path         = EXCLUDED.file_path,
            file_size_bytes   = EXCLUDED.file_size_bytes,
            file_sha256       = EXCLUDED.file_sha256,
            error_message     = EXCLUDED.error_message,
            tender_count      = EXCLUDED.tender_count,
            completed_at      = NOW(),
            duration_seconds  = EXCLUDED.duration_seconds
        """,
        (
            bulletin_date,
            procurement_type,
            status,
            str(kwargs.get("file_path")) if kwargs.get("file_path") else None,
            kwargs.get("file_size_bytes"),
            kwargs.get("file_sha256"),
            kwargs.get("error_message"),
            kwargs.get("tender_count"),
            kwargs.get("duration_seconds"),
        ),
    )


def run(target_date, types, db_url):
    logger.info(f"=== Daily tender ingestion: date={target_date} types={types} ===")
    t_overall = time.time()

    # Stage 1: Download
    logger.info("[1/3] Acquisition layer (Playwright)")
    results = download_bulletins(target_date=target_date, types=types)

    # Stage 2: Parse + log
    logger.info("[2/3] Parse + DB ingest + log")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    pipeline_stats = {}
    for ptype in types:
        zip_path = results.get(ptype)
        t_start = time.time()

        if zip_path is None or not zip_path.exists():
            logger.error(f"  {ptype}: download failed (no bulletin?)")
            log_to_db(cur, target_date, ptype, "failed_download",
                      error_message="Downloader returned no zip")
            conn.commit()
            pipeline_stats[ptype] = {"status": "failed_download"}
            continue

        try:
            size = zip_path.stat().st_size
            sha = sha256sum(zip_path)
            log_to_db(cur, target_date, ptype, "downloaded",
                      file_path=zip_path, file_size_bytes=size, file_sha256=sha)
            conn.commit()

            stats = process_zip(zip_path, db_url)
            duration = time.time() - t_start

            log_to_db(cur, target_date, ptype, "parsed",
                      file_path=zip_path, file_size_bytes=size, file_sha256=sha,
                      tender_count=stats.get("total"),
                      duration_seconds=duration)
            conn.commit()
            logger.info(
                f"  {ptype}: OK total={stats['total']} "
                f"HIGH={stats.get('HIGH', 0)} MEDIUM={stats.get('MEDIUM', 0)} "
                f"REJECTED={stats.get('REJECTED', 0)} "
                f"duration={duration:.1f}s"
            )
            pipeline_stats[ptype] = {"status": "parsed", **stats}
        except Exception as e:
            duration = time.time() - t_start
            err = f"{type(e).__name__}: {e}"
            log_to_db(cur, target_date, ptype, "failed_parse",
                      file_path=zip_path, error_message=err[:1000],
                      duration_seconds=duration)
            conn.commit()
            logger.error(f"  {ptype}: PARSE FAILED {err}")
            pipeline_stats[ptype] = {"status": "failed_parse", "error": err}

    # Stage 3: Summary
    logger.info("[3/3] Summary")
    cur.execute(
        """
        SELECT procurement_type, status, tender_count, file_size_bytes, duration_seconds
        FROM bulletin_ingestion_log
        WHERE bulletin_date = %s AND source = 'ekap'
        ORDER BY procurement_type
        """,
        (target_date,),
    )
    for r in cur.fetchall():
        size_kb = (r[3] or 0) // 1024
        logger.info(
            f"  {r[0]:5s} {r[1]:18s} "
            f"tenders={r[2] if r[2] is not None else '?':>4} "
            f"size={size_kb:>6}KB "
            f"dur={(r[4] or 0):>5.1f}s"
        )

    cur.close()
    conn.close()

    logger.info(f"=== Done in {time.time() - t_overall:.1f}s ===")
    return pipeline_stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Bulletin date YYYY-MM-DD (default: today)")
    parser.add_argument("--types", help="Comma-separated types (default: MAL)")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else date.today()
    types = (
        [t.strip().upper() for t in args.types.split(",")]
        if args.types
        else ["MAL"]
    )

    db_url = os.environ.get("DATABASE_URL") or os.environ.get("RAYON_DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL or RAYON_DATABASE_URL not set")

    run(target_date, types, db_url)


if __name__ == "__main__":
    main()
