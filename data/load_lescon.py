"""
data/load_lescon.py

Load lescon_orme_structured.csv and lescon_dokuma_structured.csv into the
lescon_sales PostgreSQL table.

Usage:
    python data/load_lescon.py
    python data/load_lescon.py --truncate   # drop existing rows first
    python data/load_lescon.py --dry-run    # print counts only, no DB writes

Reads DATABASE_URL from the .env file in the project root.
"""

import argparse
import csv
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent

SOURCES = [
    {"csv": DATA_DIR / "lescon_orme_structured.csv",    "miktar_unit": "KG"},
    {"csv": DATA_DIR / "lescon_dokuma_structured.csv",  "miktar_unit": "MT"},
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS lescon_sales (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    evrak_no        TEXT        NOT NULL,
    tarih           DATE,
    urun_aciklamasi TEXT,
    unit_price_usd  NUMERIC(10,2),
    miktar          NUMERIC(12,3),
    miktar_unit     TEXT,
    fabric_type     TEXT,
    fabric_subtype  TEXT,
    is_return       BOOLEAN     DEFAULT FALSE,
    source_file     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS lescon_sales_tarih_idx  ON lescon_sales (tarih);
CREATE INDEX IF NOT EXISTS lescon_sales_fabric_idx ON lescon_sales (fabric_type);
"""

INSERT_SQL = """
INSERT INTO lescon_sales
    (evrak_no, tarih, urun_aciklamasi, unit_price_usd,
     miktar, miktar_unit, fabric_type, fabric_subtype,
     is_return, source_file)
VALUES
    (%(evrak_no)s, %(tarih)s, %(urun_aciklamasi)s, %(unit_price_usd)s,
     %(miktar)s, %(miktar_unit)s, %(fabric_type)s, %(fabric_subtype)s,
     %(is_return)s, %(source_file)s)
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_env():
    """Load .env from project root (two levels up from data/)."""
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)


def get_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(url, connect_timeout=15)


def read_csv(csv_path: Path, miktar_unit: str) -> list[dict]:
    """
    Read one structured CSV and return a list of row dicts ready for INSERT.
    CSV columns: evrak_no, tarih, urun_aciklamasi, unit_price_usd, miktar_mt,
                 fabric_type, source_file
    """
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            miktar_str = raw.get("miktar_mt", "").strip()
            try:
                miktar = float(miktar_str) if miktar_str else None
            except ValueError:
                miktar = None

            price_str = raw.get("unit_price_usd", "").strip()
            try:
                unit_price = float(price_str) if price_str else None
            except ValueError:
                unit_price = None

            tarih_str = raw.get("tarih", "").strip()
            tarih = tarih_str if tarih_str else None

            rows.append({
                "evrak_no":        raw.get("evrak_no", "").strip(),
                "tarih":           tarih,
                "urun_aciklamasi": raw.get("urun_aciklamasi", "").strip() or None,
                "unit_price_usd":  unit_price,
                "miktar":          miktar,
                "miktar_unit":     miktar_unit,
                "fabric_type":     raw.get("fabric_type", "").strip() or None,
                "fabric_subtype":  None,   # not present in structured CSV
                "is_return":       (miktar is not None and miktar < 0),
                "source_file":     raw.get("source_file", "").strip() or None,
            })
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Load Lescon structured CSVs into PostgreSQL")
    parser.add_argument("--truncate", action="store_true",
                        help="Truncate lescon_sales before loading")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Read CSVs and print counts; do not write to DB")
    args = parser.parse_args()

    load_env()

    # Read all CSVs first
    all_rows: list[dict] = []
    for source in SOURCES:
        csv_path = source["csv"]
        if not csv_path.exists():
            print(f"ERROR: CSV not found — {csv_path}")
            sys.exit(1)
        rows = read_csv(csv_path, source["miktar_unit"])
        print(f"  {csv_path.name}: {len(rows)} rows  "
              f"({sum(1 for r in rows if r['is_return'])} returns)")
        all_rows.extend(rows)

    print(f"\nTotal rows to insert: {len(all_rows)}")

    if args.dry_run:
        print("[DRY-RUN] No database writes performed.")
        return

    # Connect and write
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Ensure table + indexes exist
            cur.execute(CREATE_TABLE_SQL)

            if args.truncate:
                cur.execute("TRUNCATE lescon_sales")
                print("Truncated lescon_sales.")

            # Batch insert
            for row in all_rows:
                cur.execute(INSERT_SQL, row)

        conn.commit()
        print(f"Inserted {len(all_rows)} rows into lescon_sales.")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()

    # Summary
    conn2 = get_connection()
    try:
        with conn2.cursor() as cur:
            cur.execute("SELECT COUNT(*), MIN(tarih), MAX(tarih) FROM lescon_sales")
            total, min_d, max_d = cur.fetchone()
            cur.execute(
                "SELECT fabric_type, COUNT(*) FROM lescon_sales GROUP BY fabric_type ORDER BY 2 DESC"
            )
            by_fabric = cur.fetchall()
    finally:
        conn2.close()

    print(f"\nlescon_sales summary:")
    print(f"  Total rows : {total}")
    print(f"  Date range : {min_d} to {max_d}")
    print(f"  By fabric_type:")
    for fabric, cnt in by_fabric:
        print(f"    {(fabric or 'NULL'):<20}: {cnt}")


if __name__ == "__main__":
    main()
