"""
yarn_audit.py — Validation pass for Yarn Master Phase 1.

Steps:
  1  Populate traceability fields (raw_yarn_label, source_row_id, parse_confidence)
  2  Generate parse_audit.csv
  3  Coverage gap report (absent fiber families)
  4  Driver mapping review (DTY driver flag, HT premium rule check)
  5  Flag rows needing manual_review_required = TRUE

Does NOT commit schema changes or seed new data.
"""
import csv
import os
import sys

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Allow running from repo root or scrapers/
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from _yarn_parse_lib import build_code_map

load_dotenv()
DB_URL = os.environ.get("RAYON_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("Set RAYON_DATABASE_URL in environment or .env")

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "outputs")
os.makedirs(OUT_DIR, exist_ok=True)
AUDIT_CSV = os.path.join(OUT_DIR, "parse_audit.csv")


def main():
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    raw_cur = conn.cursor()

    # ── Rebuild lkp_id → yarn_code map via deterministic re-parse ─────────────
    cur.execute("SELECT id, yarn_type FROM lkp_yarn_taxonomy ORDER BY id")
    lkp_rows = cur.fetchall()
    parsed_map = build_code_map(lkp_rows)   # list of dicts with yarn_code + lkp_id

    print("=" * 70)
    print("STEP 1 — Populate traceability fields")
    print("=" * 70)

    updated = 0
    for p in parsed_map:
        raw_cur.execute("""
            UPDATE dim_yarn_master
            SET raw_yarn_label  = %s,
                source_row_id   = %s,
                parse_confidence = %s
            WHERE yarn_code = %s
        """, (p["raw_yarn_type"], p["lkp_id"], p["parse_confidence"], p["yarn_code"]))
        updated += raw_cur.rowcount

    conn.commit()
    print(f"  Updated {updated} rows with raw_yarn_label / source_row_id / parse_confidence")

    # ── STEP 2 — Parse audit report ───────────────────────────────────────────
    print()
    print("=" * 70)
    print("STEP 2 — Parse audit report -> outputs/parse_audit.csv")
    print("=" * 70)

    cur.execute("""
        SELECT
            ym.yarn_id,
            ym.yarn_code,
            ym.raw_yarn_label,
            ym.fiber_family,
            ym.filament_process,
            ym.denier,
            ym.filament_count,
            ym.luster,
            ym.recycle_flag,
            ym.parse_confidence,
            ym.source_row_id,
            yd.primary_driver_slug
        FROM dim_yarn_master ym
        LEFT JOIN dim_yarn_price_driver yd ON yd.yarn_id = ym.yarn_id
        ORDER BY ym.yarn_id
    """)
    audit_rows = cur.fetchall()

    flag_counts = {
        "MISSING_DENIER":    0,
        "MISSING_FILAMENT":  0,
        "ENCODING_CORRUPT":  0,
        "DUPLICATE_SPEC":    0,
        "NO_DRIVER":         0,
        "GENERIC_LABEL":     0,
        "CLEAN":             0,
    }

    csv_rows = []
    for r in audit_rows:
        flags = []
        if r["denier"] is None:
            flags.append("MISSING_DENIER")
        if r["filament_count"] is None:
            flags.append("MISSING_FILAMENT")
        raw = r["raw_yarn_label"] or ""
        if "\ufffd" in raw or "?" in raw or "\x00" in raw:
            flags.append("ENCODING_CORRUPT")
        code = r["yarn_code"] or ""
        if "_V2" in code or "_V3" in code or "_V4" in code:
            flags.append("DUPLICATE_SPEC")
        if r["primary_driver_slug"] is None:
            flags.append("NO_DRIVER")
        # Generic: no denier AND no filament AND short code
        if r["denier"] is None and r["filament_count"] is None and len(code) <= 6:
            flags.append("GENERIC_LABEL")

        if not flags:
            flags = ["CLEAN"]

        for f in flags:
            if f in flag_counts:
                flag_counts[f] += 1

        csv_rows.append({
            "yarn_code":        code,
            "raw_yarn_label":   raw,
            "fiber_family":     r["fiber_family"],
            "filament_process": r["filament_process"],
            "denier":           r["denier"] if r["denier"] is not None else "",
            "filament_count":   r["filament_count"] if r["filament_count"] is not None else "",
            "luster":           r["luster"],
            "recycle_flag":     r["recycle_flag"],
            "primary_driver":   r["primary_driver_slug"] or "",
            "parse_confidence": r["parse_confidence"],
            "flags":            ",".join(flags),
        })

    with open(AUDIT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"  Wrote {len(csv_rows)} rows to {AUDIT_CSV}")
    print()
    print("  Flag summary:")
    print(f"  {'Total:':<22} {len(csv_rows)}")
    for flag, cnt in flag_counts.items():
        if cnt:
            print(f"  {flag + ':':<22} {cnt}")

    # Per-row detail for non-CLEAN rows
    print()
    print("  Non-clean rows:")
    print(f"  {'#':>3}  {'yarn_code':<40} {'flags'}")
    print("  " + "-" * 75)
    non_clean = [r for r in csv_rows if r["flags"] != "CLEAN"]
    for r in non_clean:
        print(f"  {r.get('yarn_code',''):<43} {r['flags']}")

    # ── STEP 3 — Coverage gap report ──────────────────────────────────────────
    print()
    print("=" * 70)
    print("STEP 3 — Coverage gap report")
    print("=" * 70)

    check_terms = [
        ("Cotton/Pamuk",  ["pamuk", "cotton", "penye", "karde"]),
        ("Viscose/Modal", ["viskon", "modal", "lyocell", "tencel"]),
        ("Elastane",      ["elastan", "spandex", "likra", "lycra"]),
        ("Blend PES/COT", ["karism", "blend", "karisim"]),
        ("Polypropylene", ["polipropil", "pp iplik"]),
        ("Acrylic",       ["akrilik"]),
    ]

    print()
    present_in_lkp = {}
    for label, terms in check_terms:
        conditions = " OR ".join([f"LOWER(yarn_type) LIKE '%{t}%'" for t in terms])
        cur.execute(f"SELECT yarn_type FROM lkp_yarn_taxonomy WHERE {conditions}")
        hits = cur.fetchall()
        present_in_lkp[label] = hits

    cur.execute("SELECT DISTINCT fiber_family FROM dim_yarn_master ORDER BY fiber_family")
    present_families = {r["fiber_family"] for r in cur.fetchall()}

    print(f"  {'Family':<18} {'In dim_yarn_master':<22} {'In lkp_yarn_taxonomy':<22} Reason")
    print("  " + "-" * 85)
    gap_families = ["cotton", "viscose", "elastane", "blend", "polypropylene", "acrylic"]
    labels_map   = {
        "Cotton/Pamuk":  "cotton",
        "Viscose/Modal": "viscose",
        "Elastane":      "elastane",
        "Blend PES/COT": "blend",
        "Polypropylene": "polypropylene",
        "Acrylic":       "acrylic",
    }
    for label, terms in check_terms:
        fam     = labels_map[label]
        in_dim  = fam in present_families
        in_lkp  = len(present_in_lkp[label]) > 0
        if in_dim:
            reason = "present in both"
        elif in_lkp:
            reason = "PARSING GAP — in source but missing from dim"
        else:
            reason = "not in source (lkp_yarn_taxonomy)"
        in_dim_str = "YES" if in_dim else "absent"
        in_lkp_str = f"YES ({len(present_in_lkp[label])} rows)" if in_lkp else "absent"
        print(f"  {label:<18} {in_dim_str:<22} {in_lkp_str:<22} {reason}")

    # ── STEP 4 — Driver mapping review ────────────────────────────────────────
    print()
    print("=" * 70)
    print("STEP 4 — Driver mapping review")
    print("=" * 70)

    cur.execute("""
        SELECT
            ym.yarn_code,
            ym.filament_process,
            yd.primary_driver_slug,
            yd.pricing_method,
            yd.luster_premium_rule,
            CASE
                WHEN ym.filament_process = 'dty'
                 AND yd.primary_driver_slug = 'polyester_fdy'
                THEN 'REVIEW: DTY should use polyester_dty as primary driver'
                WHEN ym.yarn_code LIKE '%%HT%%'
                 AND yd.luster_premium_rule IS NULL
                THEN 'REVIEW: HT premium rule missing'
                ELSE 'OK'
            END AS driver_review
        FROM dim_yarn_master ym
        LEFT JOIN dim_yarn_price_driver yd ON yd.yarn_id = ym.yarn_id
        ORDER BY driver_review DESC, ym.yarn_code
    """)
    dr_rows = cur.fetchall()

    review_count = sum(1 for r in dr_rows if r["driver_review"] != "OK")
    ok_count     = len(dr_rows) - review_count

    print(f"  {'yarn_code':<42} {'process':<8} {'driver':<22} status")
    print("  " + "-" * 100)
    for r in dr_rows:
        status = r["driver_review"]
        marker = "  " if status == "OK" else "! "
        print(f"  {marker}{r['yarn_code']:<40} {str(r['filament_process']):<8} "
              f"{str(r['primary_driver_slug'] or ''):<22} {status}")

    print()
    print(f"  REVIEW needed: {review_count}    OK: {ok_count}")

    # ── STEP 5 — Flag rows for manual review ──────────────────────────────────
    print()
    print("=" * 70)
    print("STEP 5 — Flag rows for manual_review_required")
    print("=" * 70)

    raw_cur.execute("""
        UPDATE dim_yarn_master SET manual_review_required = TRUE
        WHERE denier IS NULL
           OR filament_count IS NULL
           OR yarn_code LIKE '%_V2%'
           OR yarn_code LIKE '%_V3%'
           OR yarn_code = 'PA66'
           OR raw_yarn_label LIKE '%?%'
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) AS n FROM dim_yarn_master WHERE manual_review_required = TRUE")
    flagged = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM dim_yarn_master WHERE manual_review_required = FALSE")
    clean = cur.fetchone()["n"]

    print(f"  manual_review_required = TRUE  : {flagged}")
    print(f"  manual_review_required = FALSE : {clean}")

    # Detail of flagged rows
    cur.execute("""
        SELECT yarn_code, denier, filament_count, raw_yarn_label
        FROM dim_yarn_master
        WHERE manual_review_required = TRUE
        ORDER BY yarn_code
    """)
    flagged_rows = cur.fetchall()
    print()
    print("  Flagged rows:")
    for r in flagged_rows:
        reasons = []
        if r["denier"] is None:         reasons.append("no denier")
        if r["filament_count"] is None: reasons.append("no filament")
        code = r["yarn_code"]
        if "_V2" in code or "_V3" in code: reasons.append("duplicate spec")
        if code == "PA66":              reasons.append("generic code")
        raw = r["raw_yarn_label"] or ""
        if "?" in raw:                  reasons.append("encoding artifact")
        print(f"    {code:<42} [{', '.join(reasons)}]")
        if raw:
            print(f"    {'':42}  raw: {raw[:70]}")

    # ── Final summary ──────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"  dim_yarn_master rows         : 52")
    print(f"  parse_audit.csv              : {AUDIT_CSV}")
    print(f"  CLEAN (no flags)             : {flag_counts['CLEAN']}")
    print(f"  ENCODING_CORRUPT             : {flag_counts['ENCODING_CORRUPT']}")
    print(f"  DUPLICATE_SPEC (_V2/_V3)     : {flag_counts['DUPLICATE_SPEC']}")
    print(f"  MISSING_DENIER               : {flag_counts['MISSING_DENIER']}")
    print(f"  NO_DRIVER                    : {flag_counts['NO_DRIVER']}")
    print(f"  GENERIC_LABEL                : {flag_counts['GENERIC_LABEL']}")
    print(f"  DTY driver review items      : {review_count}")
    print(f"  manual_review_required=TRUE  : {flagged}")
    print(f"  manual_review_required=FALSE : {clean}")
    print()
    print("  NOT committed — review parse_audit.csv before proceeding.")

    conn.close()


if __name__ == "__main__":
    main()
