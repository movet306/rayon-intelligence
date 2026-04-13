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
    # SEGMENT 5 — Turkish technical/military/functional competitors
    {
        "name": "Kipaş Mensucat",
        "country": "TR",
        "category": "competitor",
        "website": "https://kipas.com.tr",
        "tags": ["woven", "knit", "FR", "military", "technical", "export"],
        "notes": "Integrated yarn to fabric; defense FR fabrics, military textiles.",
    },
    {
        "name": "Ekoten Textile",
        "country": "TR",
        "category": "competitor",
        "website": "https://ekoten.com.tr",
        "tags": ["knit", "technical", "military", "FR", "export"],
        "notes": "Functional knit fabrics; CORDURA, military, activewear segments.",
    },
    {
        "name": "MEM Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://memtekstil.com",
        "tags": ["knit", "technical", "export"],
        "notes": "Integrated yarn to knit fabric; viscose/modal specialisation.",
    },
    {
        "name": "SANKO Textile",
        "country": "TR",
        "category": "competitor",
        "website": "https://sankotekstil.com",
        "tags": ["knit", "woven", "export"],
        "notes": "Sustainable yarn and fabrics, athleisure focus.",
    },
    {
        "name": "Arkum Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://arkumtekstil.com",
        "tags": ["knit", "technical", "export"],
        "notes": "Vertical circular knit; active/performance fabrics.",
    },
    {
        "name": "Almodo Altunlar Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://almodo.com.tr",
        "tags": ["woven", "export"],
        "notes": "Woven polyester/viscose; exports to 60+ countries.",
    },
    {
        "name": "Ariteks Boyacılık",
        "country": "TR",
        "category": "competitor",
        "website": "https://ariteks.com.tr",
        "tags": ["woven", "FR", "military", "technical"],
        "notes": "Aramid/FR protective technical textiles; military contracts.",
    },
    {
        "name": "AKATEK",
        "country": "TR",
        "category": "competitor",
        "website": "https://akatek.com.tr",
        "tags": ["technical", "FR", "military", "export"],
        "notes": "FR/flame-protective yarns and finished fabrics.",
    },
    {
        "name": "Bengü Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://bengutekstil.com",
        "tags": ["woven", "military", "workwear", "technical"],
        "notes": "Ripstop military/outdoor/workwear fabrics with coating.",
    },
    {
        "name": "Akrida Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://akridatekstil.com",
        "tags": ["woven", "military", "technical"],
        "notes": "Ripstop and camouflage technical textiles.",
    },
    {
        "name": "Zeynar Mensucat",
        "country": "TR",
        "category": "competitor",
        "website": "https://zeynarmensucat.com",
        "tags": ["woven", "technical", "export"],
        "notes": "Dyed/printed fabrics, Performance Wear segment, OEKO-TEX certified.",
    },
    {
        "name": "Aslıteks",
        "country": "TR",
        "category": "competitor",
        "website": "https://asliteks.com.tr",
        "tags": ["knit", "technical", "export"],
        "notes": "Knitted performance fabrics; capacity ~150 t/month.",
    },
    {
        "name": "Karsu Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://karsutekstil.com",
        "tags": ["knit", "FR", "technical", "export"],
        "notes": "Technical yarns (aramid/FR); exports to 38 countries.",
    },
    {
        "name": "Micron Teknik Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://micronteknik.com",
        "tags": ["technical", "FR", "workwear"],
        "notes": "ESD/antistatic/arc-flash protective fabrics.",
    },
    {
        "name": "Zorlu Tekstil",
        "country": "TR",
        "category": "competitor",
        "website": "https://zorlu.com.tr",
        "tags": ["woven", "knit", "export"],
        "notes": "Large integrated textile group; USA/EU/Russia export markets.",
    },
    {
        "name": "BATUTEK Teknik Kumaş",
        "country": "TR",
        "category": "competitor",
        "website": "https://batutek.com.tr",
        "tags": ["woven", "technical", "waterproof"],
        "notes": "Waterproof technical fabrics; tent and outdoor fabrics.",
    },
    # SEGMENT 6 — International benchmarks
    {
        "name": "Lenzing AG",
        "country": "AT",
        "category": "competitor",
        "website": "https://lenzing.com",
        "tags": ["fiber", "technical", "benchmark"],
        "notes": "MMCF benchmark; ECOVERO and REFIBRA branded viscose fibres.",
    },
    {
        "name": "Schoeller Textil",
        "country": "CH",
        "category": "competitor",
        "website": "https://schoeller-textiles.com",
        "tags": ["woven", "technical", "benchmark", "export"],
        "notes": "High-performance softshell and protective textiles benchmark.",
    },
    {
        "name": "Concordia Textiles",
        "country": "BE",
        "category": "competitor",
        "website": "https://concordiatextiles.com",
        "tags": ["woven", "technical", "workwear", "benchmark"],
        "notes": "Technical outdoor and workwear fabrics; European benchmark.",
    },
    {
        "name": "Formosa Taffeta",
        "country": "TW",
        "category": "competitor",
        "website": "https://fft.com.tw",
        "tags": ["woven", "knit", "technical", "benchmark", "export"],
        "notes": "Functional woven/knit outdoor and workwear fabrics; global scale.",
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
