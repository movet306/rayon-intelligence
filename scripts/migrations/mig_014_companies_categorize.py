"""Mig 014: Categorize NULL companies + add 16 missing priority entities"""
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
url = os.environ['RAYON_DATABASE_URL']

# Step 1: ENUM extension (autocommit)
conn = psycopg2.connect(url)
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT EXISTS (SELECT 1 FROM pg_enum e JOIN pg_type t ON e.enumtypid=t.oid WHERE t.typname='company_category' AND e.enumlabel='regulator')")
if cur.fetchone()[0]:
    print("[1/4] SKIP: ENUM already has 'regulator'")
else:
    cur.execute("ALTER TYPE company_category ADD VALUE 'regulator'")
    print("[1/4] OK: ENUM +regulator")
conn.close()

# Steps 2-4: transaction
conn = psycopg2.connect(url)
conn.autocommit = False
cur = conn.cursor()

print("\n[2/4] Categorizing NULL by entity_type...")
mappings = [
    ('supplier',    ['supplier']),
    ('competitor',  ['competitor_tr', 'competitor_intl']),
    ('association', ['association']),
    ('regulator',   ['regulator']),
]
for cat, types in mappings:
    cur.execute(
        "UPDATE companies SET category = %s::company_category WHERE category IS NULL AND entity_type = ANY(%s) RETURNING name",
        (cat, types)
    )
    for r in cur.fetchall():
        print(f"  -> {cat:12s}: {r[0]}")

print("\n[3/4] Fix Lenzing AG: competitor -> supplier")
cur.execute("UPDATE companies SET category='supplier', entity_type='supplier' WHERE name='Lenzing AG' AND category='competitor' RETURNING name")
rows = cur.fetchall()
print(f"  -> {'Fixed: '+rows[0][0] if rows else 'SKIP: already fixed'}")

new_entities = [
    ("\u0130TH\u0130B",                  "TR", "association", "association", "TR",     "\u0130stanbul Tekstil ve Hammaddeleri \u0130hracat\u00e7\u0131lar\u0131 Birli\u011fi"),
    ("BGMEA",                            "BD", "association", "association", "GLOBAL", "Bangladesh Garment Manufacturers Association"),
    ("NCTO",                             "US", "association", "association", "GLOBAL", "National Council of Textile Organizations"),
    ("European Commission",              "BE", "regulator",   "regulator",   "EU",     "EU executive body"),
    ("\u0130zmir Commodity Exchange",    "TR", "other",       "regulator",   "TR",     "TR commodity exchange, cotton reference"),
    ("Teijin Frontier",                  "JP", "supplier",    "supplier",    "GLOBAL", "Japanese synthetic fiber"),
    ("Barmag",                           "DE", "supplier",    "supplier",    "EU",     "German textile machinery (Oerlikon Barmag)"),
    ("Saurer",                           "CH", "supplier",    "supplier",    "GLOBAL", "Swiss textile machinery"),
    ("Syre",                             "SE", "supplier",    "supplier",    "EU",     "Swedish chemical polyester recycling"),
    ("JEPLAN",                           "JP", "supplier",    "supplier",    "GLOBAL", "Japanese chemical recycler"),
    ("AWARE",                            "NL", "supplier",    "supplier",    "EU",     "Dutch traceability technology"),
    ("Archroma",                         "CH", "supplier",    "supplier",    "GLOBAL", "Swiss specialty chemicals (dyes)"),
    ("OMAFIL",                           "TR", "supplier",    "supplier",    "TR",     "OMA Polimer A.\u015e. - polyester yarn"),
    ("Egypt",                            "EG", "customer",    "customer_segment", "ME",     "Export destination market"),
    ("Geli\u015fim Tekstil",             "TR", "customer",    "customer_segment", "TR",     "TR knit fabric customer"),
    ("Garanti BBVA",                     "TR", "other",       "other",       "TR",     "Turkish bank, financing partner"),
]

print(f"\n[4/4] Inserting {len(new_entities)} entities...")
inserted = skipped = 0
for name, country, category, etype, geo, notes in new_entities:
    cur.execute("""
        INSERT INTO companies (name, country, category, entity_type, geography, notes)
        SELECT %s, %s, %s::company_category, %s, %s, %s
        WHERE NOT EXISTS (SELECT 1 FROM companies WHERE LOWER(TRIM(name)) = LOWER(TRIM(%s)))
        RETURNING name
    """, (name, country, category, etype, geo, notes, name))
    if cur.fetchone():
        print(f"  + {name} ({category})")
        inserted += 1
    else:
        print(f"  - SKIP: {name}")
        skipped += 1

conn.commit()

print(f"\n=== Result ===\nInserted: {inserted}, Skipped: {skipped}")
cur.execute("SELECT COALESCE(category::text,'(NULL)'), COUNT(*) FROM companies GROUP BY category ORDER BY COUNT(*) DESC")
for r in cur.fetchall():
    print(f"  {r[0]:15s}: {r[1]}")
cur.execute("SELECT COUNT(*) FROM companies")
print(f"\nTotal: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM companies WHERE category IS NULL")
print(f"NULL category: {cur.fetchone()[0]}")
conn.close()
print("\nDone.")