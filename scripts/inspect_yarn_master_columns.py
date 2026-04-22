"""dim_yarn_master tablosundaki tüm kolonları listele."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'dim_yarn_master'
    ORDER BY ordinal_position;
""")

print(f"{'COLUMN':<25} {'TYPE':<20}")
print("-" * 50)
for col_name, data_type in cur.fetchall():
    print(f"{col_name:<25} {data_type:<20}")

cur.close()
conn.close()