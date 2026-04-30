"""
inspect_price_columns.py - Show column structure of price/dim tables.

Used to determine the correct date and dedup keys before writing PI-1.1
deduplication logic.
"""
import os
import sys
import psycopg2

try:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("[X] DATABASE_URL env var not set.")
    sys.exit(1)

TABLES = [
    "price_signals",
    "price_intelligence_signals",
    "price_metrics_daily",
    "price_chain_spreads",
    "fact_yarn_price_pressure",
    "dim_material",
    "dim_price_source",
]

with psycopg2.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        for tbl in TABLES:
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s
                ORDER BY ordinal_position
                """,
                (tbl,),
            )
            cols = cur.fetchall()
            print(f"\n{'='*75}")
            print(f"TABLE: {tbl}  ({len(cols)} columns)")
            print(f"{'='*75}")
            if not cols:
                print("  (no columns / table missing)")
                continue
            for name, dtype, nullable, default in cols:
                null_str = "NULL" if nullable == "YES" else "NOT NULL"
                default_str = f"DEFAULT {default}" if default else ""
                print(f"  {name:30} {dtype:25} {null_str:10} {default_str}")

            # Show 2 sample rows for protected tables to understand content
            if tbl in (
                "price_signals",
                "price_intelligence_signals",
                "price_metrics_daily",
                "price_chain_spreads",
            ):
                cur.execute(f"SELECT * FROM {tbl} ORDER BY 1 DESC LIMIT 2")
                rows = cur.fetchall()
                col_names = [c[0] for c in cols]
                print(f"\n  Sample (2 most recent rows):")
                for row in rows:
                    print("  ---")
                    for cname, val in zip(col_names, row):
                        # Truncate long values
                        sval = str(val)
                        if len(sval) > 60:
                            sval = sval[:57] + "..."
                        print(f"    {cname:30} = {sval}")
