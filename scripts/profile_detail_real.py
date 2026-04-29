"""
M2.2.6 deep profiling — locate the real 7-9s bottleneck.

Tests in increasing isolation:
  1. Direct DB queries on a single open connection (pure DB time)
  2. Direct DB queries opening fresh connection each time (handshake cost)
  3. The FastAPI endpoint via HTTP (full stack: pool + queries + serialization)
  4. The FastAPI endpoint internals replayed in-process (skip HTTP layer)

Output reveals which layer adds the latency:
  - If (1) fast and (3) slow: FastAPI / pool / serialization
  - If (1) slow: DB query plans bad
  - If (2) much slower than (1): pool not actually reusing
"""
import time
import os
import requests
from dotenv import load_dotenv
import psycopg2

load_dotenv()
DB_URL = os.environ["DATABASE_URL"]

CANONICAL_KEY = "tax:REDACTED_TAX_ID.0"
VERGI = "REDACTED_TAX_ID.0"

print("=" * 70)
print("DEEP PROFILING — counterparty/detail endpoint")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────
# Test 1: All queries on ONE persistent connection (pure DB time)
# ─────────────────────────────────────────────────────────────────────────
print("\n[1] All queries on ONE persistent connection")
print("-" * 70)

t_open = time.time()
conn = psycopg2.connect(DB_URL)
print(f"  initial connect:           {(time.time()-t_open)*1000:>7.0f} ms")

# Mimic the real endpoint's queries (approximations — actual SQL may differ)
queries = [
    ("horizon",       "SELECT MAX(fatura_tarihi) FROM fact_purchase_lines_clean"),
    ("header",        "SELECT * FROM dim_counterparty_mv WHERE canonical_key = %s LIMIT 1"),
    ("summary",       """SELECT SUM(net_tutar_y), COUNT(*), COUNT(DISTINCT cari_hesap_aciklamasi)
                         FROM fact_purchase_lines_clean
                         WHERE vergi_numarasi = %s AND fatura_tarihi >= (CURRENT_DATE - INTERVAL '24 months')"""),
    ("side_total",    """SELECT SUM(net_tutar_y) FROM fact_purchase_lines_clean
                         WHERE fatura_tarihi >= (CURRENT_DATE - INTERVAL '24 months')"""),
    ("monthly",       """SELECT DATE_TRUNC('month', fatura_tarihi)::date, SUM(net_tutar_y), COUNT(*)
                         FROM fact_purchase_lines_clean
                         WHERE vergi_numarasi = %s AND fatura_tarihi >= (CURRENT_DATE - INTERVAL '24 months')
                         GROUP BY 1 ORDER BY 1"""),
    ("buckets",       """SELECT business_bucket, SUM(net_tutar_y), COUNT(*)
                         FROM fact_purchase_lines_clean
                         WHERE vergi_numarasi = %s AND fatura_tarihi >= (CURRENT_DATE - INTERVAL '24 months')
                         GROUP BY 1"""),
    ("currency",      """SELECT para_birimi_d, SUM(net_tutar_y), COUNT(*)
                         FROM fact_purchase_lines_clean
                         WHERE vergi_numarasi = %s AND fatura_tarihi >= (CURRENT_DATE - INTERVAL '24 months')
                         GROUP BY 1"""),
    ("recent_rows",   """SELECT fatura_tarihi, net_tutar_y, business_bucket, para_birimi_d
                         FROM fact_purchase_lines_clean
                         WHERE vergi_numarasi = %s AND fatura_tarihi >= (CURRENT_DATE - INTERVAL '24 months')
                         ORDER BY fatura_tarihi DESC LIMIT 10"""),
]

t_total = 0
for name, sql in queries:
    params = []
    if "%s" in sql:
        # Determine param: use canonical_key for header, vergi for others
        if name == "header":
            params = [CANONICAL_KEY]
        else:
            params = [VERGI]
    t0 = time.time()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    elapsed = (time.time() - t0) * 1000
    t_total += elapsed
    print(f"  {name:15s} ({len(rows):>4} rows):     {elapsed:>7.0f} ms")
print(f"  {'TOTAL':15s} (queries only):  {t_total:>7.0f} ms")

t_close = time.time()
conn.close()
print(f"  close:                      {(time.time()-t_close)*1000:>7.0f} ms")


# ─────────────────────────────────────────────────────────────────────────
# Test 2: Each query opens its own fresh connection (worst case)
# ─────────────────────────────────────────────────────────────────────────
print("\n[2] Each query on a FRESH connection (handshake every time)")
print("-" * 70)
t_total = 0
for name, sql in queries:
    params = []
    if "%s" in sql:
        params = [CANONICAL_KEY] if name == "header" else [VERGI]
    t0 = time.time()
    c = psycopg2.connect(DB_URL)
    with c.cursor() as cur:
        cur.execute(sql, params)
        cur.fetchall()
    c.close()
    elapsed = (time.time() - t0) * 1000
    t_total += elapsed
    print(f"  {name:15s}                 {elapsed:>7.0f} ms")
print(f"  {'TOTAL':15s}                 {t_total:>7.0f} ms")


# ─────────────────────────────────────────────────────────────────────────
# Test 3: Endpoint via HTTP — 3 calls, see if pool actually warms
# ─────────────────────────────────────────────────────────────────────────
print("\n[3] HTTP calls to the live endpoint (3 in a row)")
print("-" * 70)
url = f"http://localhost:8000/api/internal/counterparty/detail?side=purchase&canonical_key={CANONICAL_KEY}&months=24"
for i in range(3):
    t0 = time.time()
    try:
        r = requests.get(url, timeout=60)
        elapsed = (time.time() - t0) * 1000
        size = len(r.content)
        print(f"  call {i+1}:  {elapsed:>7.0f} ms   status={r.status_code}   {size:>7} bytes")
    except Exception as e:
        print(f"  call {i+1}:  ERROR — {e}")


# ─────────────────────────────────────────────────────────────────────────
# Diagnosis hints
# ─────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("DIAGNOSIS HINTS")
print("=" * 70)
print("""
Compare these three numbers:

  [1] queries-only TOTAL:     pure DB time (lower bound)
  [2] fresh-connect TOTAL:    [1] + handshake-per-query
  [3] HTTP call 2-3 timing:   [1] + FastAPI + pool + serialization

If [3] ≈ [1]: pool works, no extra latency, system is healthy.
If [3] >> [1] but ≈ [2]: pool is NOT reusing connections (patch broken).
If [3] >> both: bottleneck is in FastAPI / Python / network beyond DB.
If [1] is itself slow (>3s): DB plans need indexing/optimization.
""")
