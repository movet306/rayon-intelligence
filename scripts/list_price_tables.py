"""
list_price_tables.py - Inventory Price Intelligence database tables.

Lists all price/fact/dim tables with row counts, column counts, and most recent
data timestamp where applicable. Output is used to write the PI-0 Data Safety Map.

Reads DATABASE_URL from env (Railway connection string).
"""
import os
import sys
import psycopg2

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("[X] DATABASE_URL env var not set.")
    print("    In PowerShell: $env:DATABASE_URL = '<railway_postgres_url>'")
    sys.exit(1)

QUERY = """
SELECT
    t.table_name,
    COALESCE((SELECT n_live_tup FROM pg_stat_user_tables
              WHERE schemaname='public' AND relname=t.table_name), 0) AS rows,
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema='public' AND table_name=t.table_name) AS cols,
    t.table_type
FROM information_schema.tables t
WHERE t.table_schema='public'
  AND (
       t.table_name LIKE 'price_%%'
    OR t.table_name LIKE 'fact_%%'
    OR t.table_name LIKE 'dim_%%'
    OR t.table_name LIKE 'lkp_%%'
    OR t.table_name LIKE 'v_%%'
    OR t.table_name LIKE 'mv_%%'
  )
ORDER BY
  CASE
    WHEN t.table_name LIKE 'price_%%' THEN 1
    WHEN t.table_name LIKE 'fact_%%' THEN 2
    WHEN t.table_name LIKE 'dim_%%' THEN 3
    WHEN t.table_name LIKE 'lkp_%%' THEN 4
    WHEN t.table_name LIKE 'v_%%' THEN 5
    WHEN t.table_name LIKE 'mv_%%' THEN 6
    ELSE 7
  END,
  t.table_name;
"""

# Tables likely holding daily-accumulated time-series. We probe their max date.
TIME_SERIES_PROBES = {
    "price_metrics_daily":          "metric_date",
    "price_signals":                "signal_date",
    "price_intelligence_signals":   "signal_date",
    "price_chain_spreads":          "spread_date",
    "fact_yarn_price_pressure":     "pressure_date",
    "fact_supplier_quotes":         "quote_date",
}

def main():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(QUERY)
            rows = cur.fetchall()

            print(f"{'TABLE':45} {'ROWS':>10} {'COLS':>5} {'TYPE':10}")
            print("-" * 75)
            for tbl, rowcount, colcount, ttype in rows:
                ttype_short = "VIEW" if "VIEW" in ttype else "TABLE"
                print(f"{tbl:45} {rowcount:>10,} {colcount:>5} {ttype_short:10}")

            print()
            print("=" * 75)
            print("TIME-SERIES PROBE (latest date per protected table)")
            print("=" * 75)
            for tbl, datecol in TIME_SERIES_PROBES.items():
                # Confirm table exists first
                cur.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name=%s",
                    (tbl,),
                )
                if not cur.fetchone():
                    print(f"{tbl:45} (table missing)")
                    continue
                # Confirm date column exists
                cur.execute(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=%s AND column_name=%s",
                    (tbl, datecol),
                )
                if not cur.fetchone():
                    print(f"{tbl:45} (no column {datecol})")
                    continue
                cur.execute(f"SELECT MIN({datecol}), MAX({datecol}), COUNT(DISTINCT {datecol}) FROM {tbl}")
                mn, mx, distinct = cur.fetchone()
                print(f"{tbl:45} min={mn} max={mx} distinct_days={distinct}")

if __name__ == "__main__":
    main()
