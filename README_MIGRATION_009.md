# Migration 009 — Nebim Internal Data Foundation

## Ne yapıyoruz

5 yıllık Nebim ALIŞ/SATIŞ verisini v3 classification'la PostgreSQL'e yüklüyoruz.

## Dosyalar

İndirdiğin zip içinde 4 dosya var:

1. **`009_nebim_foundation.sql`** → `migrations/` klasörüne
2. **`classify_nebim_v3.py`** → `scripts/` klasörüne
3. **`etl_nebim_load.py`** → `scripts/` klasörüne
4. **`verify_nebim_load.py`** → `scripts/` klasörüne

---

## Adım adım

Her adımdan sonra sonucu kopyala, yapıştır — bir sorun varsa beraber düzelteriz.

### Adım 1 — SQL migration'ı uygula

```powershell
cd C:\Projects\rayon-intelligence
conda activate rayon-dashboard
```

SQL dosyasını `migrations/` altına koy (VS Code'da kopyala-yapıştır veya explorer'da taşı).

Railway DB'ye bağlanıp uygula:

```powershell
python -c "import os; from dotenv import load_dotenv; load_dotenv(); import psycopg2; conn = psycopg2.connect(os.environ['DATABASE_URL']); cur = conn.cursor(); cur.execute(open('migrations/009_nebim_foundation.sql', encoding='utf-8').read()); conn.commit(); print('Migration 009 applied.'); conn.close()"
```

Beklediğim çıktı:
```
Migration 009 applied.
```

### Adım 2 — v3 classification'ı çalıştır (pickle'lar üret)

`classify_nebim_v3.py`'yi `scripts/` altına koy. Sonra:

```powershell
python scripts/classify_nebim_v3.py
```

Beklediğim çıktı:
```
Loading: C:\Projects\rayon-intelligence\data\ALIŞ SATIŞ 22042026.xlsx
  [X.Xs] ALIŞ: 60,768 / SATIŞ: 50,589
  [X.Xs] ALIŞ classified
  [X.Xs] SATIŞ classified

Outputs in C:\Projects\rayon-intelligence\outputs\v3
  alis_raw.pkl        (60,768 rows)
  satis_raw.pkl       (50,589 rows)
  alis_clean_v3.pkl   (60,768 rows, 30 cols)
  satis_clean_v3.pkl  (50,589 rows, 30 cols)
  classification_summary.txt

Next: python scripts/etl_nebim_load.py
```

### Adım 3 — ETL loader'ı çalıştır (DB'ye yaz)

`etl_nebim_load.py`'yi `scripts/` altına koy. Sonra:

```powershell
python scripts/etl_nebim_load.py
```

Bu 3-5 dakika sürebilir, 111,357 satır yüklüyor.

Beklediğim çıktı:
```
Loading pickles...
Connecting to DB...
  All migration 009 tables present ✓

=== NEW BATCH: <uuid> ===
=== Classification version: v3 ===

  Loading bronze_nebim_alis_raw (60,768 rows)...
    [Xs] inserted 60,768 bronze rows
  Loading bronze_nebim_satis_raw (50,589 rows)...
    [Xs] inserted 50,589 bronze rows
  Loading fact_purchase_lines_clean (60,768 rows)...
    [Xs] inserted 60,768 fact rows
  Loading fact_sales_lines_clean (50,589 rows)...
    [Xs] inserted 50,589 fact rows

=== LOAD COMPLETE ===
Total (all batches): fact_purchase=60,768  fact_sales=50,589
```

### Adım 4 — Verification

`verify_nebim_load.py`'yi `scripts/` altına koy. Sonra:

```powershell
python scripts/verify_nebim_load.py
```

Beklediğim çıktı: tüm checks yeşil ✓. Özellikle:
- 4 table'ın row sayısı pickle ile eşleşiyor
- Her bucket'ın TL tutarı pickle ile eşleşiyor
- Yarn resale: 826 rows / 458.7M TL
- Suspected asset sales: 2 rows
- Supplier prepayments: tüm satırlar `is_prepayment=TRUE`
- dim_business_bucket: 28 bucket seeded
- Current classification version: v3

---

## Bir şey ters giderse

### "table already exists" hatası (Adım 1)
Migration idempotent, tekrar çalıştır — `DROP IF EXISTS` var.

### ".env" dosyası yok hatası
`.env` dosyası yok demek. Var olduğundan emin ol, içinde `DATABASE_URL=postgres://...` olmalı.

### "pickle not found" hatası (Adım 3)
Adım 2'yi atlamış olabilirsin. Önce classify'ı çalıştır.

### Classification farklı rakamlar çıkarırsa
Ben cloud'da aynı script'le 111,357 satırı aynı şekilde classified ettim. Beklentin:
- ALIŞ anomalous_review: ~198 rows
- SATIŞ anomalous_review: ~1,005 rows (çoğu yarn resale)
- 5 new bucket: leasing, customer_claims, capex_investment, capex_disposal, supplier_prepayments

---

## Sonraki adım (bu tamamlanınca)

Internal Intelligence UI — dashboard'a "Operations Intelligence" tab'ı. Ama önce bu DB foundation'ının sağlam oturduğundan emin olalım.
