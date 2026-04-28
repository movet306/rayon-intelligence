"""
Inserts the M2 internal endpoints block into dashboard/server.py
just before the app.mount(...) line at the bottom.

Idempotent: if the marker is already present, prints a warning and exits.

Usage:
    python scripts/insert_m2_endpoints.py
"""
from pathlib import Path
import sys

SERVER = Path("dashboard/server.py")
BLOCK  = Path("scripts/internal_endpoints_block.py")

MARKER = "OPERATIONS INTELLIGENCE ENDPOINTS (M2)"
MOUNT_NEEDLE = 'app.mount("/", StaticFiles'


def main():
    if not SERVER.exists():
        print(f"ERROR: {SERVER} not found.")
        sys.exit(1)
    if not BLOCK.exists():
        print(f"ERROR: {BLOCK} not found.")
        sys.exit(1)

    server_text = SERVER.read_text(encoding="utf-8")

    if MARKER in server_text:
        print("WARN: M2 endpoints block already present. Aborting (no double-insert).")
        sys.exit(0)

    if MOUNT_NEEDLE not in server_text:
        print(f"ERROR: could not find anchor `{MOUNT_NEEDLE}` in server.py.")
        print("Cannot safely insert without the StaticFiles mount anchor.")
        sys.exit(1)

    block_text = BLOCK.read_text(encoding="utf-8")

    # Find the comment line that introduces the StaticFiles mount, if present
    # Pattern: line with "Serve static files" comment immediately before app.mount
    idx_mount = server_text.index(MOUNT_NEEDLE)
    # walk back to start of line
    line_start = server_text.rfind("\n", 0, idx_mount) + 1
    # also walk back over the preceding comment line if present
    # so the M2 block goes ABOVE the "Serve static files" comment block
    cursor = line_start
    while True:
        prev_line_end = cursor - 1  # the \n
        if prev_line_end <= 0:
            break
        prev_line_start = server_text.rfind("\n", 0, prev_line_end) + 1
        prev_line = server_text[prev_line_start:prev_line_end]
        if prev_line.strip().startswith("#"):
            cursor = prev_line_start
        else:
            break

    insertion_point = cursor

    new_text = (
        server_text[:insertion_point]
        + block_text.rstrip() + "\n\n\n"
        + server_text[insertion_point:]
    )

    # Write a backup first
    backup = SERVER.with_suffix(".py.bak")
    backup.write_text(server_text, encoding="utf-8")
    print(f"Backup written: {backup}")

    SERVER.write_text(new_text, encoding="utf-8")
    print(f"Inserted M2 endpoints block into {SERVER}")
    print(f"  Inserted at byte offset: {insertion_point}")
    print(f"  New file size: {len(new_text):,} bytes")


if __name__ == "__main__":
    main()
