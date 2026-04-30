# scripts/archive

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
