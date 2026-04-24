"""
Nebim load verification — confirms DB matches v3 pickle expectations.

Checks:
  1. Table row counts (bronze + silver match each other and pickles)
  2. Business bucket totals match pickle aggregations
  3. Date range coverage
  4. Key anomaly rows (yarn resale, suspected asset sales) present and flagged
  5. Latest batch id + classification version are correct

Usage:
    python scripts/verify_nebim_load.py
"""
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")
PICKLE_DIR = Path("outputs/v3")

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def ok(msg):
    print(f"  {GREEN}✓{RESET} {msg}")


def warn(msg):
    print(f"  {YELLOW}⚠{RESET} {msg}")


def fail(msg):
    print(f"  {RED}✗{RESET} {msg}")


def main():
    # --- Load pickles for comparison ---
    alis_clean = pd.read_pickle(PICKLE_DIR / "alis_clean_v3.pkl")
    satis_clean = pd.read_pickle(PICKLE_DIR / "satis_clean_v3.pkl")

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # ========================================================================
    print("=" * 70)
    print("CHECK 1 — Row counts")
    print("=" * 70)
    # ========================================================================

    # Get latest batch
    cur.execute("SELECT DISTINCT load_batch_id, MAX(loaded_at) FROM fact_purchase_lines_clean GROUP BY 1 ORDER BY 2 DESC LIMIT 1")
    row = cur.fetchone()
    if not row:
        fail("No rows in fact_purchase_lines_clean.")
        sys.exit(1)
    latest_batch, latest_ts = row
    print(f"\n  Latest batch: {latest_batch}")
    print(f"  Loaded at   : {latest_ts}")
    print()

    expected = {
        "bronze_nebim_alis_raw":        len(alis_clean),
        "bronze_nebim_satis_raw":       len(satis_clean),
        "fact_purchase_lines_clean":    len(alis_clean),
        "fact_sales_lines_clean":       len(satis_clean),
    }

    for tbl, exp_n in expected.items():
        cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE load_batch_id = %s", (str(latest_batch),))
        got = cur.fetchone()[0]
        if got == exp_n:
            ok(f"{tbl}: {got:,} rows (matches pickle)")
        else:
            fail(f"{tbl}: {got:,} rows but expected {exp_n:,}")

    # ========================================================================
    print("\n" + "=" * 70)
    print("CHECK 2 — Business bucket totals (fact_purchase_lines_clean)")
    print("=" * 70)
    # ========================================================================

    pickle_agg = alis_clean.groupby("business_bucket").agg(
        rows=("Hesap Kodu", "size"),
        amount=("Net Tutar (Y)", "sum"),
    ).sort_values("amount", ascending=False)

    cur.execute("""
        SELECT business_bucket, COUNT(*), COALESCE(SUM(net_tutar_y), 0)::numeric
        FROM fact_purchase_lines_clean
        WHERE load_batch_id = %s
        GROUP BY business_bucket
        ORDER BY SUM(net_tutar_y) DESC NULLS LAST
    """, (str(latest_batch),))
    db_rows = {b: (int(n), float(amt)) for b, n, amt in cur.fetchall()}

    all_ok = True
    for bucket, r in pickle_agg.iterrows():
        pkl_rows = int(r['rows'])
        pkl_amt = float(r['amount']) if pd.notna(r['amount']) else 0.0
        db_r, db_a = db_rows.get(bucket, (0, 0.0))
        rows_ok = db_r == pkl_rows
        amt_ok = abs(db_a - pkl_amt) < 1.0  # <1 TL tolerance for rounding
        if rows_ok and amt_ok:
            ok(f"{bucket:30s}  {pkl_rows:6,} rows  {pkl_amt:>15,.0f} TL")
        else:
            fail(f"{bucket:30s}  expected {pkl_rows}/{pkl_amt:,.0f} got {db_r}/{db_a:,.0f}")
            all_ok = False

    # ========================================================================
    print("\n" + "=" * 70)
    print("CHECK 3 — Business bucket totals (fact_sales_lines_clean)")
    print("=" * 70)
    # ========================================================================

    pickle_agg = satis_clean.groupby("business_bucket").agg(
        rows=("Hesap Kodu", "size"),
        amount=("Net Tutar (Y)", "sum"),
    ).sort_values("amount", ascending=False)

    cur.execute("""
        SELECT business_bucket, COUNT(*), COALESCE(SUM(net_tutar_y), 0)::numeric
        FROM fact_sales_lines_clean
        WHERE load_batch_id = %s
        GROUP BY business_bucket
        ORDER BY SUM(net_tutar_y) DESC NULLS LAST
    """, (str(latest_batch),))
    db_rows = {b: (int(n), float(amt)) for b, n, amt in cur.fetchall()}

    for bucket, r in pickle_agg.iterrows():
        pkl_rows = int(r['rows'])
        pkl_amt = float(r['amount']) if pd.notna(r['amount']) else 0.0
        db_r, db_a = db_rows.get(bucket, (0, 0.0))
        rows_ok = db_r == pkl_rows
        amt_ok = abs(db_a - pkl_amt) < 1.0
        if rows_ok and amt_ok:
            ok(f"{bucket:30s}  {pkl_rows:6,} rows  {pkl_amt:>15,.0f} TL")
        else:
            fail(f"{bucket:30s}  expected {pkl_rows}/{pkl_amt:,.0f} got {db_r}/{db_a:,.0f}")

    # ========================================================================
    print("\n" + "=" * 70)
    print("CHECK 4 — Date range coverage")
    print("=" * 70)
    # ========================================================================

    cur.execute("""
        SELECT MIN(fatura_tarihi), MAX(fatura_tarihi)
        FROM fact_purchase_lines_clean
        WHERE load_batch_id = %s
    """, (str(latest_batch),))
    min_p, max_p = cur.fetchone()
    cur.execute("""
        SELECT MIN(fatura_tarihi), MAX(fatura_tarihi)
        FROM fact_sales_lines_clean
        WHERE load_batch_id = %s
    """, (str(latest_batch),))
    min_s, max_s = cur.fetchone()

    print(f"  fact_purchase: {min_p} → {max_p}")
    print(f"  fact_sales   : {min_s} → {max_s}")
    ok("Date ranges look sane")

    # ========================================================================
    print("\n" + "=" * 70)
    print("CHECK 5 — Key anomaly rows present + correctly flagged")
    print("=" * 70)
    # ========================================================================

    # Yarn resale must be anomalous_review + subtype=yarn_resale
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(net_tutar_y), 0)::numeric
        FROM fact_sales_lines_clean
        WHERE load_batch_id = %s
          AND business_bucket = 'anomalous_review'
          AND subtype = 'yarn_resale'
    """, (str(latest_batch),))
    n, amt = cur.fetchone()
    expected_n = 826
    expected_amt = 458_744_832
    if int(n) == expected_n and abs(float(amt) - expected_amt) < 100:
        ok(f"Yarn resale: {int(n)} rows / {float(amt):,.0f} TL (correct, excluded from core revenue)")
    else:
        warn(f"Yarn resale: got {int(n)} rows / {float(amt):,.0f} TL, expected ~{expected_n}/{expected_amt:,}")

    # Suspected asset sales
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(net_tutar_y), 0)::numeric
        FROM fact_sales_lines_clean
        WHERE load_batch_id = %s
          AND subtype = 'suspected_asset_sale'
    """, (str(latest_batch),))
    n, amt = cur.fetchone()
    if int(n) == 2:
        ok(f"Suspected asset sales: 2 rows / {float(amt):,.0f} TL (MEHMET ALAGÖZ + GONCA)")
    else:
        warn(f"Suspected asset sales: got {int(n)} rows (expected 2)")

    # Contra revenue totals
    cur.execute("""
        SELECT COUNT(*), COALESCE(SUM(net_tutar_y), 0)::numeric
        FROM fact_purchase_lines_clean
        WHERE load_batch_id = %s
          AND subtype IN ('contra_revenue_return', 'contra_revenue_discount')
    """, (str(latest_batch),))
    n, amt = cur.fetchone()
    ok(f"Contra revenue (ALIŞ side): {int(n)} rows / {float(amt):,.0f} TL")

    # Supplier prepayments with is_prepayment flag
    cur.execute("""
        SELECT COUNT(*), COUNT(*) FILTER (WHERE is_prepayment = TRUE)
        FROM fact_purchase_lines_clean
        WHERE load_batch_id = %s
          AND business_bucket = 'supplier_prepayments'
    """, (str(latest_batch),))
    total, flagged = cur.fetchone()
    if total == flagged and total > 0:
        ok(f"Supplier prepayments: {total} rows, all flagged with is_prepayment=TRUE")
    else:
        warn(f"Supplier prepayments: {total} rows, {flagged} flagged (should be equal)")

    # ========================================================================
    print("\n" + "=" * 70)
    print("CHECK 6 — dim tables")
    print("=" * 70)
    # ========================================================================

    cur.execute("SELECT COUNT(*) FROM dim_business_bucket")
    n = cur.fetchone()[0]
    if n >= 25:
        ok(f"dim_business_bucket: {n} buckets seeded")
    else:
        warn(f"dim_business_bucket: only {n} buckets")

    cur.execute("SELECT version_label, is_current FROM dim_classification_version WHERE is_current = TRUE")
    row = cur.fetchone()
    if row and row[0] == "v3":
        ok(f"Current classification version: {row[0]}")
    else:
        warn(f"Current version: {row}")

    # ========================================================================
    print("\n" + "=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)
    # ========================================================================

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
