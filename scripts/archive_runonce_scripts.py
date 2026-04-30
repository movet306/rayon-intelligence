"""
archive_runonce_scripts.py - Move completed/run-once scripts to scripts/archive/.

Establishes the convention:
  scripts/             = reusable utilities, diagnostics, patch scripts
  scripts/archive/     = run-once scripts that have completed their job.
                         Kept for traceability, not for re-execution.

Idempotent: re-running detects already-archived files and skips.
"""
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
ARCHIVE = SCRIPTS / "archive"

# Run-once scripts to archive. Each is one of:
#   - a fix that has already been applied and the change is committed elsewhere
#   - a one-shot diagnostic for a past investigation
TO_ARCHIVE = [
    "check_contra_extended.py",   # Mar 2026 contra revenue spike investigation
    "check_db.py",                # ad-hoc table row count check
    "check_phase_b_infra.py",     # Phase B infra verification (one-time)
    "fix_detail_perf.py",         # Counterparty TRIM fix, applied in 438f6c6
    "fix_endpoint_position.py",   # PI-1.2 endpoint relocation, applied
]

ARCHIVE.mkdir(exist_ok=True)

# Add a README so the convention is visible
README = ARCHIVE / "README.md"
README_TEXT = """# scripts/archive

Run-once scripts that have completed their job. Kept here for traceability:
they document what was done, in what order, and why.

**Do not re-execute** scripts in this folder. They were designed for a specific
state of the codebase or database that no longer exists.

If you need similar functionality, copy and adapt — do not run from this folder.

## Convention

- `scripts/`          → reusable utilities, diagnostics, patch scripts
- `scripts/archive/`  → run-once scripts that have completed their job

When a script in `scripts/` is applied successfully and the resulting code
change is committed, move the script here.
"""
if not README.exists():
    README.write_text(README_TEXT, encoding="utf-8")
    print(f"[OK]  created {README.relative_to(REPO)}")
else:
    print(f"[skip] {README.relative_to(REPO)} already exists")

moved = 0
skipped = 0
missing = 0
for name in TO_ARCHIVE:
    src = SCRIPTS / name
    dst = ARCHIVE / name
    if dst.exists():
        # Already archived. If src also still exists, that's a duplicate -
        # remove the duplicate at scripts/ root.
        if src.exists():
            src.unlink()
            print(f"[OK]  removed duplicate at root: {name}")
            moved += 1
        else:
            print(f"[skip] {name} already archived")
            skipped += 1
        continue
    if not src.exists():
        print(f"[!]   {name} not found at scripts/ root, skipping")
        missing += 1
        continue
    shutil.move(str(src), str(dst))
    print(f"[OK]  archived {name}")
    moved += 1

print(f"\nMoved: {moved}, Already archived: {skipped}, Missing: {missing}")
print("\nNext: git status to verify, then commit.")
