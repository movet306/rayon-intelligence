"""
Seed competitor companies into the companies table.
Usage: python db/seed_companies.py
"""

import os
import sys

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ["DATABASE_URL"]

COMPANIES = [
    # SEGMENT 1 — Direct Turkish competitors (woven + finishing)
    {
        "name": "ARTA Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://arta.com.tr",
        "tags": ["woven", "export"],
        "notes": "Çorlu-based, same location as Rayon. Woven fabric, finishing, export.",
    },
    {
        "name": "Ozkasif Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://ozkasif.com",
        "tags": ["woven", "workwear", "technical"],
        "notes": "Workwear, waterproof, flame retardant, Oxford fabric.",
    },
    {
        "name": "Barutçu Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://barutcu.com.tr",
        "tags": ["woven", "export"],
        "notes": "Woven, dyeing, Eastern Europe export. Exhibits at Texworld Paris.",
    },
    {
        "name": "Dominant Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://domitekstil.com",
        "tags": ["woven", "technical"],
        "notes": "Technical textile fabric, raincoat fabric. DOMITEX brand.",
    },
    # SEGMENT 2 — Direct Turkish competitors (knit + finishing)
    {
        "name": "Universal Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://universaltekstil.com",
        "tags": ["knit", "technical", "FR"],
        "notes": "Polyester knit, FR, antibacterial, anti-pilling. Capacity: 60 ton/day.",
    },
    {
        "name": "Ünteks Group",
        "country": "TR",
        "category": "competitor",
        "website": "https://unteksgroup.com",
        "tags": ["knit", "export"],
        "notes": "Integrated: yarn + knit fabric + dyeing + printing.",
    },
    {
        "name": "Rota Textile",
        "country": "TR",
        "category": "competitor",
        "website": "https://rotatex.com.tr",
        "tags": ["knit", "export"],
        "notes": "Integrated yarn and knit fabric, export oriented.",
    },
    {
        "name": "Üçler Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://uclertekstil.com.tr",
        "tags": ["knit"],
        "notes": "Knit fabric manufacturer. ~700 employees.",
    },
    # SEGMENT 3 — International price pressure
    {
        "name": "Henan Safe-Guard",
        "country": "CN",
        "category": "competitor",
        "website": "https://frworkwear.en.made-in-china.com",
        "tags": ["woven", "knit", "FR", "workwear", "military"],
        "notes": "FR woven and knitted fabrics, workwear, military. EN standards compliant.",
    },
    {
        "name": "Sapphire Finishing Mills",
        "country": "PK",
        "category": "competitor",
        "website": "https://sapphiremills.com",
        "tags": ["woven", "workwear", "military"],
        "notes": "Workwear, military, tactical fabric. Capacity: 6M meters/month.",
    },
    # SEGMENT 4 — Benchmark
    {
        "name": "Altınyıldız Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://altinyildiz.com.tr",
        "tags": ["woven", "military", "technical"],
        "notes": "Military fabric, CORDURA, technical textile.",
    },
    {
        "name": "Akın Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://akintekstil.com",
        "tags": ["woven", "technical", "export"],
        "notes": "Waterproof, UV protection, technical finishes, woven export.",
    },
]

INSERT_SQL = """
    INSERT INTO companies (name, country, category, website, tags, notes)
    VALUES (%(name)s, %(country)s, %(category)s::company_category, %(website)s, %(tags)s, %(notes)s)
    ON CONFLICT (name, country) DO UPDATE SET
        category = EXCLUDED.category,
        website  = EXCLUDED.website,
        tags     = EXCLUDED.tags,
        notes    = EXCLUDED.notes,
        updated_at = NOW()
    RETURNING id, name, country,
              CASE WHEN xmax = 0 THEN 'inserted' ELSE 'updated' END AS action
"""

def main():
    print(f"Connecting to Railway PostgreSQL...")
    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except psycopg2.OperationalError as e:
        print(f"ERROR: Could not connect — {e}")
        sys.exit(1)

    inserted = 0
    updated = 0
    errors = 0

    with conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for company in COMPANIES:
                try:
                    cur.execute(INSERT_SQL, {
                        "name":     company["name"],
                        "country":  company["country"],
                        "category": company["category"],
                        "website":  company["website"],
                        "tags":     company["tags"],
                        "notes":    company["notes"],
                    })
                    row = cur.fetchone()
                    action = row["action"]
                    if action == "inserted":
                        inserted += 1
                    else:
                        updated += 1
                    print(f"  [{action:8s}] {row['name']} ({row['country']})  id={row['id']}")
                except Exception as e:
                    errors += 1
                    conn.rollback()
                    print(f"  [ERROR   ] {company['name']}: {e}")

    conn.close()
    print(f"\nDone. inserted={inserted}  updated={updated}  errors={errors}")
    if errors:
        sys.exit(1)

if __name__ == "__main__":
    main()
