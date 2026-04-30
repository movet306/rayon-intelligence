"""
backup_db.py — Snapshot every public table in the Rayon Intelligence DB to CSV.

Part of the PI-0 data safety discipline: take a versioned dump before any
schema-touching refactor, so accumulated historical price data is recoverable.

Usage:
    # default: ./backups/YYYY-MM-DD/
    python backup_db.py

    # custom output dir
    python backup_db.py --out C:\my-backups

    # via environment variable
    $env:BACKUP_DIR = "D:\rayon-snapshots"
    python backup_db.py

DATABASE_URL is read from environment (or .env via python-dotenv if present).
A single failed table does not abort the run; failures are reported at the end.
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--out",
        default=None,
        help="Output directory. Default: ./backups/YYYY-MM-DD or $BACKUP_DIR",
    )
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("[X] DATABASE_URL not set in environment or .env")
        sys.exit(1)

    today = date.today().isoformat()
    if args.out:
        out_dir = Path(args.out)
    elif os.environ.get("BACKUP_DIR"):
        out_dir = Path(os.environ["BACKUP_DIR"]) / today
    else:
        out_dir = Path(__file__).resolve().parent / "backups" / today

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output: {out_dir}")

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_type='BASE TABLE'
                ORDER BY table_name
            """)
            tables = [r[0] for r in cur.fetchall()]

        print(f"Dumping {len(tables)} tables...")
        total_bytes = 0
        failed = []

        for t in tables:
            out = out_dir / f"{t}.csv"
            try:
                with conn.cursor() as cur, \
                     open(out, "w", encoding="utf-8", newline="") as f:
                    cur.copy_expert(
                        f'COPY "{t}" TO STDOUT WITH CSV HEADER',
                        f,
                    )
                sz = out.stat().st_size
                total_bytes += sz
                print(f"  OK  {t:40} {sz:>12,} bytes")
            except Exception as e:
                failed.append((t, str(e)))
                print(f"  FAIL {t:40} {e}")
                # Rollback the failed transaction so subsequent tables work
                conn.rollback()
    finally:
        conn.close()

    print(f"\nTotal: {total_bytes:,} bytes ({total_bytes / 1024 / 1024:.2f} MB)")
    print(f"Saved to: {out_dir}")
    if failed:
        print(f"\n[!] {len(failed)} table(s) failed:")
        for t, err in failed:
            print(f"     {t}: {err}")
        sys.exit(2)


if __name__ == "__main__":
    main()
