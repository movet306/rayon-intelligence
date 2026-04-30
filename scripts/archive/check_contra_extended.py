"""
Extended diagnostic for contra revenue spike (Mar 2026 vs Mar 2025).

Sections:
  1. 24-month contra trend with contra% (gross-relative)
  2. Median / max / min contra% — anomaly context
  3. Source split (ALIŞ vs SATIŞ) for Mar 2026 and Mar 2025
  4. Subtype split for Mar 2026 and Mar 2025
  5. Top counterparty concentration (Mar 2026)
  6. Top counterparty concentration (Mar 2025) — for comparison
  7. v3 classification check — are both months processed by same rules
"""
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()


def section(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


# ============================================================================
section("1) 24-MONTH CONTRA TREND")
# ============================================================================
cur.execute("""
    WITH monthly AS (
        SELECT
            DATE_TRUNC('month', s.fatura_tarihi)::date AS month,
            SUM(CASE WHEN s.business_bucket = 'sales_return_contra' THEN s.net_tutar_y ELSE 0 END) AS satis_contra,
            SUM(CASE WHEN s.business_bucket = 'core_product_sales' THEN s.net_tutar_y ELSE 0 END)
              + SUM(CASE WHEN s.business_bucket = 'outsourced_service_revenue' THEN s.net_tutar_y ELSE 0 END) AS gross
        FROM fact_sales_lines_clean s
        WHERE s.fatura_tarihi IS NOT NULL
        GROUP BY 1
    ),
    purchase_contra AS (
        SELECT DATE_TRUNC('month', fatura_tarihi)::date AS month,
               SUM(net_tutar_y) AS alis_contra
        FROM fact_purchase_lines_clean
        WHERE business_bucket = 'sales_return_contra'
        GROUP BY 1
    )
    SELECT
        to_char(m.month, 'YYYY-MM') AS ay,
        m.satis_contra::float        AS satis_contra,
        COALESCE(pc.alis_contra, 0)::float AS alis_contra,
        (m.satis_contra + COALESCE(pc.alis_contra, 0))::float AS total_contra,
        m.gross::float               AS gross,
        ROUND(((m.satis_contra + COALESCE(pc.alis_contra, 0))
               / NULLIF(m.gross, 0) * 100)::numeric, 2) AS contra_pct
    FROM monthly m
    LEFT JOIN purchase_contra pc USING (month)
    WHERE m.month >= (CURRENT_DATE - INTERVAL '24 months')
    ORDER BY 1
""")
print(f"  {'month':>8s}  {'SATIŞ contra':>14s}  {'ALIŞ contra':>14s}  {'total':>14s}  {'gross':>15s}  {'contra%':>8s}")
contra_pcts = []
for row in cur.fetchall():
    ay, sat, ali, tot, gross, pct = row
    pct_v = float(pct) if pct is not None else 0.0
    contra_pcts.append((ay, pct_v, float(tot)))
    print(f"  {ay:>8s}  {float(sat):>14,.0f}  {float(ali):>14,.0f}  {float(tot):>14,.0f}  {float(gross):>15,.0f}  {str(pct):>8s}")


# ============================================================================
section("2) ANOMALY CONTEXT — median / max / min contra%")
# ============================================================================
if contra_pcts:
    pcts_only = sorted([p for _, p, _ in contra_pcts])
    n = len(pcts_only)
    median = pcts_only[n // 2]
    mn = min(pcts_only)
    mx = max(pcts_only)
    avg = sum(pcts_only) / n
    print(f"  Sample size            : {n} months")
    print(f"  Min contra%            : {mn:.2f}%")
    print(f"  Median contra%         : {median:.2f}%")
    print(f"  Mean contra%           : {avg:.2f}%")
    print(f"  Max contra%            : {mx:.2f}%")
    # Find Mar 2026 specifically
    mar26 = next((p for ay, p, _ in contra_pcts if ay == "2026-03"), None)
    mar25 = next((p for ay, p, _ in contra_pcts if ay == "2025-03"), None)
    if mar26 is not None:
        ratio_to_median = (mar26 / median) if median > 0 else None
        print(f"  Mar 2026 contra%       : {mar26:.2f}%")
        if ratio_to_median:
            print(f"    → {ratio_to_median:.1f}x the median")
        if mar26 == mx:
            print(f"    → MAX of last 24 months")
    if mar25 is not None:
        print(f"  Mar 2025 contra%       : {mar25:.2f}%  (the prior-year reference for KPI YoY)")


# ============================================================================
section("3) SOURCE SPLIT — ALIŞ vs SATIŞ for Mar 2026 and Mar 2025")
# ============================================================================
cur.execute("""
    SELECT 'Mar 2026' AS period, 'ALIŞ' AS source,
           COUNT(*)::int AS rows,
           SUM(net_tutar_y)::float AS amt
    FROM fact_purchase_lines_clean
    WHERE business_bucket = 'sales_return_contra'
      AND fatura_tarihi >= '2026-03-01' AND fatura_tarihi < '2026-04-01'
    UNION ALL
    SELECT 'Mar 2026', 'SATIŞ',
           COUNT(*)::int,
           SUM(net_tutar_y)::float
    FROM fact_sales_lines_clean
    WHERE business_bucket = 'sales_return_contra'
      AND fatura_tarihi >= '2026-03-01' AND fatura_tarihi < '2026-04-01'
    UNION ALL
    SELECT 'Mar 2025', 'ALIŞ',
           COUNT(*)::int,
           SUM(net_tutar_y)::float
    FROM fact_purchase_lines_clean
    WHERE business_bucket = 'sales_return_contra'
      AND fatura_tarihi >= '2025-03-01' AND fatura_tarihi < '2025-04-01'
    UNION ALL
    SELECT 'Mar 2025', 'SATIŞ',
           COUNT(*)::int,
           SUM(net_tutar_y)::float
    FROM fact_sales_lines_clean
    WHERE business_bucket = 'sales_return_contra'
      AND fatura_tarihi >= '2025-03-01' AND fatura_tarihi < '2025-04-01'
    ORDER BY 1, 2
""")
print(f"  {'period':>10s}  {'source':>8s}  {'rows':>8s}  {'amount_TL':>15s}")
for row in cur.fetchall():
    print(f"  {row[0]:>10s}  {row[1]:>8s}  {row[2]:>8,}  {(float(row[3]) if row[3] else 0):>15,.0f}")


# ============================================================================
section("4) SUBTYPE SPLIT — Mar 2026 and Mar 2025 contra")
# ============================================================================
cur.execute("""
    SELECT period, source, subtype, rows, amt FROM (
        SELECT 'Mar 2026' AS period, 'ALIŞ' AS source,
               COALESCE(subtype, '<null>') AS subtype,
               COUNT(*)::int AS rows,
               SUM(net_tutar_y)::float AS amt
        FROM fact_purchase_lines_clean
        WHERE business_bucket = 'sales_return_contra'
          AND fatura_tarihi >= '2026-03-01' AND fatura_tarihi < '2026-04-01'
        GROUP BY 3
        UNION ALL
        SELECT 'Mar 2026', 'SATIŞ',
               COALESCE(subtype, '<null>'),
               COUNT(*)::int,
               SUM(net_tutar_y)::float
        FROM fact_sales_lines_clean
        WHERE business_bucket = 'sales_return_contra'
          AND fatura_tarihi >= '2026-03-01' AND fatura_tarihi < '2026-04-01'
        GROUP BY 3
        UNION ALL
        SELECT 'Mar 2025', 'ALIŞ',
               COALESCE(subtype, '<null>'),
               COUNT(*)::int,
               SUM(net_tutar_y)::float
        FROM fact_purchase_lines_clean
        WHERE business_bucket = 'sales_return_contra'
          AND fatura_tarihi >= '2025-03-01' AND fatura_tarihi < '2025-04-01'
        GROUP BY 3
        UNION ALL
        SELECT 'Mar 2025', 'SATIŞ',
               COALESCE(subtype, '<null>'),
               COUNT(*)::int,
               SUM(net_tutar_y)::float
        FROM fact_sales_lines_clean
        WHERE business_bucket = 'sales_return_contra'
          AND fatura_tarihi >= '2025-03-01' AND fatura_tarihi < '2025-04-01'
        GROUP BY 3
    ) t
    ORDER BY period, source, amt DESC
""")
print(f"  {'period':>10s}  {'source':>8s}  {'subtype':>30s}  {'rows':>6s}  {'amount_TL':>15s}")
for row in cur.fetchall():
    print(f"  {row[0]:>10s}  {row[1]:>8s}  {str(row[2]):>30s}  {row[3]:>6,}  {(float(row[4]) if row[4] else 0):>15,.0f}")


# ============================================================================
section("5) TOP COUNTERPARTY CONCENTRATION — Mar 2026 contra")
# ============================================================================
cur.execute("""
    SELECT party, source, hesap_kodu, subtype, amt FROM (
        SELECT cari_hesap_aciklamasi AS party, 'ALIŞ' AS source,
               hesap_kodu, COALESCE(subtype, '<null>') AS subtype,
               SUM(net_tutar_y)::float AS amt
        FROM fact_purchase_lines_clean
        WHERE business_bucket = 'sales_return_contra'
          AND fatura_tarihi >= '2026-03-01' AND fatura_tarihi < '2026-04-01'
        GROUP BY 1, 2, 3, 4
        UNION ALL
        SELECT cari_hesap_aciklamasi, 'SATIŞ',
               hesap_kodu, COALESCE(subtype, '<null>'),
               SUM(net_tutar_y)::float
        FROM fact_sales_lines_clean
        WHERE business_bucket = 'sales_return_contra'
          AND fatura_tarihi >= '2026-03-01' AND fatura_tarihi < '2026-04-01'
        GROUP BY 1, 2, 3, 4
    ) t
    ORDER BY amt DESC NULLS LAST
    LIMIT 15
""")
print(f"  {'counterparty':<35s}  {'source':>6s}  {'hesap':<15s}  {'subtype':>30s}  {'amount_TL':>13s}")
total_top = 0
all_rows = cur.fetchall()
for row in all_rows:
    party, source, hesap, subtype, amt = row
    total_top += float(amt) if amt else 0
    print(f"  {str(party)[:35]:<35s}  {source:>6s}  {str(hesap):<15s}  {subtype:>30s}  {(float(amt) if amt else 0):>13,.0f}")

# Total Mar 2026 contra
cur.execute("""
    SELECT
        (SELECT COALESCE(SUM(net_tutar_y), 0) FROM fact_purchase_lines_clean
         WHERE business_bucket = 'sales_return_contra'
           AND fatura_tarihi >= '2026-03-01' AND fatura_tarihi < '2026-04-01')
        +
        (SELECT COALESCE(SUM(net_tutar_y), 0) FROM fact_sales_lines_clean
         WHERE business_bucket = 'sales_return_contra'
           AND fatura_tarihi >= '2026-03-01' AND fatura_tarihi < '2026-04-01')
""")
total_mar26 = float(cur.fetchone()[0] or 0)
print()
print(f"  Top 15 sum         : {total_top:>15,.0f} TL")
print(f"  Total Mar 2026     : {total_mar26:>15,.0f} TL")
if total_mar26 > 0:
    print(f"  Top-15 concentration: {(total_top / total_mar26 * 100):.1f}%")


# ============================================================================
section("6) TOP COUNTERPARTY CONCENTRATION — Mar 2025 contra")
# ============================================================================
cur.execute("""
    SELECT party, source, hesap_kodu, subtype, amt FROM (
        SELECT cari_hesap_aciklamasi AS party, 'ALIŞ' AS source,
               hesap_kodu, COALESCE(subtype, '<null>') AS subtype,
               SUM(net_tutar_y)::float AS amt
        FROM fact_purchase_lines_clean
        WHERE business_bucket = 'sales_return_contra'
          AND fatura_tarihi >= '2025-03-01' AND fatura_tarihi < '2025-04-01'
        GROUP BY 1, 2, 3, 4
        UNION ALL
        SELECT cari_hesap_aciklamasi, 'SATIŞ',
               hesap_kodu, COALESCE(subtype, '<null>'),
               SUM(net_tutar_y)::float
        FROM fact_sales_lines_clean
        WHERE business_bucket = 'sales_return_contra'
          AND fatura_tarihi >= '2025-03-01' AND fatura_tarihi < '2025-04-01'
        GROUP BY 1, 2, 3, 4
    ) t
    ORDER BY amt DESC NULLS LAST
    LIMIT 10
""")
print(f"  {'counterparty':<35s}  {'source':>6s}  {'hesap':<15s}  {'subtype':>30s}  {'amount_TL':>13s}")
for row in cur.fetchall():
    party, source, hesap, subtype, amt = row
    print(f"  {str(party)[:35]:<35s}  {source:>6s}  {str(hesap):<15s}  {subtype:>30s}  {(float(amt) if amt else 0):>13,.0f}")


# ============================================================================
section("7) CLASSIFICATION CONSISTENCY CHECK")
# ============================================================================
cur.execute("""
    SELECT
        classification_version,
        COUNT(*)::int AS rows,
        MIN(loaded_at) AS earliest_load,
        MAX(loaded_at) AS latest_load
    FROM fact_purchase_lines_clean
    WHERE business_bucket = 'sales_return_contra'
      AND (fatura_tarihi >= '2025-03-01' AND fatura_tarihi < '2025-04-01'
           OR fatura_tarihi >= '2026-03-01' AND fatura_tarihi < '2026-04-01')
    GROUP BY classification_version
""")
print(f"  ALIŞ contra in Mar 2025 + Mar 2026:")
for row in cur.fetchall():
    print(f"    classification_version: {row[0]}, {row[1]:,} rows, loaded at {row[3]}")

cur.execute("""
    SELECT
        classification_version,
        COUNT(*)::int AS rows,
        MIN(loaded_at) AS earliest_load,
        MAX(loaded_at) AS latest_load
    FROM fact_sales_lines_clean
    WHERE business_bucket = 'sales_return_contra'
      AND (fatura_tarihi >= '2025-03-01' AND fatura_tarihi < '2025-04-01'
           OR fatura_tarihi >= '2026-03-01' AND fatura_tarihi < '2026-04-01')
    GROUP BY classification_version
""")
print(f"  SATIŞ contra in Mar 2025 + Mar 2026:")
for row in cur.fetchall():
    print(f"    classification_version: {row[0]}, {row[1]:,} rows, loaded at {row[3]}")

print()
print("  → If both periods show classification_version='v3' loaded in the same batch,")
print("    the YoY comparison is methodologically consistent (apples-to-apples).")
print("    If they show different versions or load times, the spike may be artifactual.")


conn.close()
print()
print("=" * 78)
print("DIAGNOSTIC COMPLETE")
print("=" * 78)
