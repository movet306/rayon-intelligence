"""
Phase B.0 — Cotton Usage Discovery

Goal: find every cotton-related label across Rayon's internal tables,
parse them into (count_ne, ply, cotton_process, spinning_method) tuples,
and report real usage frequency so we can seed Phase B from data, not theory.

Searches:
  1. yarn_costs          (245 records, 2015-2025)
  2. orders              (1484 records)
  3. order_invoices      (2459 sub-records)
  4. lkp_yarn_taxonomy   (52 types)
  5. lescon_sales        (532 rows — fabric-level, may mention yarn)
  6. any column flagged cotton-related in information_schema

Output: categorized report, no DB writes.
"""
import os
import re
import sys
import psycopg2
from collections import Counter, defaultdict
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# ---------------------------------------------------------------------------
# Heuristics — what counts as "cotton-related"?
# ---------------------------------------------------------------------------
COTTON_KEYWORDS = [
    r"\bcotton\b", r"\bpamuk\b", r"\bpenye\b", r"\bkarde\b", r"\bkardeli\b",
    r"\bco\b", r"\bcot\b", r"\b100%?\s*co\b", r"\b100%?\s*pamuk\b",
    r"\bne\s*\d+", r"\b\d+/\d+\b",  # Ne 30, 30/1 patterns
    r"open[\s\-]?end", r"\boe\b", r"\bring\b", r"\bcompact\b", r"\bvortex\b",
]
COTTON_RE = re.compile("|".join(COTTON_KEYWORDS), re.IGNORECASE)

# Polyester / synthetic rule-outs — if any of these match, it's NOT pure cotton
SYNTHETIC_RULEOUT = re.compile(
    r"\b(polyester|pes|poliester|pa6|pa66|naylon|nylon|viscose|viskon|"
    r"modal|lyocell|elastane|elastan|lycra|spandex|acrylic|akrilik)\b",
    re.IGNORECASE
)


def is_likely_cotton(text):
    """Return True if text looks cotton-related and not blended with synthetic."""
    if not text:
        return False
    text_str = str(text)
    if not COTTON_RE.search(text_str):
        return False
    if SYNTHETIC_RULEOUT.search(text_str):
        return False  # blend or synthetic, not pure cotton
    return True


# ---------------------------------------------------------------------------
# Parser — normalize raw label into canonical tuple
# ---------------------------------------------------------------------------
def parse_cotton_label(text):
    """
    Extract (count_ne, ply, cotton_process, spinning_method) from raw text.
    Returns dict with None for unparseable parts.
    """
    t = str(text).lower()
    result = {
        "count_ne":         None,
        "ply":              None,
        "cotton_process":   None,
        "spinning_method":  None,
        "raw":              text,
    }

    # count_ne + ply patterns: "Ne 30/1", "30/1", "Ne30", "30s"
    m = re.search(r"(?:ne\s*)?(\d{1,3})\s*/\s*(\d)", t)
    if m:
        result["count_ne"] = int(m.group(1))
        result["ply"]      = int(m.group(2))
    else:
        m = re.search(r"ne\s*(\d{1,3})", t)
        if m:
            result["count_ne"] = int(m.group(1))
            result["ply"]      = 1  # default single
        else:
            # "30s" style
            m = re.search(r"\b(\d{2,3})s\b", t)
            if m:
                result["count_ne"] = int(m.group(1))
                result["ply"]      = 1

    # cotton_process
    if re.search(r"penye|combed", t):
        result["cotton_process"] = "combed"
    elif re.search(r"karde|carded", t):
        result["cotton_process"] = "carded"

    # spinning_method
    if re.search(r"open[\s\-]?end|\boe\b", t):
        result["spinning_method"] = "open_end"
    elif re.search(r"compact", t):
        result["spinning_method"] = "compact"
    elif re.search(r"vortex", t):
        result["spinning_method"] = "vortex"
    elif re.search(r"ring", t):
        result["spinning_method"] = "ring"

    return result


def canonical_key(parsed):
    """Build canonical yarn_key if all core fields present."""
    if not all([parsed["count_ne"], parsed["ply"],
                parsed["cotton_process"], parsed["spinning_method"]]):
        return None
    return (f"CO_Ne{parsed['count_ne']}_"
            f"{parsed['ply']}PLY_"
            f"{parsed['cotton_process'].upper()}_"
            f"{parsed['spinning_method'].upper()}")


# ---------------------------------------------------------------------------
# Table scanners
# ---------------------------------------------------------------------------
raw_labels = []   # list of (source_table, source_column, raw_text)


def scan_column(table, column, extra_where=""):
    """Pull non-null values from a given column, filter for cotton-likelihood."""
    try:
        sql = f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'
        if extra_where:
            sql += f" AND {extra_where}"
        cur.execute(sql)
        rows = cur.fetchall()
        count = 0
        for (val,) in rows:
            if is_likely_cotton(val):
                raw_labels.append((table, column, str(val).strip()))
                count += 1
        print(f"    ✓ {table}.{column}: {count} cotton-like values (of {len(rows)} distinct)")
    except Exception as e:
        print(f"    ✗ {table}.{column}: ERROR — {e}")
        conn.rollback()


def get_text_columns(table):
    """Return list of text/varchar columns for a given table."""
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = %s
          AND data_type IN ('text','character varying','character')
        ORDER BY ordinal_position
    """, (table,))
    return [c for c, _ in cur.fetchall()]


# ---------------------------------------------------------------------------
# 1) Scan all relevant tables
# ---------------------------------------------------------------------------
print("=" * 70)
print("STEP 1 — Scanning internal tables for cotton-related labels")
print("=" * 70)

TARGETS = [
    "yarn_costs",
    "orders",
    "order_invoices",
    "lkp_yarn_taxonomy",
    "lescon_sales",
]

for tbl in TARGETS:
    print(f"\n[{tbl}]")
    # check table exists
    cur.execute("""
        SELECT 1 FROM information_schema.tables
        WHERE table_name = %s
    """, (tbl,))
    if not cur.fetchone():
        print(f"    (table does not exist, skipping)")
        continue

    cols = get_text_columns(tbl)
    if not cols:
        print(f"    (no text columns)")
        continue

    for col in cols:
        scan_column(tbl, col)

print(f"\n>>> TOTAL raw cotton-like strings found: {len(raw_labels)}")


# ---------------------------------------------------------------------------
# 2) Raw label examples (de-dup, show variety)
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("STEP 2 — Raw cotton label examples")
print("=" * 70)

unique_texts = sorted(set(r[2] for r in raw_labels))
print(f"Unique raw strings: {len(unique_texts)}")
print("\nFirst 40 examples:")
for t in unique_texts[:40]:
    print(f"    {t!r}")
if len(unique_texts) > 40:
    print(f"    ... and {len(unique_texts) - 40} more")


# ---------------------------------------------------------------------------
# 3) Parse + count canonical patterns
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("STEP 3 — Parsed canonical pattern frequencies")
print("=" * 70)

canonical_counts  = Counter()
partial_counts    = Counter()   # has count_ne but missing process/spin
ambiguous         = []

for source_tbl, source_col, raw in raw_labels:
    parsed = parse_cotton_label(raw)
    canon  = canonical_key(parsed)
    if canon:
        canonical_counts[canon] += 1
    elif parsed["count_ne"]:
        partial_key = (
            f"Ne{parsed['count_ne']}/{parsed['ply'] or '?'}"
            f"_proc={parsed['cotton_process'] or '?'}"
            f"_spin={parsed['spinning_method'] or '?'}"
        )
        partial_counts[partial_key] += 1
    else:
        ambiguous.append(raw)

print(f"\n>>> FULL canonical matches: {sum(canonical_counts.values())}")
print(f">>> PARTIAL matches (missing some fields): {sum(partial_counts.values())}")
print(f">>> AMBIGUOUS (couldn't parse count): {len(ambiguous)}")

print("\n--- Top canonical patterns ---")
for canon, n in canonical_counts.most_common(20):
    print(f"    {n:4d}x   {canon}")

print("\n--- Top partial patterns (missing fields) ---")
for partial, n in partial_counts.most_common(20):
    print(f"    {n:4d}x   {partial}")

print("\n--- Ambiguous label sample (first 20) ---")
for a in sorted(set(ambiguous))[:20]:
    print(f"    {a!r}")


# ---------------------------------------------------------------------------
# 4) Recommended seed set
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("STEP 4 — Recommended Phase B seed (top specs by frequency)")
print("=" * 70)

top4 = canonical_counts.most_common(4)
if not top4:
    print("\n⚠ No fully-canonical patterns found in internal data.")
    print("   Phase B seed cannot be derived automatically.")
    print("   Options: (a) use partial patterns + human review,")
    print("            (b) proceed with minimal theoretical seed (Ne30 combed ring),")
    print("            (c) postpone Phase B until internal data captures cotton spec.")
else:
    print(f"\nTop {len(top4)} canonical cotton specs by internal usage frequency:")
    for canon, n in top4:
        print(f"    {n:4d}x   {canon}")

# Excluded: everything below top 4
excluded = canonical_counts.most_common()[4:]
if excluded:
    print(f"\n{len(excluded)} patterns below top 4 (excluded from seed):")
    for canon, n in excluded[:10]:
        reason = "low frequency" if n < 3 else "below top 4"
        print(f"    {n:4d}x   {canon}   [{reason}]")


# ---------------------------------------------------------------------------
# 5) Data quality flags
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("STEP 5 — Data quality & caveats")
print("=" * 70)

total_raw    = len(raw_labels)
total_canon  = sum(canonical_counts.values())
total_part   = sum(partial_counts.values())
total_amb    = len(ambiguous)

print(f"Total raw cotton labels:        {total_raw}")
print(f"Fully canonical:                {total_canon}  ({total_canon*100/max(total_raw,1):.1f}%)")
print(f"Partial (needs review):         {total_part}")
print(f"Ambiguous (unparseable):        {total_amb}")

if total_canon == 0 and total_raw > 0:
    print("\n⚠ NO fully-canonical matches.")
    print("  This usually means cotton labels in internal data are free-text")
    print("  without consistent spec fields (common in small textile ERPs).")
    print("  Recommendation: proceed with minimum viable seed + manual refinement.")

if total_part > total_canon * 2:
    print("\n⚠ Many labels missing process (carded/combed) or spin method.")
    print("  These are likely simplified entries — partial data has to be")
    print("  enriched manually before seeding.")

conn.close()
print("\n" + "=" * 70)
print("DISCOVERY COMPLETE — no DB writes performed.")
print("=" * 70)