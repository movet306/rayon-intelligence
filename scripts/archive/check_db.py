import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

cur.execute('''
    SELECT 'bronze_alis' AS t, COUNT(*) FROM bronze_nebim_alis_raw UNION ALL
    SELECT 'bronze_satis', COUNT(*) FROM bronze_nebim_satis_raw UNION ALL
    SELECT 'fact_purchase', COUNT(*) FROM fact_purchase_lines_clean UNION ALL
    SELECT 'fact_sales', COUNT(*) FROM fact_sales_lines_clean UNION ALL
    SELECT 'dim_buckets', COUNT(*) FROM dim_business_bucket UNION ALL
    SELECT 'dim_versions', COUNT(*) FROM dim_classification_version
''')

for row in cur.fetchall():
    print(f'  {row[0]:20s}  {row[1]:>8,}')

conn.close()
