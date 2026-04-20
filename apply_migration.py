"""
apply_migration.py
Reads a SQL file and executes it against DATABASE_URL.

Usage:
    python apply_migration.py schema/006_market_signals_v2.sql
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def apply(sql_path: str):
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL environment variable is not set", file=sys.stderr)
        sys.exit(1)

    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    print(f"Applying {sql_path} …")
    conn = psycopg2.connect(url, connect_timeout=10)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        print("Migration applied successfully.")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        conn.close()
        sys.exit(1)
    conn.close()


def verify(table: str, columns: list[str]):
    """Print which expected columns exist in the given table."""
    url = os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(url, connect_timeout=10)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM   information_schema.columns
            WHERE  table_name = %s
            ORDER  BY ordinal_position
            """,
            (table,),
        )
        actual = {row[0] for row in cur.fetchall()}
    conn.close()

    missing = [c for c in columns if c not in actual]
    present = [c for c in columns if c in actual]
    print(f"\nVerification — {table}:")
    print(f"  Present : {present}")
    if missing:
        print(f"  MISSING : {missing}")
    else:
        print("  All expected columns present.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <path/to/migration.sql>")
        sys.exit(1)

    apply(sys.argv[1])

    # Post-migration verification
    verify("market_signals", [
        "impact_score", "time_horizon", "action_tag",
        "signal_category", "material_form", "theme",
        "affected_products", "rayon_relevance",
    ])
    verify("dim_material", [
        "rayon_relevance_score", "material_form", "applications",
    ])
