"""
pi_1_1_endpoint_switch.py - Targeted FROM-clause swap for the feed endpoint only.

Context:
  After running pi_1_1_dedup_view.py, the SQL view v_active_signals exists,
  but the endpoint switch step aborted defensively because three different
  endpoints contain `FROM price_intelligence_signals`. Only ONE of them —
  the feed endpoint — should be switched.

  Endpoints that MUST stay on the raw table (per PI-1.1 narrow scope):
    line ~244  : /api/stats  price_signals_active counter
    line ~1948 : /api/price_intelligence_stats  Action Now KPI
    line ~1961 : /api/price_intelligence_stats  Cost Pressure Up KPI
    line ~1973 : /api/price_intelligence_stats  Cost Pressure Down KPI

  Endpoint to switch:
    line ~531  : /api/price_intelligence_signals (the feed)

This script uses a multi-line context block to anchor the swap unambiguously
to the feed endpoint. If the surrounding code shifts, the script aborts
rather than corrupting the file.

Idempotent: detects whether the switch already happened.
"""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "dashboard" / "server.py"

# Multi-line anchor: the four lines preceding "FROM price_intelligence_signals"
# in the feed endpoint are unique in the file (turkey_lag_max, suppressed list,
# and the FROM line). This won't accidentally match the KPI queries.
OLD_BLOCK = """\
            turkey_lag_max,
            suppressed
        FROM price_intelligence_signals
        WHERE signal_date >= NOW() - INTERVAL '7 days'
          AND suppressed = FALSE
"""

NEW_BLOCK = """\
            turkey_lag_max,
            suppressed
        FROM v_active_signals
"""

src = SERVER.read_text(encoding="utf-8")

# Idempotency check: if already switched, nothing to do
already_switched = (
    "FROM v_active_signals\n"
    "        ORDER BY"
) in src.replace("\n", "\n").replace("    ", "    ")  # normalize a bit

if "FROM v_active_signals" in src:
    print("[skip] feed endpoint already switched to v_active_signals")
    sys.exit(0)

count = src.count(OLD_BLOCK)
if count == 0:
    print("[X] Could not find the expected feed-endpoint block to swap.")
    print("    The endpoint code may have been edited. Showing what was searched for:")
    print()
    print(repr(OLD_BLOCK))
    print()
    print("Manually edit dashboard/server.py around line 531:")
    print("  - Change `FROM price_intelligence_signals` to `FROM v_active_signals`")
    print("  - Remove the `WHERE signal_date >= NOW() - INTERVAL '7 days'`")
    print("    AND `AND suppressed = FALSE` lines (the view already filters)")
    sys.exit(1)
elif count > 1:
    print(f"[X] Expected exactly 1 match, found {count}. Aborting.")
    sys.exit(1)

src = src.replace(OLD_BLOCK, NEW_BLOCK)
SERVER.write_text(src, encoding="utf-8")
print("[OK] feed endpoint switched: FROM price_intelligence_signals -> FROM v_active_signals")
print("     WHERE filters removed (already applied in view definition)")
print()
print("Restart uvicorn (Ctrl+C, then re-run uvicorn command), then verify:")
print()
print("  Invoke-RestMethod http://localhost:8000/api/price_intelligence_signals |"
      " Measure-Object | Select Count")
print()
print("Expected ~9 rows (down from 30+).")
