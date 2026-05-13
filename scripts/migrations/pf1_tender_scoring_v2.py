"""
Phase F1 Day 2 - Tender scoring v2 (2026-05-13)
================================================
Idempotent migration: keyword expansion + institution negative patterns.

Changes:
- +18 new keywords (police/military/gendarmerie/security/protective uniforms,
  workwear: forma, şort, eşofman, su geçirmez)
- -1 keyword removed (koruyucu - too generic, false positives)
- +8 negative institution patterns (Tarım/Orman/DSİ/Doğa Koruma)

Effect:
- Better coverage for textile-relevant tenders (police/military/firefighter)
- Filters out pesticide-protective tenders (agriculture/forestry/water authority)
- Actionable count: ~37 -> ~20-25 (irrelevant noise filtered)

Idempotency: ON CONFLICT DO NOTHING / EXISTS guards; safe to re-run.

Usage:
    $env:RAYON_DATABASE_URL = "postgresql://..."
    python scripts/migrations/pf1_tender_scoring_v2.py
"""
import os
import psycopg2


KEYWORDS = [
    # high_priority (35): military/police/gendarmerie uniforms
    ("polis üniforma",     "polis uniforma",     "high_priority", 35),
    ("polis uniforma",     "polis uniforma",     "high_priority", 35),
    ("asker üniforma",     "asker uniforma",     "high_priority", 35),
    ("asker uniforma",     "asker uniforma",     "high_priority", 35),
    ("jandarma üniforma",  "jandarma uniforma",  "high_priority", 35),
    ("jandarma uniforma",  "jandarma uniforma",  "high_priority", 35),
    # high_priority (30): security uniform
    ("güvenlik üniforma",  "guvenlik uniforma",  "high_priority", 30),
    ("guvenlik uniforma",  "guvenlik uniforma",  "high_priority", 30),
    # medium_priority (30): protective uniform
    ("koruyucu üniforma",  "koruyucu uniforma",  "medium_priority", 30),
    ("koruyucu uniforma",  "koruyucu uniforma",  "medium_priority", 30),
    # medium_priority (22): tracksuit
    ("eşofman",            "esofman",            "medium_priority", 22),
    ("esofman",            "esofman",            "medium_priority", 22),
    # medium_priority (20): waterproof
    ("su geçirmez",        "su gecirmez",        "medium_priority", 20),
    ("su gecirmez",        "su gecirmez",        "medium_priority", 20),
    # medium_priority (18): generic (lower weight for false positive risk)
    ("forma",              "forma",              "medium_priority", 18),
    ("şort",               "sort",               "medium_priority", 18),
    ("sort",               "sort",               "medium_priority", 18),
]

KEYWORDS_TO_DELETE = ["koruyucu"]

INSTITUTIONS_NEGATIVE = [
    # Tarım Bakanlığı + İl Tarım Müdürlükleri (pesticide protective - irrelevant)
    ("İl Tarım ve Orman Müdürlüğü",  "il tarim ve orman mudurlugu", -50, "negative"),
    ("Tarım ve Orman Bakanlığı",     "tarim ve orman bakanligi",    -50, "negative"),
    # DSİ (water authority protective - irrelevant)
    ("Devlet Su İşleri",             "devlet su isleri",            -50, "negative"),
    ("DSİ",                          "dsi",                         -50, "negative"),
    # Orman (forestry protective - irrelevant)
    ("Orman İşletme Müdürlüğü",      "orman isletme mudurlugu",     -50, "negative"),
    ("Orman Bölge Müdürlüğü",        "orman bolge mudurlugu",       -50, "negative"),
    ("Orman Genel Müdürlüğü",        "orman genel mudurlugu",       -50, "negative"),
    # Nature protection (environmental, irrelevant)
    ("Doğa Koruma ve Milli Parklar", "doga koruma ve milli parklar", -50, "negative"),
]


def main():
    db_url = os.environ.get("RAYON_DATABASE_URL")
    if not db_url:
        raise RuntimeError("RAYON_DATABASE_URL not set")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    print("Phase F1 Tender Scoring v2 Migration")
    print("=" * 60)

    inserted_kw = 0
    for kw, norm, cls, wt in KEYWORDS:
        cur.execute(
            """INSERT INTO lkp_tender_keywords (keyword, normalized, keyword_class, weight)
               VALUES (%s, %s, %s, %s) ON CONFLICT (keyword) DO NOTHING""",
            (kw, norm, cls, wt),
        )
        if cur.rowcount:
            inserted_kw += 1
    print(f"  Keywords inserted (new):     {inserted_kw} / {len(KEYWORDS)}")

    for kw in KEYWORDS_TO_DELETE:
        cur.execute("DELETE FROM lkp_tender_keywords WHERE keyword = %s", (kw,))
        if cur.rowcount:
            print(f"  Removed obsolete keyword:    {kw}")

    inserted_inst = 0
    for pat, norm, wt, cat in INSTITUTIONS_NEGATIVE:
        cur.execute("SELECT 1 FROM lkp_institution_priority WHERE pattern = %s", (pat,))
        if cur.fetchone():
            continue
        cur.execute(
            """INSERT INTO lkp_institution_priority (pattern, normalized_pattern, weight, category)
               VALUES (%s, %s, %s, %s)""",
            (pat, norm, wt, cat),
        )
        inserted_inst += 1
    print(f"  Institutions inserted (new): {inserted_inst} / {len(INSTITUTIONS_NEGATIVE)}")

    conn.commit()

    cur.execute("SELECT keyword_class, COUNT(*) FROM lkp_tender_keywords GROUP BY 1 ORDER BY 1")
    print()
    print("  Final keyword counts:")
    for r in cur.fetchall():
        print(f"    {r[0]:20} {r[1]}")

    cur.execute("SELECT category, COUNT(*) FROM lkp_institution_priority GROUP BY 1 ORDER BY 1")
    print()
    print("  Final institution counts:")
    for r in cur.fetchall():
        print(f"    {r[0]:20} {r[1]}")

    conn.close()
    print()
    print("Done. To re-score existing tenders, run:")
    print("  python scripts/migrations/reanalyze_last_30d.py")


if __name__ == "__main__":
    main()