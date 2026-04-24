"""
Nebim ETL Loader — v3 pickles → PostgreSQL bronze + silver tables.

Assumes migration 009 has already been applied (tables exist).
Idempotent: uses load_batch_id to tag each run. Previous batches remain.
Safe to re-run: each call creates a fresh batch; existing data untouched.

Usage:
    python scripts/etl_nebim_load.py

Reads:
    outputs/v3/alis_raw.pkl
    outputs/v3/satis_raw.pkl
    outputs/v3/alis_clean_v3.pkl
    outputs/v3/satis_clean_v3.pkl

Writes:
    bronze_nebim_alis_raw
    bronze_nebim_satis_raw
    fact_purchase_lines_clean
    fact_sales_lines_clean
"""
import os
import sys
import time
import uuid
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv


# ============================================================================
# Config & connection
# ============================================================================

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

PICKLE_DIR = Path("outputs/v3")
CLASSIFICATION_VERSION = "v3"


# ============================================================================
# Column mappings — Excel/Pandas column name → DB column
# ============================================================================

# Bronze table columns (17 source columns + audit)
BRONZE_COL_MAP = {
    "Fatura Tarihi":           "fatura_tarihi",
    "E-Fatura Seri Numarası":  "e_fatura_seri_numarasi",
    "Cari Hesap Açıklaması":   "cari_hesap_aciklamasi",
    "Vergi Dairesi":           "vergi_dairesi",
    "Vergi Numarası":          "vergi_numarasi",
    "Kdv Oranı":               "kdv_orani",
    "Birim Cinsi (1)":         "birim_cinsi_1",
    "Miktar":                  "miktar",
    "Vergi Hariç Tutar (Y)":   "vergi_haric_tutar_y",
    "Kdv (Y)":                 "kdv_y",
    "Net Tutar (Y)":           "net_tutar_y",
    "Hesap Kodu":              "hesap_kodu",
    "Hesap Açıklaması":        "hesap_aciklamasi",
    "Vergi Hariç Tutar (D)":   "vergi_haric_tutar_d",
    "Kdv (D)":                 "kdv_d",
    "Net Tutar (D)":           "net_tutar_d",
    "Para Birimi (D)":         "para_birimi_d",
}

# Fact (silver) table columns — includes classification enrichment
# Note: birim_cinsi (no "_1" suffix in silver for readability)
FACT_RAW_COL_MAP = {
    "Fatura Tarihi":           "fatura_tarihi",
    "E-Fatura Seri Numarası":  "e_fatura_seri_numarasi",
    "Cari Hesap Açıklaması":   "cari_hesap_aciklamasi",
    "Vergi Dairesi":           "vergi_dairesi",
    "Vergi Numarası":          "vergi_numarasi",
    "Kdv Oranı":               "kdv_orani",
    "Birim Cinsi (1)":         "birim_cinsi",
    "Miktar":                  "miktar",
    "Vergi Hariç Tutar (Y)":   "vergi_haric_tutar_y",
    "Kdv (Y)":                 "kdv_y",
    "Net Tutar (Y)":           "net_tutar_y",
    "Hesap Kodu":              "hesap_kodu",
    "Hesap Açıklaması":        "hesap_aciklamasi",
    "Vergi Hariç Tutar (D)":   "vergi_haric_tutar_d",
    "Kdv (D)":                 "kdv_d",
    "Net Tutar (D)":           "net_tutar_d",
    "Para Birimi (D)":         "para_birimi_d",
}

FACT_DERIVED_COLS = [
    "account_prefix_3", "account_class_main", "account_class_sub",
    "business_bucket", "subtype", "project_use_case",
    "is_core_business_relevant", "is_cost_model_relevant",
    "review_flag", "confidence_level", "classification_reason",
    "clean_unit_group", "clean_product_type", "clean_counterparty_type",
    "is_prepayment", "realized_in_procurement",
]


# ============================================================================
# Helpers
# ============================================================================

def _safe(val):
    """Convert pandas NaN/NaT to Python None for psycopg2."""
    if pd.isna(val):
        return None
    if isinstance(val, pd.Timestamp):
        return val.to_pydatetime()
    return val


def _as_int_tuple_row(row, cols, extra_fields):
    """Build a tuple for INSERT from a DataFrame row + extra audit fields."""
    return tuple(_safe(row[c]) for c in cols) + extra_fields


# ============================================================================
# Bronze load
# ============================================================================

def load_bronze(conn, table_name, df_raw, batch_id, loaded_at):
    print(f"\n  Loading {table_name} ({len(df_raw):,} rows)...")
    t0 = time.time()

    # Build column list — audit cols + source cols (in DB order)
    audit_cols = ["source_row_id", "load_batch_id", "loaded_at"]
    source_cols = list(BRONZE_COL_MAP.values())  # DB column names
    all_cols = audit_cols + source_cols

    # Build rows
    rows = []
    for idx, row in df_raw.iterrows():
        audit_vals = (int(idx), batch_id, loaded_at)
        source_vals = tuple(_safe(row[pd_col]) for pd_col in BRONZE_COL_MAP.keys())
        rows.append(audit_vals + source_vals)

    cur = conn.cursor()
    cols_sql = ", ".join(all_cols)
    sql = f"INSERT INTO {table_name} ({cols_sql}) VALUES %s"
    execute_values(cur, sql, rows, page_size=1000)
    conn.commit()
    cur.close()
    print(f"    [{time.time()-t0:.1f}s] inserted {len(rows):,} bronze rows")


# ============================================================================
# Silver load (fact tables)
# ============================================================================

def load_fact(conn, table_name, df_clean, source_sheet, batch_id, loaded_at, class_version):
    print(f"\n  Loading {table_name} ({len(df_clean):,} rows)...")
    t0 = time.time()

    # Ordered list of DB columns (matches migration SQL order)
    audit_cols = [
        "source_sheet", "source_row_id", "bronze_id",
        "load_batch_id", "classification_version", "loaded_at",
    ]
    raw_cols = list(FACT_RAW_COL_MAP.values())
    derived_cols = FACT_DERIVED_COLS
    all_cols = audit_cols + raw_cols + derived_cols

    rows = []
    for idx, row in df_clean.iterrows():
        # Audit
        audit_vals = (source_sheet, int(idx), None, batch_id, class_version, loaded_at)
        # Raw source values (using original pandas column names)
        raw_vals = tuple(_safe(row[pd_col]) for pd_col in FACT_RAW_COL_MAP.keys())
        # Derived values
        derived_vals = tuple(_safe(row[c]) for c in FACT_DERIVED_COLS)
        rows.append(audit_vals + raw_vals + derived_vals)

    cur = conn.cursor()
    cols_sql = ", ".join(all_cols)
    sql = f"INSERT INTO {table_name} ({cols_sql}) VALUES %s"
    execute_values(cur, sql, rows, page_size=1000)
    conn.commit()
    cur.close()
    print(f"    [{time.time()-t0:.1f}s] inserted {len(rows):,} fact rows")


# ============================================================================
# MAIN
# ============================================================================

def main():
    # --- Load pickles ---
    required = ["alis_raw.pkl", "satis_raw.pkl", "alis_clean_v3.pkl", "satis_clean_v3.pkl"]
    for f in required:
        if not (PICKLE_DIR / f).exists():
            print(f"ERROR: {PICKLE_DIR / f} not found.")
            print("Run `python scripts/classify_nebim_v3.py` first.")
            sys.exit(1)

    print("Loading pickles...")
    alis_raw    = pd.read_pickle(PICKLE_DIR / "alis_raw.pkl")
    satis_raw   = pd.read_pickle(PICKLE_DIR / "satis_raw.pkl")
    alis_clean  = pd.read_pickle(PICKLE_DIR / "alis_clean_v3.pkl")
    satis_clean = pd.read_pickle(PICKLE_DIR / "satis_clean_v3.pkl")

    print(f"  ALIŞ raw  : {len(alis_raw):,} rows")
    print(f"  SATIŞ raw : {len(satis_raw):,} rows")
    print(f"  ALIŞ clean: {len(alis_clean):,} rows")
    print(f"  SATIŞ clean: {len(satis_clean):,} rows")

    # --- Connect to DB ---
    print(f"\nConnecting to DB...")
    conn = psycopg2.connect(DATABASE_URL)
    print("  Connected.")

    # --- Pre-flight: verify tables exist ---
    cur = conn.cursor()
    for tbl in [
        "bronze_nebim_alis_raw", "bronze_nebim_satis_raw",
        "fact_purchase_lines_clean", "fact_sales_lines_clean",
        "dim_business_bucket", "dim_classification_version",
    ]:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
            (tbl,),
        )
        if not cur.fetchone()[0]:
            print(f"ERROR: table {tbl} does not exist. Run migration 009 first.")
            sys.exit(1)
    cur.close()
    print("  All migration 009 tables present ✓")

    # --- New batch ID for this load ---
    batch_id = str(uuid.uuid4())
    loaded_at = pd.Timestamp.now(tz="UTC")
    print(f"\n=== NEW BATCH: {batch_id} ===")
    print(f"=== Loaded at: {loaded_at} ===")
    print(f"=== Classification version: {CLASSIFICATION_VERSION} ===")

    total_t0 = time.time()

    # --- Bronze loads ---
    load_bronze(conn, "bronze_nebim_alis_raw",  alis_raw,  batch_id, loaded_at)
    load_bronze(conn, "bronze_nebim_satis_raw", satis_raw, batch_id, loaded_at)

    # --- Silver loads ---
    load_fact(conn, "fact_purchase_lines_clean", alis_clean,  "ALIS",  batch_id, loaded_at, CLASSIFICATION_VERSION)
    load_fact(conn, "fact_sales_lines_clean",    satis_clean, "SATIS", batch_id, loaded_at, CLASSIFICATION_VERSION)

    # --- Final stats ---
    print(f"\n=== LOAD COMPLETE ===")
    print(f"Total elapsed: {time.time()-total_t0:.1f}s")

    cur = conn.cursor()
    for tbl in ["bronze_nebim_alis_raw", "bronze_nebim_satis_raw",
                "fact_purchase_lines_clean", "fact_sales_lines_clean"]:
        cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE load_batch_id = %s", (batch_id,))
        n = cur.fetchone()[0]
        print(f"  {tbl}: {n:,} rows in this batch")

    cur.execute("SELECT COUNT(*) FROM fact_purchase_lines_clean")
    total_p = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM fact_sales_lines_clean")
    total_s = cur.fetchone()[0]
    print(f"\n  Total (all batches): fact_purchase={total_p:,}  fact_sales={total_s:,}")

    cur.close()
    conn.close()
    print(f"\nBatch ID for audit: {batch_id}")
    print("Next: python scripts/verify_nebim_load.py")


if __name__ == "__main__":
    main()
