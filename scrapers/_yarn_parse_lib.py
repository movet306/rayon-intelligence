"""
_yarn_parse_lib.py — shared parse_row() logic used by seed and audit scripts.
Returns the same deterministic yarn_code for a given lkp_id + yarn_type.
"""
import json
import re

DENIER_PREMIUM_JSON = json.dumps({"micro": 1.12, "fine": 1.05, "medium": 1.0, "heavy": 0.96})
PES_LUSTER_JSON     = json.dumps({"FD": 1.03, "SD": 1.0, "BR": 0.98, "HT": 1.15, "FR": 1.20, "CD": 1.08})
PA66_LUSTER_JSON    = json.dumps({"HT": 1.18, "standard": 1.0})


def parse_row(lkp_id: int, yarn_type: str) -> dict:
    raw = yarn_type.upper()

    # Fiber
    if "NAYL.6.6" in raw or "NAYL.66" in raw or "NYL66" in raw:
        fiber_family, fiber_code, fiber_type_key = "polyamide", "PA66", "PA6.6"
    elif "NAYL.6" in raw:
        fiber_family, fiber_code, fiber_type_key = "polyamide", "PA6", "PA6"
    else:
        fiber_family, fiber_code, fiber_type_key = "polyester", "PES", "PES"

    is_ht       = bool(re.search(r"HT\d", raw) or re.search(r"\bHT\b", raw))
    is_dty      = "DTY" in raw or "TEXT" in raw
    is_kanalli  = "KANAL" in raw
    is_recycle  = "RECYCLE" in raw
    is_cationic = "KATYON" in raw
    is_ddb      = "DDB" in raw
    is_doubled  = bool(re.search(r"/\d+X2|\d+X2", raw))

    quality = None
    if re.search(r"S.PER B KAL|SUPER B", raw):
        quality = "SUPER_B"
    elif re.search(r"\bA KAL", raw):
        quality = "A"
    elif re.search(r"\bB KAL", raw):
        quality = "B"

    twist = None
    if is_doubled:
        twist = "X2"
    elif re.search(r"\bS\b.{0,5}B.K.M", raw):
        twist = "S"
    elif re.search(r"\bZ\b.{0,5}B.K.M", raw):
        twist = "Z"

    denier = filament_count = None
    m = re.search(r"HT(\d+)/(\d+)", raw)
    if m:
        denier, filament_count = int(m.group(1)), int(m.group(2))
    if denier is None:
        m = re.search(r"(\d+)D[/ ](\d+)F", raw)
        if m:
            denier, filament_count = int(m.group(1)), int(m.group(2))
    if denier is None:
        m = re.search(r"(\d{2,3})/(\d{2,3})", raw)
        if m:
            denier, filament_count = int(m.group(1)), int(m.group(2))

    if denier is None:           denier_class = None
    elif denier < 50:            denier_class = "micro"
    elif denier < 100:           denier_class = "fine"
    elif denier < 200:           denier_class = "medium"
    else:                        denier_class = "heavy"

    if is_ht:               luster = "HT"
    elif is_cationic:       luster = "CD"
    elif "YARI MAT" in raw: luster = "SD"
    elif is_ddb:            luster = "BR"
    elif is_dty:            luster = "FD"
    else:                   luster = "SD"

    color = None
    if   "EKRU" in raw or "ECRU" in raw:           color = "ECRU"
    elif re.search(r"S.YAH|SIYAH", raw):            color = "BLACK"
    elif re.search(r"LAC.VERT|LACIVERT", raw):      color = "NAVY"
    elif "KIRMIZI" in raw:                           color = "RED"
    elif re.search(r"ANTRAS.T|ANTRASIT", raw):      color = "ANTH"
    elif is_ddb:                                     color = "DDB"

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

    base_yarn_code = "_".join(parts)

    if is_ht:       filament_process = "ht"
    elif is_dty:    filament_process = "dty"
    else:           filament_process = "fdy"

    if fiber_family == "polyamide" and is_ht:
        material_form = "industrial_filament"
    elif is_dty:    material_form = "textured_filament"
    else:           material_form = "filament"

    if fiber_family == "polyester":
        primary_driver   = "polyester_fdy"
        secondary_driver = "pta"
        luster_json      = PES_LUSTER_JSON
    elif fiber_type_key == "PA6.6":
        primary_driver   = "pa66_chip"
        secondary_driver = "adipic_acid"
        luster_json      = PA66_LUSTER_JSON
    else:
        primary_driver   = "pa6_chip"
        secondary_driver = "polyamide_fdy"
        luster_json      = PA66_LUSTER_JSON

    recycle_factor = 1.05 if is_recycle else 1.0

    # Parse confidence: high if denier+filament found cleanly, low if not
    if denier and filament_count and not is_doubled:
        parse_confidence = "high"
    elif denier and filament_count:
        parse_confidence = "medium"
    else:
        parse_confidence = "low"

    return {
        "lkp_id":           lkp_id,
        "raw_yarn_type":    yarn_type,
        "base_yarn_code":   base_yarn_code,   # before _V2/_V3 dedup
        "fiber_family":     fiber_family,
        "filament_process": filament_process,
        "denier":           denier,
        "filament_count":   filament_count,
        "denier_class":     denier_class,
        "luster":           luster,
        "recycle_flag":     is_recycle,
        "primary_driver":   primary_driver,
        "secondary_driver": secondary_driver,
        "luster_json":      luster_json,
        "recycle_factor":   recycle_factor,
        "parse_confidence": parse_confidence,
        "color":            color,
        "is_ht":            is_ht,
        "is_kanalli":       is_kanalli,
        "is_dty":           is_dty,
    }


def build_code_map(rows):
    """Given list of (id, yarn_type) dicts, return list with resolved yarn_code (incl. _V2/_V3)."""
    code_seen = {}
    result = []
    for row in rows:
        p = parse_row(row["id"], row["yarn_type"])
        base = p["base_yarn_code"]
        if base in code_seen:
            code_seen[base] += 1
            p["yarn_code"] = f"{base}_V{code_seen[base]}"
        else:
            code_seen[base] = 1
            p["yarn_code"] = base
        result.append(p)
    return result
