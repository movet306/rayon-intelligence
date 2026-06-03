"""
yarn_consolidate.py — Upgrade Yarn Master from validated draft to canonical spec model.

Fixes applied (no new features):
  A) Consolidate duplicate specs: keep lowest yarn_id as canonical, move
     aliases to dim_yarn_label_alias, delete alias rows from dim_yarn_master.
  B) Mark PA66 (row 29 — NYL66 IPLIK, no spec data) as placeholder.
  C) Fix PES DTY driver: polyester_fdy -> polyester_dty / polyester_poy.
  D) Verify: no _V2/_V3 remain, alias table populated, no orphaned drivers.
"""
import os
from collections import defaultdict

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ.get("RAYON_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("Set RAYON_DATABASE_URL in environment or .env")


def main():
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    wcur = conn.cursor()   # plain cursor for writes

    # ── Load all dim_yarn_master rows ─────────────────────────────────────────
    cur.execute("""
        SELECT yarn_id, yarn_code, fiber_family, filament_process,
               denier, filament_count, luster, recycle_flag,
               raw_yarn_label, source_row_id, parse_confidence
        FROM dim_yarn_master
        ORDER BY yarn_id
    """)
    all_rows = cur.fetchall()
    before_count = len(all_rows)
    print(f"Canonical specs before : {before_count}")

    # ── A) Group by technical spec key ────────────────────────────────────────
    # Group key: (fiber_family, filament_process, denier, filament_count, luster, recycle_flag)
    # Within each group keep lowest yarn_id as canonical.
    groups = defaultdict(list)
    for row in all_rows:
        key = (
            row["fiber_family"],
            row["filament_process"],
            row["denier"],           # None-safe: two NULLs group together
            row["filament_count"],
            row["luster"],
            row["recycle_flag"],
        )
        groups[key].append(row)

    aliases_moved    = 0
    aliases_detail   = []   # for the report

    for key, members in groups.items():
        if len(members) == 1:
            continue  # no duplicates in this group

        # Sort by yarn_id ascending: first is canonical
        members.sort(key=lambda r: r["yarn_id"])
        canonical = members[0]
        aliases   = members[1:]

        for alias in aliases:
            # B-i) Insert alias label into dim_yarn_label_alias
            wcur.execute("""
                INSERT INTO dim_yarn_label_alias
                    (yarn_id, raw_label, source_table, source_row_id, alias_type, notes)
                VALUES (%s, %s, 'lkp_yarn_taxonomy', %s, 'duplicate_spec', %s)
            """, (
                canonical["yarn_id"],
                alias["raw_yarn_label"] or alias["yarn_code"],
                alias["source_row_id"],
                f"Consolidated from {alias['yarn_code']} into {canonical['yarn_code']}",
            ))

            aliases_detail.append({
                "alias_code":     alias["yarn_code"],
                "canonical_code": canonical["yarn_code"],
                "raw_label":      alias["raw_yarn_label"] or "",
            })

            # B-ii) Delete the alias's price_driver row (canonical keeps its own)
            wcur.execute(
                "DELETE FROM dim_yarn_price_driver WHERE yarn_id = %s",
                (alias["yarn_id"],)
            )

            # B-iii) Delete alias from dim_yarn_master
            wcur.execute(
                "DELETE FROM dim_yarn_master WHERE yarn_id = %s",
                (alias["yarn_id"],)
            )

            aliases_moved += 1

    conn.commit()
    print(f"Aliases moved         : {aliases_moved}")

    # ── Alias detail ──────────────────────────────────────────────────────────
    if aliases_detail:
        print()
        print("  Alias consolidations:")
        for a in aliases_detail:
            print(f"    {a['alias_code']:<42} -> {a['canonical_code']}")

    # ── D) Mark PA66 as placeholder ───────────────────────────────────────────
    wcur.execute("""
        UPDATE dim_yarn_master SET
            is_placeholder          = TRUE,
            pricing_eligible        = FALSE,
            manual_review_required  = TRUE,
            notes = 'Unresolved: raw label NYL66 IPLIK, no denier/filament data available. Manual review required.'
        WHERE yarn_code = 'PA66'
    """)
    placeholder_count = wcur.rowcount
    conn.commit()

    # ── E) Fix PES DTY primary driver ─────────────────────────────────────────
    # PES_75D_72F_DTY_ECRU_RECYCLE: polyester_fdy -> polyester_dty
    wcur.execute("""
        UPDATE dim_yarn_price_driver yd
        SET primary_driver_slug   = 'polyester_dty',
            secondary_driver_slug = 'polyester_poy',
            notes = 'DTY process: primary driver corrected from polyester_fdy to polyester_dty'
        WHERE yd.yarn_id IN (
            SELECT yarn_id FROM dim_yarn_master
            WHERE filament_process = 'dty' AND fiber_family = 'polyester'
        )
    """)
    dty_fixed = wcur.rowcount
    conn.commit()

    # ── C) Verification queries ───────────────────────────────────────────────
    print()
    print("=== Verification ===")

    cur.execute("SELECT COUNT(*) AS n FROM dim_yarn_master")
    after_count = cur.fetchone()["n"]
    print(f"Canonical specs after  : {after_count}")

    cur.execute("SELECT yarn_code FROM dim_yarn_master WHERE yarn_code LIKE '%_V2%' OR yarn_code LIKE '%_V3%'")
    v_rows = cur.fetchall()
    print(f"_V2/_V3 remaining      : {len(v_rows)}")
    if v_rows:
        for r in v_rows:
            print(f"  WARNING: {r['yarn_code']}")

    cur.execute("SELECT COUNT(*) AS n FROM dim_yarn_label_alias")
    alias_count = cur.fetchone()["n"]
    print(f"dim_yarn_label_alias   : {alias_count} rows")

    # Orphaned drivers (yarn_id not in dim_yarn_master)
    cur.execute("""
        SELECT COUNT(*) AS n FROM dim_yarn_price_driver yd
        LEFT JOIN dim_yarn_master ym ON ym.yarn_id = yd.yarn_id
        WHERE ym.yarn_id IS NULL
    """)
    orphans = cur.fetchone()["n"]
    print(f"Orphaned driver rows   : {orphans}")

    cur.execute("""
        SELECT yarn_code, is_placeholder, pricing_eligible
        FROM dim_yarn_master WHERE is_placeholder = TRUE
    """)
    placeholders = cur.fetchall()
    print(f"Placeholders           : {len(placeholders)}")
    for p in placeholders:
        print(f"  {p['yarn_code']}  is_placeholder={p['is_placeholder']}  pricing_eligible={p['pricing_eligible']}")

    # DTY driver verification
    cur.execute("""
        SELECT ym.yarn_code, yd.primary_driver_slug, yd.secondary_driver_slug
        FROM dim_yarn_master ym
        JOIN dim_yarn_price_driver yd ON yd.yarn_id = ym.yarn_id
        WHERE ym.filament_process = 'dty' AND ym.fiber_family = 'polyester'
    """)
    dty_rows = cur.fetchall()
    dty_ok = all(r["primary_driver_slug"] == "polyester_dty" for r in dty_rows)
    print(f"DTY driver fixed       : {'yes' if dty_ok else 'FAIL'}")
    for r in dty_rows:
        print(f"  {r['yarn_code']}: {r['primary_driver_slug']} / {r['secondary_driver_slug']}")

    # Final breakdown by fiber
    print()
    print("=== Final dim_yarn_master by fiber family ===")
    cur.execute("""
        SELECT fiber_family, filament_process, COUNT(*) AS n,
               SUM(CASE WHEN is_placeholder THEN 1 ELSE 0 END) AS placeholders,
               SUM(CASE WHEN NOT pricing_eligible THEN 1 ELSE 0 END) AS ineligible
        FROM dim_yarn_master
        GROUP BY fiber_family, filament_process
        ORDER BY fiber_family, filament_process
    """)
    for r in cur.fetchall():
        print(f"  {r['fiber_family']:<12} {r['filament_process']:<8} : {r['n']:>3} specs"
              f"  (placeholders={r['placeholders']}, ineligible={r['ineligible']})")

    # ── Consolidation report ───────────────────────────────────────────────────
    print()
    print("=" * 50)
    print("=== Yarn Master Consolidation Report ===")
    print("=" * 50)
    print(f"Canonical specs before : {before_count}")
    print(f"Aliases moved          : {aliases_moved}")
    print(f"Canonical specs after  : {after_count}")
    print(f"Placeholders           : {placeholder_count}")
    print(f"dim_yarn_label_alias   : {alias_count} rows")
    print(f"DTY driver fixed       : {'yes' if dty_ok else 'FAIL'}")
    print(f"_V2/_V3 remaining      : {len(v_rows)}")
    print(f"Orphaned driver rows   : {orphans}")

    conn.close()


if __name__ == "__main__":
    main()
