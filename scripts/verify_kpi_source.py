"""
verify_kpi_source.py - Read-only diagnostic to clarify where 'HIGH IMPACT 0' KPI value originates.

Theory: dashboard's top-strip 'HIGH IMPACT (7D)' KPI on Price Intelligence
sub-tab is reading from market_signals (news table), not from
price_intelligence_signals (signal cards). That explains why feed shows
YÜKSEK signals but KPI shows 0.

This script confirms by counting both possible sources.
"""
import os
import sys
import psycopg2
from datetime import datetime, timezone, timedelta

try:
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("[X] DATABASE_URL env var not set."); sys.exit(1)

cutoff_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

with psycopg2.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:

        print("=" * 75)
        print("CANDIDATE 1: market_signals (news/articles)")
        print("Feeds dashboard's 'HIGH IMPACT (7D)' KPI per server.py line 354")
        print("=" * 75)

        cur.execute(
            "SELECT COUNT(DISTINCT source_id)::int FROM market_signals "
            "WHERE detected_at >= %s AND impact_score >= 60",
            [cutoff_7d],
        )
        c1 = cur.fetchone()[0]
        print(f"  Distinct source_id with impact_score >= 60 (last 7d): {c1}")

        cur.execute(
            "SELECT COUNT(*) FROM market_signals WHERE detected_at >= %s",
            [cutoff_7d],
        )
        c1_total = cur.fetchone()[0]
        print(f"  Total market_signals rows last 7d:                    {c1_total}")

        cur.execute(
            "SELECT MIN(impact_score)::int, MAX(impact_score)::int, "
            "AVG(impact_score)::int "
            "FROM market_signals WHERE detected_at >= %s",
            [cutoff_7d],
        )
        smin, smax, savg = cur.fetchone()
        print(f"  impact_score range last 7d:  min={smin} max={smax} avg={savg}")

        print()
        print("=" * 75)
        print("CANDIDATE 2: price_intelligence_signals (chain mismatch / cost pressure)")
        print("Feeds dashboard's signal CARDS per server.py line 244 + 507")
        print("=" * 75)

        cur.execute(
            "SELECT COUNT(*)::int FROM price_intelligence_signals "
            "WHERE signal_date >= NOW() - INTERVAL '7 days' AND suppressed = FALSE"
        )
        c2 = cur.fetchone()[0]
        print(f"  Total active rows last 7d: {c2}")

        cur.execute(
            "SELECT severity, COUNT(*) FROM price_intelligence_signals "
            "WHERE signal_date >= NOW() - INTERVAL '7 days' AND suppressed = FALSE "
            "GROUP BY severity ORDER BY COUNT(*) DESC"
        )
        for sev, cnt in cur.fetchall():
            print(f"    {sev or '(null)':10} : {cnt}")

        print()
        print("=" * 75)
        print("VERDICT")
        print("=" * 75)
        if c1 == 0 and c2 > 0:
            print(f"  market_signals high-impact count = 0 (KPI reads this)")
            print(f"  price_intelligence_signals active = {c2} (feed reads this)")
            print(f"  -> 'HIGH IMPACT 0' KPI is technically correct but conceptually misplaced")
            print(f"     on the Price Intelligence sub-tab. Should either:")
            print(f"       (a) Replace the KPI with one that counts severity='high'")
            print(f"           in price_intelligence_signals, OR")
            print(f"       (b) Move/scope the strip so it doesn't appear on this sub-tab.")
        else:
            print(f"  market_signals: {c1}, price_intelligence_signals: {c2}")
            print(f"  -> Investigate further; theory not cleanly confirmed.")
