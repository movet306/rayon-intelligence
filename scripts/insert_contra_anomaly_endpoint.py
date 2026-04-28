"""
Adds the /api/internal/contra-anomaly endpoint to dashboard/server.py.

Inserts BEFORE the "Serve static files" comment block (i.e. inside the
OPERATIONS INTELLIGENCE section, after the existing top-customers endpoint).

Idempotent: if endpoint marker already present, exits without changes.

Usage:
    python scripts/insert_contra_anomaly_endpoint.py
"""
from pathlib import Path
import sys

SERVER = Path("dashboard/server.py")
ENDPOINT_MARKER = "/api/internal/contra-anomaly"
MOUNT_NEEDLE = 'app.mount("/", StaticFiles'

ENDPOINT_BLOCK = '''
# ── /api/internal/contra-anomaly ───────────────────────────────────────────
# Single-row alert card. Surfaces contra revenue as a separate anomaly signal
# (median-based context, top counterparty concentration, severity flag) instead
# of an unreliable YoY % from a low-base prior month.

@app.get("/api/internal/contra-anomaly")
def internal_contra_anomaly():
    row = _one("""
        SELECT
            month_label,
            to_char(month_date, 'YYYY-MM-DD')        AS month_date,
            total_contra_tl::float                   AS total_contra_tl,
            alis_contra_tl::float                    AS alis_contra_tl,
            satis_contra_tl::float                   AS satis_contra_tl,
            returns_tl::float                        AS returns_tl,
            discounts_tl::float                      AS discounts_tl,
            gross_revenue_tl::float                  AS gross_revenue_tl,
            contra_pct_of_gross::float               AS contra_pct_of_gross,
            median_24m_pct::float                    AS median_24m_pct,
            mean_24m_pct::float                      AS mean_24m_pct,
            min_24m_pct::float                       AS min_24m_pct,
            max_24m_pct::float                       AS max_24m_pct,
            history_sample_months                    AS history_sample_months,
            ratio_to_median::float                   AS ratio_to_median,
            top_counterparty_name,
            top_counterparty_source,
            top_counterparty_tl::float               AS top_counterparty_tl,
            top_counterparty_pct::float              AS top_counterparty_pct,
            severity
        FROM v_contra_anomaly_detail
    """)

    return {
        "anomaly":  row,
        "notes": {
            "method":     "Median-based anomaly detection over 24-month history. "
                          "Severity: high if ratio_to_median >= 2.5, elevated if >= 1.5, else normal.",
            "yoy_warning": "YoY % is intentionally NOT exposed for contra revenue. "
                           "Prior-year same month can be an outlier itself, making YoY misleading.",
            "yarn_resale": "Gross revenue used for contra% excludes yarn resale (subtype filter).",
        },
    }


'''


def main():
    if not SERVER.exists():
        print(f"ERROR: {SERVER} not found.")
        sys.exit(1)

    text = SERVER.read_text(encoding="utf-8")

    if ENDPOINT_MARKER in text:
        print("WARN: contra-anomaly endpoint already present. Aborting.")
        sys.exit(0)

    if MOUNT_NEEDLE not in text:
        print(f"ERROR: anchor `{MOUNT_NEEDLE}` not found.")
        sys.exit(1)

    # Find the StaticFiles mount line, then walk back over preceding comment lines
    idx_mount = text.index(MOUNT_NEEDLE)
    line_start = text.rfind("\n", 0, idx_mount) + 1

    cursor = line_start
    while True:
        prev_end = cursor - 1
        if prev_end <= 0:
            break
        prev_start = text.rfind("\n", 0, prev_end) + 1
        prev_line = text[prev_start:prev_end]
        if prev_line.strip().startswith("#"):
            cursor = prev_start
        else:
            break
    insertion_point = cursor

    # Backup
    backup = SERVER.with_suffix(".py.bak2")
    backup.write_text(text, encoding="utf-8")
    print(f"Backup written: {backup}")

    new_text = text[:insertion_point] + ENDPOINT_BLOCK.lstrip("\n") + "\n" + text[insertion_point:]
    SERVER.write_text(new_text, encoding="utf-8")
    print(f"Inserted contra-anomaly endpoint into {SERVER}")
    print(f"  Insertion at byte offset: {insertion_point}")
    print(f"  New file size: {len(new_text):,} bytes")


if __name__ == "__main__":
    main()
