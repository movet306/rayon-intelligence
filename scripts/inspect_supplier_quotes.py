"""
Phase A — coverage logic öncesi teşhis.
fact_supplier_quotes tablosunun gerçek durumunu raporla.
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

def run(label, sql):
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        if cols:
            print(" | ".join(cols))
            print("-" * 60)
        for r in rows:
            print(" | ".join(str(v) for v in r))
        if not rows:
            print("(no rows)")
    except Exception as e:
        print(f"ERROR: {e}")
        conn.rollback()

# 1. Tablo var mı, şema ne?
run("1. TABLE EXISTS + COLUMNS", """
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name = 'fact_supplier_quotes'
    ORDER BY ordinal_position;
""")

# 2. Toplam satır sayısı
run("2. TOTAL ROW COUNT", """
    SELECT COUNT(*) AS total_rows FROM fact_supplier_quotes;
""")

# 3. Kaç distinct yarn kapsanmış?
run("3. DISTINCT YARN COVERAGE", """
    SELECT COUNT(DISTINCT yarn_id) AS distinct_yarns
    FROM fact_supplier_quotes;
""")

# 4. Son 20 kayıt — gerçek mi test mi?
run("4. RECENT 20 ROWS (quality check)", """
    SELECT yarn_id, supplier_name, quote_date, price_usd_kg, source
    FROM fact_supplier_quotes
    ORDER BY quote_date DESC NULLS LAST
    LIMIT 20;
""")

# 5. dim_yarn_master'daki flag alanları
run("5. DIM_YARN_MASTER FLAG COLUMNS", """
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'dim_yarn_master'
      AND column_name IN ('pricing_eligible', 'is_placeholder', 'subspec_sensitive', 'is_active')
    ORDER BY column_name;
""")

# 6. Flag dağılımı
run("6. DIM_YARN_MASTER FLAG DISTRIBUTION", """
    SELECT
      COUNT(*) FILTER (WHERE is_placeholder = true)   AS placeholders,
      COUNT(*) FILTER (WHERE subspec_sensitive = true) AS subspec_sensitive,
      COUNT(*) AS total_specs
    FROM dim_yarn_master;
""")

cur.close()
conn.close()
print("\n" + "="*60 + "\nInspection complete.\n" + "="*60)