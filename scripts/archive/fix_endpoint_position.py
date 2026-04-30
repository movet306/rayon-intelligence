"""
fix_endpoint_position.py - Move /api/price_intelligence_stats above StaticFiles mount.

The previous patch (pi_1_2_kpi_strip.py) appended the endpoint at the end of
server.py, but FastAPI's `app.mount("/", StaticFiles(..., html=True))` is a
catch-all that intercepts any request below it. Endpoints registered after
the mount never receive traffic — hence the 404 on /api/price_intelligence_stats
even though the route is defined.

This script relocates the endpoint block to immediately BEFORE the mount line,
preserving its content. It also bumps the cache buster on app.v5.js so the
browser fetches fresh JS.

Idempotent: re-running detects the relocation already happened and skips.
"""
from pathlib import Path
import re
import sys
import time

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "dashboard" / "server.py"
INDEX = REPO / "dashboard" / "static" / "index.html"

MOUNT_LINE = 'app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")'
ENDPOINT_HEADER = "# ── /api/price_intelligence_stats ──"

src = SERVER.read_text(encoding="utf-8")

# Find the endpoint block (header + decorator + def + body until next top-level
# definition or end of file). Simplest: find the header marker, take everything
# from there to end of file.
header_idx = src.find(ENDPOINT_HEADER)
if header_idx == -1:
    print("[X] Endpoint header not found. Did pi_1_2_kpi_strip.py run?")
    sys.exit(1)

mount_idx = src.find(MOUNT_LINE)
if mount_idx == -1:
    print("[X] StaticFiles mount line not found. server.py structure changed?")
    sys.exit(1)

# Already relocated: header is before mount
if header_idx < mount_idx:
    print("[skip] endpoint already positioned before StaticFiles mount")
else:
    # Extract the endpoint block: from header to end of file
    endpoint_block = src[header_idx:].rstrip() + "\n"
    # Remove it from its current location
    before_endpoint = src[:header_idx].rstrip() + "\n"

    # Insert it just before the mount line
    new_mount_idx = before_endpoint.find(MOUNT_LINE)
    if new_mount_idx == -1:
        print("[X] Mount line vanished after extraction — aborting.")
        sys.exit(1)

    # Insert two blank lines before mount, then endpoint, then mount continues
    new_src = (
        before_endpoint[:new_mount_idx].rstrip()
        + "\n\n\n"
        + endpoint_block.rstrip()
        + "\n\n\n"
        + before_endpoint[new_mount_idx:]
    )
    SERVER.write_text(new_src, encoding="utf-8")
    print("[OK]  server.py: endpoint relocated above StaticFiles mount")

# Bump cache buster on app.v5.js to force browser refresh after JS changes
html = INDEX.read_text(encoding="utf-8")
ts = int(time.time())
m = re.search(r'app\.v5\.js\?v=(\S+?)"', html)
if m:
    old_v = m.group(1)
    html = re.sub(r'app\.v5\.js\?v=\S+?"', f'app.v5.js?v={ts}"', html)
    INDEX.write_text(html, encoding="utf-8")
    print(f"[OK]  index.html: cache buster {old_v} -> {ts}")

print("\nDone. Restart uvicorn to load the relocated endpoint:")
print("  Ctrl+C in the uvicorn terminal, then:")
print("  python -m uvicorn dashboard.server:app --reload --port 8000")
print("\nVerify with:")
print("  Invoke-RestMethod http://localhost:8000/api/price_intelligence_stats | ConvertTo-Json")
