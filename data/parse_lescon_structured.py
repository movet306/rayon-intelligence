"""
data/parse_lescon_structured.py

Reads raw CSVs + re-parses BIFF8 XLS worksheets to produce structured
transaction tables with one row per fabric delivery.

Schema discovered from binary inspection:

  DOKUMA (lescon usd.xls)
    Financial rows : col0=date_serial  col1=evrak_no  col4=kdv  col4=amount
    Product rows   : col1=price_str    col2=miktar    col3=unit_price
    Unit           : implied meters (MT) — no explicit unit column

  ORME (lescon örme usd hs.xls)
    Financial rows : col0=date_serial  col1=evrak_no  col5=kdv  col5=amount
    Product rows   : col1=price_str    col2='KG'      col3=miktar  col4=unit_price
    Unit           : KG (explicitly stored in col2)

Grouping rule: each product row inherits evrak_no + date from the immediately
preceding financial rows.  Multiple product rows can follow one evrak.

Output columns (both files):
  evrak_no, tarih, urun_aciklamasi, unit_price_usd, miktar_mt,
  fabric_type, source_file

Usage:
    python data/parse_lescon_structured.py
"""

import csv
import datetime
import os
import re
import struct
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")

INPUT_XLS = {
    "lescon_orme":   os.path.join(DOWNLOADS, "lescon    \u00f6rme usd hs.xls"),
    "lescon_dokuma": os.path.join(DOWNLOADS, "lescon    usd.xls"),
}

OUTPUT_DIR = Path(__file__).parent
OUTPUT_CSVS = {
    "lescon_orme":   OUTPUT_DIR / "lescon_orme_structured.csv",
    "lescon_dokuma": OUTPUT_DIR / "lescon_dokuma_structured.csv",
}

OUTPUT_COLS = [
    "evrak_no", "tarih", "urun_aciklamasi",
    "unit_price_usd", "miktar_mt", "fabric_type", "source_file",
]

# ---------------------------------------------------------------------------
# Pattern constants
# ---------------------------------------------------------------------------
EVRAK_RE = re.compile(r"Evrak\s+No\s*:\s*(\d+)", re.IGNORECASE)

# "3.70$+KDV /POLY.BISTRECH TAYLAN 2/2 DUZ BOYA"
# "0.60$+%20 KDV /FASON BOYAMA"
# "7$+KDV /SCUBA POLY.ELASTAN PIKE RAPORLU 100/96"
PRICE_PROD_RE = re.compile(
    r"^\s*([\d.]+)\s*\$.*?/\s*(.+)$", re.DOTALL
)

# Fabric-type keyword map — first match wins
FABRIC_KEYWORDS: list[tuple[str, re.Pattern]] = [
    ("interlok",   re.compile(r"INTERLOK",           re.I)),
    ("scuba",      re.compile(r"SCUBA",               re.I)),
    ("suprem",     re.compile(r"SUPREM",              re.I)),
    ("jakar",      re.compile(r"JAKAR",               re.I)),
    ("doubleface", re.compile(r"DOUBLEFACE",          re.I)),
    ("kaskorse",   re.compile(r"KASKORSE",            re.I)),
    ("file",       re.compile(r"\bFILE\b",            re.I)),
    ("bistrech",   re.compile(r"BISTRECH",            re.I)),
    ("saten",      re.compile(r"SATEN",               re.I)),
    ("down_proof", re.compile(r"DOWN.?PROOF",         re.I)),
    ("ottoman",    re.compile(r"OTTOMAN",             re.I)),
    ("pike",       re.compile(r"\bPIKE\b",            re.I)),
    ("fason",      re.compile(r"FASON",               re.I)),
    ("micro",      re.compile(r"\bMICRO\b",           re.I)),
    ("naylon",     re.compile(r"\bNAYL\b",            re.I)),
    ("polyester",  re.compile(r"\bPOLY\b",            re.I)),
]


# ---------------------------------------------------------------------------
# BIFF8 parsing helpers (no external dependencies)
# ---------------------------------------------------------------------------

def _iter_records(data: bytes, start: int = 512):
    """Yield (rec_type, payload_bytes, file_offset) for each BIFF8 record."""
    pos = start
    while pos + 4 <= len(data):
        rt, rl = struct.unpack_from("<HH", data, pos)
        if rl > 65535:
            break
        end = pos + 4 + rl
        if end > len(data):
            break
        yield rt, data[pos + 4 : end], pos
        pos = end


def _decode_rk(buf4: bytes) -> float:
    """Decode a 4-byte BIFF8 RK value into a Python float."""
    u = struct.unpack_from("<I", buf4)[0]
    s = struct.unpack_from("<i", buf4)[0]
    fX100 = u & 0x01
    fInt  = u & 0x02
    if fInt:
        val = float(s >> 2)
    else:
        val_bits = (u & 0xFFFFFFFC) << 32
        val = struct.unpack("<d", struct.pack("<Q", val_bits))[0]
    return val / 100.0 if fX100 else val


def _read_xl_str(buf: bytes, pos: int, boundaries: set) -> tuple[str, int]:
    """Parse one XLUnicodeString from buf[pos]; handle CONTINUE boundaries."""
    cch = struct.unpack_from("<H", buf, pos)[0]; pos += 2
    g   = buf[pos]; pos += 1
    hi  = g & 0x01
    ri  = (g >> 3) & 0x01
    ei  = (g >> 2) & 0x01
    cRun = 0
    if ri:
        cRun = struct.unpack_from("<H", buf, pos)[0]; pos += 2
    cbExt = 0
    if ei:
        cbExt = struct.unpack_from("<I", buf, pos)[0]; pos += 4
    chars: list[int] = []
    cur = hi
    for _ in range(cch):
        if pos in boundaries:
            cur = buf[pos] & 0x01; pos += 1
        if cur:
            chars.append(struct.unpack_from("<H", buf, pos)[0]); pos += 2
        else:
            chars.append(buf[pos]); pos += 1
    return "".join(chr(c) for c in chars), pos + 4 * cRun + cbExt


def _get_sst(data: bytes) -> list[str]:
    """Extract the Shared String Table from BIFF8 data."""
    REC_SST  = 0x00FC
    REC_CONT = 0x003C
    recs = list(_iter_records(data))
    for idx, (rt, pay, _) in enumerate(recs):
        if rt != REC_SST:
            continue
        uniq = struct.unpack_from("<I", pay, 4)[0]
        if uniq == 0 or uniq > 100_000:
            continue
        buf   = bytearray(pay)
        bnds: set[int] = set()
        for j in range(idx + 1, len(recs)):
            ct, cp, _ = recs[j]
            if ct != REC_CONT:
                break
            bnds.add(len(buf))
            buf.extend(cp)
        buf   = bytes(buf)
        sp    = 8       # skip cstTotal (4) + cstUnique (4)
        strs: list[str] = []
        for _ in range(uniq):
            if sp >= len(buf):
                break
            try:
                s, sp = _read_xl_str(buf, sp, bnds)
                strs.append(s)
            except (IndexError, struct.error):
                break
        return strs
    return []


def _excel_date(serial: float) -> datetime.date:
    """Convert Excel 1900-system date serial to a datetime.date."""
    n = int(serial)
    if n > 59:          # correct for Excel's phantom Feb-29-1900
        n -= 1
    return datetime.date(1899, 12, 31) + datetime.timedelta(days=n)


def get_worksheet_cells(
    data: bytes,
) -> dict[int, dict[int, object]]:
    """
    Parse the first worksheet from BIFF8 data.
    Returns {row_num: {col_num: value}}, where value is str or float.
    """
    REC_BOF      = 0x0809
    REC_EOF      = 0x000A
    REC_LABELSST = 0x00FD
    REC_NUMBER   = 0x0203
    REC_RK       = 0x027E
    REC_MULRK    = 0x00BD

    sst = _get_sst(data)

    # Find the second BOF (first worksheet)
    bof_count = 0
    ws_start  = 512
    for rt, pay, pos in _iter_records(data):
        if rt == REC_BOF:
            bof_count += 1
            if bof_count == 2:
                ws_start = pos
                break

    cells: dict[int, dict[int, object]] = {}

    for rt, pay, _ in _iter_records(data, ws_start):
        if rt == REC_EOF:
            break

        if rt == REC_LABELSST and len(pay) >= 10:
            r, c = struct.unpack_from("<HH", pay)
            isst = struct.unpack_from("<I", pay, 6)[0]
            val  = sst[isst] if isst < len(sst) else f"SST[{isst}]"
            cells.setdefault(r, {})[c] = val

        elif rt == REC_NUMBER and len(pay) >= 14:
            r, c = struct.unpack_from("<HH", pay)
            val  = struct.unpack_from("<d", pay, 6)[0]
            cells.setdefault(r, {})[c] = val

        elif rt == REC_RK and len(pay) >= 10:
            r, c = struct.unpack_from("<HH", pay)
            val  = _decode_rk(pay[6:10])
            cells.setdefault(r, {})[c] = val

        elif rt == REC_MULRK:
            r, cf = struct.unpack_from("<HH", pay)
            n     = (len(pay) - 6) // 6
            for i in range(n):
                val = _decode_rk(pay[4 + i * 6 + 2 : 4 + i * 6 + 6])
                cells.setdefault(r, {})[cf + i] = val

    return cells


# ---------------------------------------------------------------------------
# Schema detection
# ---------------------------------------------------------------------------

def detect_schema(cells: dict[int, dict[int, object]]) -> tuple[int, int]:
    """
    Auto-detect miktar_col and price_col from the first product row.

    DOKUMA: col1=price_str  col2=float(miktar)  col3=float(price)  → (2, 3)
    ORME:   col1=price_str  col2=str('KG')       col3=float(miktar)  col4=float(price) → (3, 4)
    """
    for rnum in sorted(cells):
        row = cells[rnum]
        v1  = row.get(1)
        if not isinstance(v1, str):
            continue
        if "$" not in v1 or "/" not in v1:
            continue
        v2 = row.get(2)
        if isinstance(v2, str):          # col2 is unit label ('KG') → ORME
            return 3, 4
        elif isinstance(v2, float):      # col2 is numeric → DOKUMA
            return 2, 3
    return 2, 3                          # fallback


# ---------------------------------------------------------------------------
# Product description helpers
# ---------------------------------------------------------------------------

def parse_price_product(text: str) -> tuple[float | None, str]:
    """
    Parse '3.70$+KDV /POLY.BISTRECH TAYLAN 2/2 DUZ BOYA'
    into (3.70, 'POLY.BISTRECH TAYLAN 2/2 DUZ BOYA').

    Returns (None, text) on parse failure.
    """
    m = PRICE_PROD_RE.match(text)
    if not m:
        return None, text.strip()
    try:
        price = float(m.group(1))
    except ValueError:
        price = None
    urun = m.group(2).strip()
    return price, urun


def classify_fabric(urun: str) -> str:
    """Return a coarse fabric-type label from the product description."""
    for label, pattern in FABRIC_KEYWORDS:
        if pattern.search(urun):
            return label
    return "other"


# ---------------------------------------------------------------------------
# Transaction grouping
# ---------------------------------------------------------------------------

def group_transactions(
    cells: dict[int, dict[int, object]],
    miktar_col: int,
    price_col: int,
    source_label: str,
) -> list[dict]:
    """
    Walk worksheet rows in order and reconstruct one transaction dict per
    product row, inheriting evrak_no + date from the preceding financial rows.
    """
    current_evrak: str | None = None
    current_date:  str | None = None
    transactions: list[dict] = []

    for rnum in sorted(cells):
        row  = cells[rnum]
        col0 = row.get(0)
        col1 = row.get(1)

        # ── Financial row: date in col0, evrak_no in col1 ──────────────────
        is_date = isinstance(col0, float) and 40_000 < col0 < 60_000
        is_evrak = isinstance(col1, str) and EVRAK_RE.match(col1)

        if is_date and is_evrak:
            m       = EVRAK_RE.match(col1)
            new_evr = m.group(1)
            new_dt  = _excel_date(col0).isoformat()
            # The same evrak appears twice (KDV row + main amount row).
            # Only update when we see a genuinely different evrak number.
            if new_evr != current_evrak:
                current_evrak = new_evr
                current_date  = new_dt
            continue

        # ── Product row: price string in col1, miktar numeric ──────────────
        if isinstance(col1, str) and "$" in col1 and "/" in col1:
            price_from_str, urun = parse_price_product(col1)
            if not urun:
                continue

            miktar_val = row.get(miktar_col)
            price_val  = row.get(price_col, price_from_str)

            # Use string-parsed price as fallback for missing/zero numeric cell
            if price_val is None or price_val == 0.0:
                price_val = price_from_str
            # Take abs of price (returns have negative prices but same product)
            if isinstance(price_val, float):
                price_val = abs(price_val)

            if not isinstance(miktar_val, float):
                continue                # no usable quantity — skip

            if current_evrak is None:
                continue                # product row before any evrak — skip

            transactions.append({
                "evrak_no":       current_evrak,
                "tarih":          current_date,
                "urun_aciklamasi": urun,
                "unit_price_usd": round(price_val, 4) if price_val else "",
                "miktar_mt":      round(miktar_val, 3),
                "fabric_type":    classify_fabric(urun),
                "source_file":    source_label,
            })

    return transactions


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLS)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(label: str, rows: list[dict]) -> None:
    if not rows:
        print(f"  No transactions found.\n")
        return

    dates  = [r["tarih"] for r in rows if r["tarih"]]
    prices = [r["unit_price_usd"] for r in rows
              if isinstance(r["unit_price_usd"], (int, float))]
    miktars = [r["miktar_mt"] for r in rows
               if isinstance(r["miktar_mt"], (int, float))]
    products = Counter(r["urun_aciklamasi"] for r in rows)

    print(f"  Total transactions : {len(rows)}")
    if dates:
        print(f"  Date range         : {min(dates)}  to  {max(dates)}")
    if miktars:
        print(f"  Total miktar       : {sum(miktars):,.1f}")
    if prices:
        print(f"  Price range (USD)  : ${min(prices):.2f}  –  ${max(prices):.2f}")

    print(f"  Top 5 products:")
    for prod, cnt in products.most_common(5):
        print(f"    {cnt:4d}×  {prod}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_file(
    key: str,
    xls_path: str,
    source_label: str,
) -> list[dict]:
    print(f"Reading {xls_path}")

    if not os.path.exists(xls_path):
        print(f"  ERROR: file not found\n")
        return []

    with open(xls_path, "rb") as f:
        data = f.read()

    cells      = get_worksheet_cells(data)
    miktar_col, price_col = detect_schema(cells)

    schema_name = "orme" if miktar_col == 3 else "dokuma"
    print(f"  Schema detected    : {schema_name} "
          f"(miktar=col{miktar_col}, price=col{price_col})")

    rows = group_transactions(cells, miktar_col, price_col, source_label)
    return rows


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    for key, xls_path in INPUT_XLS.items():
        source_label = key
        rows = process_file(key, xls_path, source_label)

        out_path = OUTPUT_CSVS[key]
        write_csv(rows, out_path)
        print(f"  CSV written        : {out_path}")

        print(f"\n=== Summary: {key} ===")
        print_summary(key, rows)


if __name__ == "__main__":
    main()
