"""
data/parse_lescon_raw.py

Binary BIFF8 parser for two Lescon account-statement XLS files.
No external dependencies — uses only the Python standard library.

Files read (adjust INPUT_FILES if paths differ on your machine):
  C:\\Users\\ASUS\\Downloads\\lescon    örme usd hs.xls   → lescon_orme_raw.csv
  C:\\Users\\ASUS\\Downloads\\lescon    usd.xls            → lescon_dokuma_raw.csv

Output written to the same directory as this script (data/):
  lescon_orme_raw.csv
  lescon_dokuma_raw.csv
  lescon_parse_summary.txt

Usage:
    python data/parse_lescon_raw.py

How it works
------------
Both XLS files are OLE2 compound documents (BIFF8 format).  The Workbook
stream starts at byte offset 512 (the first OLE2 sector, confirmed by BOF
record at that offset) and is stored contiguously.  We therefore skip the
512-byte OLE2 header and parse raw BIFF8 records directly.

BIFF8 record layout:
  2 bytes  record type (little-endian uint16)
  2 bytes  data length  (little-endian uint16)
  N bytes  record data

All string cells share a global Shared String Table (SST, record 0x00FC).
Long SSTs are split across CONTINUE records (0x003C) that follow immediately.
We also collect any inline LABEL records (0x0204) that hold strings directly.
"""

import csv
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

INPUT_FILES = {
    "lescon_orme":   os.path.join(DOWNLOADS, "lescon    \u00f6rme usd hs.xls"),
    "lescon_dokuma": os.path.join(DOWNLOADS, "lescon    usd.xls"),
}

OUTPUT_DIR  = Path(__file__).parent          # data/
OUTPUT_CSVS = {
    "lescon_orme":   OUTPUT_DIR / "lescon_orme_raw.csv",
    "lescon_dokuma": OUTPUT_DIR / "lescon_dokuma_raw.csv",
}
SUMMARY_PATH = OUTPUT_DIR / "lescon_parse_summary.txt"

# ---------------------------------------------------------------------------
# BIFF8 record type constants
# ---------------------------------------------------------------------------
REC_BOF      = 0x0809
REC_EOF      = 0x000A
REC_SST      = 0x00FC
REC_CONTINUE = 0x003C
REC_LABEL    = 0x0204   # inline string cell (legacy, not via SST)

# ---------------------------------------------------------------------------
# Line-type classification patterns (evaluated in order; first match wins)
# ---------------------------------------------------------------------------
PATTERNS = [
    # "Evrak No :202500122"
    ("evrak",
     re.compile(r"Evrak\s+No\s*:\s*\d+", re.IGNORECASE)),

    # "3.70$+KDV /POLY.BISTRECH ..."  or  "0.60$+%20 KDV /FASON BOYAMA"
    ("price_product",
     re.compile(r"^\d[\d.]*\s*\$\s*\+\s*(?:%\d+\s*)?KDV\s*/", re.IGNORECASE)),

    # "81.786,60 TL/38,7045 16.05.25 VD.ÇEK FARKI..."
    # "1.412.670 TL/35,5823 21.01.25 VD.ÇEK TAHSİL..."
    ("kur_farki",
     re.compile(r"[\d.]+[\d,]*\s+TL/[\d,]+\s+\d{1,2}\.\d{2}\.\d{2}", re.IGNORECASE)),

    # "Toplam:"
    ("toplam",
     re.compile(r"^Toplam\s*:", re.IGNORECASE)),

    # Standalone date cell: DD.MM.YYYY, DD/MM/YYYY, DD.MM.YY
    ("tarih",
     re.compile(r"^\d{1,2}[./]\d{2}[./]\d{2,4}\s*$")),
]

MIN_STRING_LEN = 3


# ---------------------------------------------------------------------------
# BIFF8 parsing helpers
# ---------------------------------------------------------------------------

def iter_biff8_records(data: bytes, start: int = 512):
    """
    Yield (record_type, record_data_bytes) tuples by walking BIFF8 records
    from `start` to end of `data`.

    Stops cleanly on truncated data or clearly invalid record lengths.
    """
    pos = start
    while pos + 4 <= len(data):
        rec_type, rec_len = struct.unpack_from("<HH", data, pos)
        if rec_len > 65535:          # BIFF8 maximum; corrupt data guard
            break
        payload_end = pos + 4 + rec_len
        if payload_end > len(data):  # truncated
            break
        yield rec_type, data[pos + 4 : payload_end]
        pos = payload_end


def _read_xl_unicode_string(buf: bytes, pos: int,
                             cont_boundaries: set) -> tuple[str, int]:
    """
    Parse one XLUnicodeString from buf starting at pos.

    cont_boundaries: set of byte offsets in buf where a CONTINUE record
                     begins.  At those positions a new fHighByte grbit byte
                     is present before the next character.

    Returns (decoded_string, new_pos).
    Raises IndexError / struct.error on truncated data.
    """
    cch = struct.unpack_from("<H", buf, pos)[0]
    pos += 2

    grbit     = buf[pos]; pos += 1
    fHighByte = grbit & 0x01
    fRichSt   = (grbit >> 3) & 0x01
    fExtSt    = (grbit >> 2) & 0x01

    cRun = 0
    if fRichSt:
        cRun = struct.unpack_from("<H", buf, pos)[0]; pos += 2

    cbExt = 0
    if fExtSt:
        cbExt = struct.unpack_from("<I", buf, pos)[0]; pos += 4

    # Read character data, honouring CONTINUE-boundary encoding switches
    chars       = []
    cur_highbyte = fHighByte
    for _ in range(cch):
        if pos in cont_boundaries:
            cur_highbyte = buf[pos] & 0x01
            pos += 1
        if cur_highbyte:
            chars.append(struct.unpack_from("<H", buf, pos)[0]); pos += 2
        else:
            chars.append(buf[pos]); pos += 1

    text = "".join(chr(c) for c in chars)

    pos += 4 * cRun   # skip rich-text formatting runs
    pos += cbExt      # skip phonetic/extended string data
    return text, pos


def extract_sst_strings(data: bytes) -> list[str]:
    """
    Walk BIFF8 records, find the SST (and any following CONTINUE records),
    and return a list of all unique strings in the SST.
    """
    strings: list[str] = []
    records = list(iter_biff8_records(data))

    for idx, (rec_type, payload) in enumerate(records):
        if rec_type != REC_SST:
            continue

        cst_total  = struct.unpack_from("<I", payload, 0)[0]
        cst_unique = struct.unpack_from("<I", payload, 4)[0]

        # Sanity-check: reject false positives from non-SST sectors
        if cst_unique > 100_000 or cst_unique == 0:
            continue

        # Concatenate SST payload + any immediately following CONTINUE records
        sst_buf     = bytearray(payload)
        boundaries  = set()                    # byte offsets of CONTINUE starts

        for j in range(idx + 1, len(records)):
            cont_type, cont_payload = records[j]
            if cont_type != REC_CONTINUE:
                break
            boundaries.add(len(sst_buf))
            sst_buf.extend(cont_payload)

        # Parse strings from the concatenated buffer
        buf = bytes(sst_buf)
        pos = 8                                # skip cstTotal (4) + cstUnique (4)

        for _ in range(cst_unique):
            if pos >= len(buf):
                break
            try:
                text, pos = _read_xl_unicode_string(buf, pos, boundaries)
                strings.append(text)
            except (IndexError, struct.error):
                break                          # truncated data; stop cleanly

        break  # only one SST per workbook

    return strings


def extract_label_strings(data: bytes) -> list[str]:
    """
    Return strings from inline LABEL records (0x0204).
    These are cells whose string value is stored directly rather than via SST.
    """
    strings: list[str] = []
    for rec_type, payload in iter_biff8_records(data):
        if rec_type != REC_LABEL:
            continue
        if len(payload) < 7:
            continue
        # row(2) col(2) XF(2) then XLUnicodeString
        try:
            text, _ = _read_xl_unicode_string(payload, 6, set())
            strings.append(text)
        except (IndexError, struct.error):
            continue
    return strings


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify(text: str) -> str:
    for line_type, pattern in PATTERNS:
        if pattern.search(text):
            return line_type
    return "diger"


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def process_file(xls_path: str, source_label: str) -> list[dict]:
    """
    Read one XLS file and return a list of row dicts:
      {"raw_line": str, "line_type": str, "source_file": str}
    """
    with open(xls_path, "rb") as f:
        data = f.read()

    sst_strings   = extract_sst_strings(data)
    label_strings = extract_label_strings(data)
    all_strings   = sst_strings + label_strings

    rows = []
    for text in all_strings:
        text = text.strip()
        if len(text) < MIN_STRING_LEN:
            continue
        rows.append({
            "raw_line":    text,
            "line_type":   classify(text),
            "source_file": os.path.basename(xls_path),
        })

    return rows


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["raw_line", "line_type", "source_file"])
        writer.writeheader()
        writer.writerows(rows)


def write_summary(all_results: dict[str, list[dict]], path: Path) -> None:
    lines = ["Lescon XLS Parse Summary", "=" * 40, ""]

    grand_total   = 0
    grand_counter: Counter = Counter()

    for label, rows in all_results.items():
        counter = Counter(r["line_type"] for r in rows)
        grand_counter += counter
        grand_total   += len(rows)

        lines.append(f"Source : {label}")
        lines.append(f"Total  : {len(rows)} strings")
        for lt in ["evrak", "price_product", "kur_farki", "toplam", "tarih", "diger"]:
            lines.append(f"  {lt:<15}: {counter.get(lt, 0)}")
        lines.append("")

    lines.append("GRAND TOTAL")
    lines.append(f"Total  : {grand_total} strings")
    for lt in ["evrak", "price_product", "kur_farki", "toplam", "tarih", "diger"]:
        lines.append(f"  {lt:<15}: {grand_counter.get(lt, 0)}")

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    all_results: dict[str, list[dict]] = {}

    for label, xls_path in INPUT_FILES.items():
        print(f"Processing {label}: {xls_path}")

        if not os.path.exists(xls_path):
            print(f"  ERROR: file not found — {xls_path}")
            continue

        rows = process_file(xls_path, label)
        all_results[label] = rows

        out_path = OUTPUT_CSVS[label]
        write_csv(rows, out_path)

        counter = Counter(r["line_type"] for r in rows)
        print(f"  Strings extracted : {len(rows)}")
        for lt in ["evrak", "price_product", "kur_farki", "toplam", "tarih", "diger"]:
            print(f"    {lt:<15}: {counter.get(lt, 0)}")
        print(f"  CSV written       : {out_path}")
        print()

    if all_results:
        write_summary(all_results, SUMMARY_PATH)
        print(f"Summary written: {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
