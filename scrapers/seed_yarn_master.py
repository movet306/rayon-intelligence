"""
seed_yarn_master.py — Parse lkp_yarn_taxonomy and seed dim_yarn_master + dim_yarn_price_driver.

The lkp_yarn_taxonomy table only has id + yarn_type (raw Turkish strings with encoding
artifacts). This script parses each string to extract structured fields.
"""
import json
import re
import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:REDACTED_DB_PASSWORD@mainline.proxy.rlwy.net:56047/railway",
)

DENIER_PREMIUM_JSON = json.dumps({"micro": 1.12, "fine": 1.05, "medium": 1.0, "heavy": 0.96})
PES_LUSTER_JSON     = json.dumps({"FD": 1.03, "SD": 1.0, "BR": 0.98, "HT": 1.15, "FR": 1.20, "CD": 1.08})
PA66_LUSTER_JSON    = json.dumps({"HT": 1.18, "standard": 1.0})


def parse_row(lkp_id: int, yarn_type: str) -> dict:
    raw = yarn_type.upper()

    # ── Fiber ─────────────────────────────────────────────────────────────────
    if "NAYL.6.6" in raw or "NAYL.66" in raw or "NYL66" in raw:
        fiber_family, fiber_code, fiber_type_key = "polyamide", "PA66", "PA6.6"
    elif "NAYL.6" in raw:
        fiber_family, fiber_code, fiber_type_key = "polyamide", "PA6", "PA6"
    else:
        fiber_family, fiber_code, fiber_type_key = "polyester", "PES", "PES"

    # ── Boolean flags ─────────────────────────────────────────────────────────
    is_ht       = bool(re.search(r"HT\d", raw) or re.search(r"\bHT\b", raw))
    is_dty      = "DTY" in raw or "TEXT" in raw
    is_kanalli  = "KANAL" in raw
    is_recycle  = "RECYCLE" in raw
    is_cationic = "KATYON" in raw
    is_ddb      = "DDB" in raw
    is_doubled  = bool(re.search(r"/\d+X2|\d+X2", raw))

    # ── Quality grade (PA6.6 HT) ──────────────────────────────────────────────
    quality = None
    if re.search(r"S.PER B KAL|SUPER B", raw):
        quality = "SUPER_B"
    elif re.search(r"\bA KAL", raw):
        quality = "A"
    elif re.search(r"\bB KAL", raw):
        quality = "B"

    # ── Twist (PA6 DTY) ───────────────────────────────────────────────────────
    twist = None
    if is_doubled:
        twist = "X2"
    elif re.search(r"\bS\b.{0,5}B.K.M", raw):
        twist = "S"
    elif re.search(r"\bZ\b.{0,5}B.K.M", raw):
        twist = "Z"

    # ── Denier / filament ─────────────────────────────────────────────────────
    denier = filament_count = None

    m = re.search(r"HT(\d+)/(\d+)", raw)               # HT470/136
    if m:
        denier, filament_count = int(m.group(1)), int(m.group(2))

    if denier is None:
        m = re.search(r"(\d+)D[/ ](\d+)F", raw)        # 75D/72F
        if m:
            denier, filament_count = int(m.group(1)), int(m.group(2))

    if denier is None:
        m = re.search(r"(\d{2,3})/(\d{2,3})", raw)     # 75/72
        if m:
            denier, filament_count = int(m.group(1)), int(m.group(2))

    # Denier class
    if denier is None:      denier_class = None
    elif denier < 50:       denier_class = "micro"
    elif denier < 100:      denier_class = "fine"
    elif denier < 200:      denier_class = "medium"
    else:                   denier_class = "heavy"

    # ── Luster ────────────────────────────────────────────────────────────────
    if is_ht:               luster = "HT"
    elif is_cationic:       luster = "CD"
    elif "YARI MAT" in raw: luster = "SD"
    elif is_ddb:            luster = "BR"
    elif is_dty:            luster = "FD"
    else:                   luster = "SD"   # default PES FDY

    # ── Color (display / code suffix only) ────────────────────────────────────
    color = None
    if   "EKRU" in raw or "ECRU" in raw:           color = "ECRU"
    elif re.search(r"S.YAH|SIYAH", raw):            color = "BLACK"
    elif re.search(r"LAC.VERT|LACIVERT", raw):      color = "NAVY"
    elif "KIRMIZI" in raw:                           color = "RED"
    elif re.search(r"ANTRAS.T|ANTRASIT", raw):      color = "ANTH"
    elif is_ddb:                                     color = "DDB"

    # ── Build base yarn_code ──────────────────────────────────────────────────
    parts = [fiber_code]
    if denier:          parts.append(f"{denier}D")
    if filament_count:  parts.append(f"{filament_count}F")
    if is_ht:           parts.append("HT")
    if is_dty:          parts.append("DTY")
    if is_kanalli:      parts.append("KANALLI")
    if is_cationic:     parts.append("CATIONIC")
    if quality:         parts.append(quality)
    if twist:           parts.append(twist)
    if color:           parts.append(color)
    if is_recycle:      parts.append("RECYCLE")

    yarn_code = "_".join(parts)

    # ── Display name ──────────────────────────────────────────────────────────
    d_parts = [fiber_code]
    if denier and filament_count:
        d_parts.append(f"{denier}D/{filament_count}F")
    elif denier:
        d_parts.append(f"{denier}D")
    if luster not in ("SD",):
        d_parts.append(luster)
    if is_kanalli:   d_parts.append("Kanalı")
    if is_cationic:  d_parts.append("Cationic")
    if quality:      d_parts.append(f"Gr.{quality}")
    if twist:        d_parts.append(twist)
    if color:        d_parts.append(color.title())
    if is_recycle:   d_parts.append("GRS")
    display_name = " ".join(d_parts)

    # ── Process / form ────────────────────────────────────────────────────────
    if is_ht:       filament_process = "ht"
    elif is_dty:    filament_process = "dty"
    else:           filament_process = "fdy"

    if fiber_family == "polyamide" and is_ht:
        material_form = "industrial_filament"
    elif is_dty:    material_form = "textured_filament"
    else:           material_form = "filament"

    application = ["technical"] if is_ht else ["woven", "knit"]

    # ── Driver mapping ────────────────────────────────────────────────────────
    if fiber_family == "polyester":
        primary_driver   = "polyester_fdy"
        secondary_driver = "pta"
        luster_json      = PES_LUSTER_JSON
    elif fiber_type_key == "PA6.6":
        primary_driver   = "pa66_chip"
        secondary_driver = "adipic_acid"
        luster_json      = PA66_LUSTER_JSON
    else:  # PA6
        primary_driver   = "pa6_chip"
        secondary_driver = "polyamide_fdy"
        luster_json      = PA66_LUSTER_JSON

    recycle_factor = 1.05 if is_recycle else 1.0

    return {
        "lkp_id":           lkp_id,
        "yarn_code":        yarn_code,
        "display_name":     display_name,
        "fiber_family":     fiber_family,
        "material_form":    material_form,
        "filament_process": filament_process,
        "denier":           denier,
        "filament_count":   filament_count,
        "denier_class":     denier_class,
        "luster":           luster,
        "recycle_flag":     is_recycle,
        "application":      application,
        "primary_driver":   primary_driver,
        "secondary_driver": secondary_driver,
        "luster_json":      luster_json,
        "recycle_factor":   recycle_factor,
    }


def main():
    conn = psycopg2.connect(DB_URL)
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id, yarn_type FROM lkp_yarn_taxonomy ORDER BY id")
    rows = cur.fetchall()
    print(f"Read {len(rows)} rows from lkp_yarn_taxonomy")

    # ── Parse all rows, resolve duplicate yarn_codes ──────────────────────────
    parsed    = []
    code_seen = {}

    for row in rows:
        p = parse_row(row["id"], row["yarn_type"])
        base = p["yarn_code"]
        if base in code_seen:
            code_seen[base] += 1
            p["yarn_code"] = f"{base}_V{code_seen[base]}"
        else:
            code_seen[base] = 1
        parsed.append(p)

    # ── Preview ───────────────────────────────────────────────────────────────
    print()
    print(f"{'#':>3}  {'yarn_code':<40} {'family':<11} {'D/F':<10} {'lust':<4} {'proc':<4} {'driver'}")
    print("-" * 110)
    for p in parsed:
        df  = f"{p['denier'] or '?'}D/{p['filament_count'] or '?'}F"
        flg = "R" if p["recycle_flag"] else " "
        print(f"{p['lkp_id']:>3}  {p['yarn_code']:<40} {p['fiber_family']:<11} {df:<10} "
              f"{p['luster']:<4} {p['filament_process']:<4} {p['primary_driver']}{flg}")

    # ── Insert dim_yarn_master ────────────────────────────────────────────────
    print()
    print("Inserting into dim_yarn_master...")
    yarn_ids = {}   # yarn_code → yarn_id

    MASTER_SQL = """
        INSERT INTO dim_yarn_master
            (yarn_code, display_name, fiber_family, material_form,
             filament_process, denier, filament_count, denier_class,
             luster, recycle_flag, application, rayon_uses)
        VALUES
            (%(yarn_code)s, %(display_name)s, %(fiber_family)s, %(material_form)s,
             %(filament_process)s, %(denier)s, %(filament_count)s, %(denier_class)s,
             %(luster)s, %(recycle_flag)s, %(application)s, TRUE)
        ON CONFLICT (yarn_code) DO UPDATE SET
            display_name     = EXCLUDED.display_name,
            filament_process = EXCLUDED.filament_process,
            denier_class     = EXCLUDED.denier_class,
            luster           = EXCLUDED.luster
        RETURNING yarn_id, yarn_code
    """

    regular_cur = conn.cursor()
    for p in parsed:
        regular_cur.execute(MASTER_SQL, p)
        yarn_id, yarn_code = regular_cur.fetchone()
        yarn_ids[yarn_code] = yarn_id

    conn.commit()
    print(f"  {len(yarn_ids)} rows upserted into dim_yarn_master")

    # ── Insert dim_yarn_price_driver ──────────────────────────────────────────
    print("Inserting into dim_yarn_price_driver...")

    DRIVER_SQL = """
        INSERT INTO dim_yarn_price_driver
            (yarn_id, primary_driver_slug, secondary_driver_slug,
             blend_weight_primary, blend_weight_secondary,
             pricing_method, price_confidence,
             denier_premium_rule, luster_premium_rule, recycle_factor)
        VALUES
            (%(yarn_id)s, %(primary)s, %(secondary)s,
             1.0, 0.0,
             'driver_indexed', 'indicative',
             %(denier_prem)s, %(luster_prem)s, %(recycle_factor)s)
        ON CONFLICT DO NOTHING
    """

    driver_count = 0
    for p in parsed:
        yid = yarn_ids.get(p["yarn_code"])
        if yid is None:
            print(f"  WARN: no yarn_id for {p['yarn_code']}")
            continue
        regular_cur.execute(DRIVER_SQL, {
            "yarn_id":       yid,
            "primary":       p["primary_driver"],
            "secondary":     p["secondary_driver"],
            "denier_prem":   DENIER_PREMIUM_JSON,
            "luster_prem":   p["luster_json"],
            "recycle_factor":p["recycle_factor"],
        })
        driver_count += 1

    conn.commit()
    print(f"  {driver_count} rows upserted into dim_yarn_price_driver")

    # ── Step 4 verification ───────────────────────────────────────────────────
    cur.execute("""
        SELECT
            ym.yarn_code, ym.fiber_family, ym.denier, ym.filament_count,
            ym.luster, ym.recycle_flag,
            yd.primary_driver_slug, yd.price_confidence
        FROM dim_yarn_master ym
        LEFT JOIN dim_yarn_price_driver yd ON yd.yarn_id = ym.yarn_id
        ORDER BY ym.fiber_family, ym.denier NULLS LAST
    """)
    verify = cur.fetchall()

    print()
    print(f"{'yarn_code':<40} {'family':<11} {'D':>5}/{'F':<5} {'lust':<5} {'R':<2} {'driver':<20} {'conf'}")
    print("-" * 115)
    for r in verify:
        flag = "Y" if r["recycle_flag"] else " "
        print(f"{r['yarn_code']:<40} {r['fiber_family']:<11} "
              f"{str(r['denier'] or ''):>5}/{str(r['filament_count'] or ''):<5} "
              f"{str(r['luster'] or ''):<5} {flag:<2} "
              f"{str(r['primary_driver_slug'] or ''):<20} {str(r['price_confidence'] or '')}")

    cur.execute("SELECT COUNT(*) AS n FROM dim_yarn_master")
    nm = cur.fetchone()["n"]
    cur.execute("SELECT COUNT(*) AS n FROM dim_yarn_price_driver")
    nd = cur.fetchone()["n"]
    print()
    print(f"TOTAL: {nm} yarns in dim_yarn_master, {nd} driver mappings in dim_yarn_price_driver")

    conn.close()


if __name__ == "__main__":
    main()
