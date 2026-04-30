"""
diagnose_signal_duplicates.py - Read-only diagnostic.

Counts how many duplicates exist in price_intelligence_signals using the
proposed dedup key. Does NOT modify any data.

Output: shows distinct signal patterns, how many times each appears, and
the date range each pattern spans. Used to validate the dedup strategy
before applying any change.
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

QUERY_TOTAL = "SELECT COUNT(*) FROM price_intelligence_signals WHERE suppressed = false"

QUERY_PATTERNS = """
SELECT
    signal_type,
    chain,
    COALESCE(material_slug, '-')      AS material,
    COALESCE(upstream_slug, '-')      AS upstream,
    COALESCE(downstream_slug, '-')    AS downstream,
    COUNT(*)                          AS occurrences,
    MIN(signal_date)                  AS first_seen,
    MAX(signal_date)                  AS last_seen,
    MIN(severity)                     AS sev_min,
    MAX(severity)                     AS sev_max,
    ROUND(MIN(value_pct)::numeric, 2) AS pct_min,
    ROUND(MAX(value_pct)::numeric, 2) AS pct_max
FROM price_intelligence_signals
WHERE suppressed = false
GROUP BY signal_type, chain, material_slug, upstream_slug, downstream_slug
ORDER BY occurrences DESC, signal_type;
"""

QUERY_SEVERITY_COUNTS = """
SELECT severity, COUNT(*)
FROM price_intelligence_signals
WHERE suppressed = false
GROUP BY severity
ORDER BY COUNT(*) DESC;
"""

QUERY_DATE_DISTRIBUTION = """
SELECT signal_date, COUNT(*) AS signals_that_day
FROM price_intelligence_signals
WHERE suppressed = false
GROUP BY signal_date
ORDER BY signal_date;
"""

with psycopg2.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        cur.execute(QUERY_TOTAL)
        total = cur.fetchone()[0]
        print(f"\nTotal active (non-suppressed) signals: {total}\n")

        print("=" * 120)
        print("DISTINCT SIGNAL PATTERNS (by dedup key)")
        print("=" * 120)
        cur.execute(QUERY_PATTERNS)
        rows = cur.fetchall()
        print(f"{'TYPE':30} {'CHAIN':10} {'MATERIAL':20} {'UPSTREAM':15} {'DOWNSTREAM':18} {'N':>3} {'FIRST':12} {'LAST':12} {'SEV':12} {'PCT_RANGE':18}")
        print("-" * 165)
        for r in rows:
            (stype, chain, mat, up, down, n, first, last, smin, smax, pmin, pmax) = r
            sev = smin if smin == smax else f"{smin}/{smax}"
            pct_range = f"{pmin}..{pmax}" if pmin != pmax else f"{pmin}"
            print(f"{stype:30} {chain:10} {mat:20} {up:15} {down:18} {n:>3} {str(first):12} {str(last):12} {sev:12} {pct_range:18}")

        # Compute "duplicate burden" = total - distinct patterns
        distinct_patterns = len(rows)
        duplicate_burden = total - distinct_patterns
        print()
        print(f"Distinct patterns: {distinct_patterns}")
        print(f"Duplicate burden: {duplicate_burden} rows ({100*duplicate_burden/total:.1f}% of feed)")

        print()
        print("=" * 60)
        print("SEVERITY DISTRIBUTION (for KPI bug diagnosis)")
        print("=" * 60)
        cur.execute(QUERY_SEVERITY_COUNTS)
        for sev, cnt in cur.fetchall():
            print(f"  {sev or '(null)':15} {cnt:>4}")

        print()
        print("=" * 60)
        print("SIGNAL VOLUME PER DAY")
        print("=" * 60)
        cur.execute(QUERY_DATE_DISTRIBUTION)
        for d, cnt in cur.fetchall():
            print(f"  {d}  {cnt:>3}")
