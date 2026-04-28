"""
Patches .github/workflows/daily_scraper.yml to add the missing
build_price_metrics step.

Insertion point: after `Run ICE Cotton scraper` and before
`Run LLM analyzer`. This places the price-metrics ETL directly
after the raw price scrapers (sunsirs + ice_cotton) and before
any downstream consumer (build_price_signals, telegram_reporter)
that depends on price_metrics_daily.

Idempotent.

Usage:
    python scripts/add_build_price_metrics_step.py
"""
from pathlib import Path
import sys

WORKFLOW = Path(".github/workflows/daily_scraper.yml")

NEW_STEP = """      - name: Build price metrics daily
        run: python scrapers/build_price_metrics.py
"""

ANCHOR_BEFORE = """      - name: Run ICE Cotton scraper
        run: python scrapers/ice_cotton.py
"""

ANCHOR_AFTER = """      - name: Run LLM analyzer"""

MARKER = "build_price_metrics.py"


def main():
    if not WORKFLOW.exists():
        print(f"ERROR: {WORKFLOW} not found. Are you in the project root?")
        sys.exit(1)

    text = WORKFLOW.read_text(encoding="utf-8")

    if MARKER in text:
        print("Workflow already contains build_price_metrics step. Skipping.")
        return

    if ANCHOR_BEFORE not in text:
        print("ERROR: anchor `Run ICE Cotton scraper` not found.")
        print("The workflow file may have been edited. Aborting safely.")
        sys.exit(1)

    if ANCHOR_AFTER not in text:
        print("ERROR: anchor `Run LLM analyzer` not found.")
        sys.exit(1)

    # Backup
    bak = WORKFLOW.with_suffix(".yml.bak")
    bak.write_text(text, encoding="utf-8")
    print(f"Backup written: {bak}")

    new_text = text.replace(
        ANCHOR_BEFORE,
        ANCHOR_BEFORE + NEW_STEP,
        1,
    )

    WORKFLOW.write_text(new_text, encoding="utf-8")
    print(f"Inserted step into {WORKFLOW}")
    print(f"  Old size: {len(text)} bytes")
    print(f"  New size: {len(new_text)} bytes")
    print()
    print("Next steps:")
    print("  1. Verify the change:")
    print("     Get-Content .github\\workflows\\daily_scraper.yml")
    print("  2. Commit and push:")
    print("     git add .github/workflows/daily_scraper.yml")
    print("     git commit -m 'workflow: add build_price_metrics step (fixes Apr 20 stale data)'")
    print("     git push")
    print("  3. The next scheduled run (08:00 UTC = 11:00 Istanbul) will use the new pipeline.")
    print("     To run immediately: GitHub Actions UI -> Daily Scraper -> Run workflow")


if __name__ == "__main__":
    main()
