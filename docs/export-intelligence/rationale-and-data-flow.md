# Export Intelligence — Tasarım Belgesi

> **Repo path önerisi:** `docs/export-intelligence/rationale-and-data-flow.md`  
> **Belge sürümü:** v1.0 (14 Mayıs 2026)  
> **Hazırlayan:** Mert Övet (Rayon Intelligence Platform)

---

## İçindekiler

1. [Amaç ve Stratejik Konum](#1-amac-ve-stratejik-konum)
2. [Veri Kaynağı Seçimi — Niye UN Comtrade?](#2-veri-kaynagi-secimi)
3. [HS Kod Seçimi ve Mantığı](#3-hs-kod-secimi)
4. [Mimari ve Veri Akışı](#4-mimari-ve-veri-akisi)
5. [Veri Kapsamı](#5-veri-kapsami)
6. [Rayon İçin Somut Use Case'ler](#6-use-cases)
7. [Bilinen Limitasyonlar](#7-limitasyonlar)
8. [Roadmap ve Sonraki Adımlar](#8-roadmap)
9. [Operasyonel Notlar](#9-operasyonel-notlar)
10. [Doğrulanması Gereken Noktalar](#10-dogrulanmasi-gereken-noktalar)

---

## 1. Amaç ve Stratejik Konum

### 1.1 İş İhtiyacı

Rayon Tekstil ihracat-merkezli bir üreticidir. Üretim profili:

- **Knit divizyonu**: Entegre iplikten-kumaşa üretim (cotton, polyester, viscose, blend yarns → fabric)
- **Woven divizyonu**: Doğu Asya'dan ithal grey kumaş + Türkiye'de dyeing, coating, lamination finishing

Aktif ihracat pazarları:

| Bölge | Tipik müşteri |
|---|---|
| Doğu Avrupa | Polonya, Bulgaristan, Romanya garment manufacturers |
| Orta Doğu | Suudi Arabistan, BAE tender suppliers |
| Kafkasya | Azerbaycan, Gürcistan wholesalers |
| Rusya / Ukrayna | Hem garment hem tender |

Müşteri tarafında alış kararı veren kişiler genellikle:
- Diğer Türk tedarikçilerinin fiyat seviyesini bilir
- Rakip ülkelerin (Çin, Hindistan, Pakistan) ihracat trendini takip eder
- Pazarlık öncesi piyasa referansı kullanır

Rayon'un satış ekibinin bu konuşmalara hazırlıklı girmesi için **Türkiye'nin sentetik kumaş ihracat profilini somut, güncel ve karşılaştırılabilir bir veriye dayandırması gerekiyordu**. Kişisel network veya genel sektör söylentisi yerine, doğrulanabilir resmi istatistik temelli bir karar yüzeyi.

### 1.2 Hedeflenen Karar Soruları

Export Intelligence sekmesinin cevaplamayı amaçladığı dört ana soru tipi:

| Soru Tipi | Kullanıcı | Örnek Soru | Verdiği Karar |
|---|---|---|---|
| **A. Pazar Haritalama** | Yönetim (yeni pazar açılımı) | "Türkiye Kazakistan'a HS 5407 ihracatı son 12 ayda %42 arttı — biz neden orada zayıfız?" | Yeni pazar prioritization |
| **B. Rakip Benchmark** | Satış müdürü | "Türk ihracatçıların Ukrayna'ya ortalama $/kg değeri nedir, bizim teklif nerede duruyor?" | Pricing strategy |
| **C. Trend Takip** | Strateji / planlama | "Belarus HS 6006 talebi son 3 ayda düştü — sipariş kaybetmeden önce sinyal var mı?" | Erken uyarı |
| **D. Müşteri Fiyat Referansı** | Satış ekibi (görüşme öncesi) | "Mısırlı müşteri $2.40/m önerdi; Türkiye geneli Mısır'a ortalama $X/m — pazarlık kaldıracımız var mı?" | Spot pazarlık desteği |

> **Önemli not:** Bu dört soru tipinden hangisinin **birincil motivasyon** olduğu doğrulanması gereken bir noktadır (bkz. §10). MVP geliştirilirken **B + C** karması ana hedef olarak çalıştığı tahmin ediliyor, ancak Phase 2'de **A** (pazar haritalama) belki ön plana çıkacak.

### 1.3 Rayon İçin Yaratılan Değer Önermeleri

| Soyut Değer | Somut Çıktı |
|---|---|
| Bilgi asimetrisini azalt | Müşteri "rakipler $X/kg veriyor" derse, dashboard'da gerçek piyasa ortalaması anında görünür |
| Yeni pazar fırsatı tespiti | Türkiye'nin yıllık ihracatı artan ülkeler otomatik vurgulanır — Rayon orada yokken sebep aranır |
| Yaklaşan talep düşüşü sinyali | Mevcut müşteri ülkesindeki Türkiye toplam ihracatı azalıyorsa, Rayon siparişlerini kaybetmeden önce uyarı |
| Üst yönetime veri-temelli rapor | Aile şirketinde "bu pazara giriyoruz" tartışması — hissiyat değil rakam ile |
| Portfolio kanıtı | Mert'in AI/data freelance işine geçişinde — sektör + veri mühendisliği birleşimi |

---

## 2. Veri Kaynağı Seçimi

### 2.1 Aday Kaynak Karşılaştırması

İhracat verisi sağlayan ana kaynaklar değerlendirildi:

| Kaynak | Kapsam | Sıklık | Ücret | Türkiye verisi | API erişimi | Karar |
|---|---|---|---|---|---|---|
| **UN Comtrade** | 140+ ülke, tüm HS kodları | Aylık | Ücretsiz (free API key) | ✅ Tam | ✅ REST API | **SEÇİLDİ** |
| TİM (Türkiye İhr. Mecl.) | Sadece TR | Aylık | Ücretsiz | Alt mal grubu **Nisan 2025'te durduruldu** | ❌ (sadece web) | Atlandı (veri kesildi) |
| TÜİK | Sadece TR | Aylık | Ücretsiz | ✅ resmi kaynak | ❌ (JS-rendered web) | Atlandı (scraping zor) |
| ITC Trade Map | 220+ ülke | Aylık | Ücretsiz tier kısıtlı | ✅ | Limited | UN Comtrade üzerine alternatif (sonraki adımlar) |
| Eurostat (Comext) | Sadece EU | Aylık | Ücretsiz | Sadece mirror data (EU import from TR) | ✅ REST | Phase 2 — mirror cross-check |

### 2.2 UN Comtrade Seçim Gerekçesi

Üç ana neden:

1. **Kapsam genişliği**  
   Hem Türkiye'nin ihracatını (reporter=TUR) hem 140+ ülkenin ithalatını (mirror data) çapraz doğrulanabilir şekilde gösterir. Tek kaynaktan iki yön.

2. **API erişimi + Python entegrasyonu**  
   REST API + ücretsiz key (https://comtradeapi.un.org) + Python ile doğrudan entegre. Haftalık otomatik çekim GitHub Actions ile basit.

3. **HS-6 detay seviyesi**  
   Rayon'un ürün portföyüne uygun spesifik HS kodları seçilebiliyor (5407, 6006, vs.) — geniş "tekstil" agregatına gömülmek yerine.

### 2.3 Niye UN Comtrade Yerine TİM Kullanılmadı?

TİM (Türkiye İhracatçılar Meclisi) Nisan 2025 itibarıyla **alt mal grubu bazında ihracat verilerinin yayımını durdurdu**. Bu, HS kodu bazlı detayın TİM'den artık çekilemediği anlamına geliyor — yalnızca toplam veya sektör-seviye agregat veri kaldı. UN Comtrade bu boşluğu HS-6 granülaritesi ile doldurdu.

### 2.4 Phase 2 Veri Çeşitlendirmesi (Önerilen)

Tek-kaynak bağımlılığını azaltmak için:
- **Eurostat (Comext)**: EU ülkeleri için mirror data (Polonya, Bulgaristan, Romanya gibi Rayon pazarları için). UN Comtrade gecikmesini telafi edebilir.
- **ITC Trade Map**: Daha geniş ülke kapsamı, daha hızlı güncellenme.

---

## 3. HS Kod Seçimi

### 3.1 Seçilen 7 HS Kodu

Rayon'un üretim profili ile eşleşen kodlar:

| HS Kodu | Açıklama | Rayon Ürün Karşılığı | Önem |
|---|---|---|---|
| **5407** | Sentetik filament iplikten dokuma kumaşlar (polyester, naylon) | Polyester/naylon woven (**ana ürün**) | Birincil |
| **6006** | Diğer örme kumaşlar | Knit kumaş (**ikinci ana divizyon**) | Birincil |
| **5512** | Sentetik staple liflerden dokuma kumaşlar | Staple woven | İkincil |
| **5515** | Diğer dokuma sentetik staple | Karışım dokuma | İkincil |
| **6001** | İlme/havlu örme kumaşlar | Velour, pile knit | Niş |
| **5402** | Sentetik filament iplik | Hammadde (upstream görünürlük) | Upstream |
| **5409** | Sentetik filament kurdele | Niş ürün | Niş |

### 3.2 Seçim Mantığı

- **Birincil odak (5407 + 6006):** Rayon'un iki ana divizyonu — toplam cironun büyük çoğunluğu bu iki HS koduna giren ürünlerden geliyor.
- **İkincil (5512, 5515, 6001):** Yan ürün / niş segmentler — sinyal değeri var ama hacim düşük.
- **Hammadde takibi (5402):** Türkiye'nin polyester/naylon **iplik** ihracatı, yarın'ın **kumaş** kapasitesinin proxy göstergesi. Üretim eğilimini bir adım önce görebilmek için.
- **Geniş kapsam (5409):** Komple sentetik kumaş portföyünde boşluk bırakmamak için.

50+ tekstil HS kodu olmasına rağmen sadece bu 7 kod seçildi çünkü **sinyal/gürültü oranı** kritik. Çok geniş HS kapsamı:
- ETL maliyetini artırır (her HS × her ay × her ülke)
- Dashboard UI'sini karmaşıklaştırır
- Rayon'un ürettiği ürünle ilgisiz HS kodlarından gürültü ekler

### 3.3 Kapsam Genişletme Kriterleri (Phase 2)

Yeni HS kodu eklenmesi için kriter:
1. Rayon'un ürettiği veya ürettirdiği ürün ile doğrudan eşleşmeli
2. Türkiye'nin yıllık ihracatı belirli bir minimum hacmin üstünde olmalı (örn. $10M+/yıl)
3. Mevcut 7 koddan biri ile %80+ örtüşmesi olmamalı (duplicate sinyal kaçınma)

---

## 4. Mimari ve Veri Akışı

### 4.1 Pipeline

```
┌─────────────────────────────────┐
│ UN Comtrade API                 │
│ (https://comtradeapi.un.org)    │
└──────────────┬──────────────────┘
               │ haftalık (GitHub Actions cron)
               ↓
┌─────────────────────────────────┐
│ scrapers/trade_flows.py         │
│ (ETL — fetch + parse + load)    │
└──────────────┬──────────────────┘
               │
               ↓
┌─────────────────────────────────┐
│ trade_flows tablosu             │
│ (PostgreSQL, Railway)           │
└──────────────┬──────────────────┘
               │
               ↓
┌─────────────────────────────────┐
│ /api/exports endpoint           │
│ (FastAPI, dashboard/server.py)  │
└──────────────┬──────────────────┘
               │
               ↓
┌─────────────────────────────────┐
│ Export Intelligence Tab UI      │
│ (app.v6.js — frontend)          │
└─────────────────────────────────┘
```

### 4.2 `trade_flows` Tablo Şeması

```sql
CREATE TABLE trade_flows (
    id              SERIAL PRIMARY KEY,
    reporter_country TEXT NOT NULL,  -- 'TUR' (sabit, ileride çoğullaştırılabilir)
    partner_country TEXT NOT NULL,   -- 'USA', 'KAZ', 'BLR', vs.
    hs_code         TEXT NOT NULL,   -- '5407', '6006', vs.
    hs_description  TEXT,            -- "Woven fabrics of synthetic filament yarn"
    period          TEXT NOT NULL,   -- 'YYYY-MM' format, örn '2025-11'
    trade_value_usd NUMERIC,         -- USD cinsinden toplam ihracat değeri
    netweight_kg    NUMERIC,         -- Kg cinsinden net ağırlık (volume)
    source          TEXT DEFAULT 'UN_COMTRADE',
    scraped_at      TIMESTAMP DEFAULT NOW()
);

-- Beklenen index'ler (verify edilmeli):
CREATE INDEX idx_trade_flows_hs_period ON trade_flows(hs_code, period);
CREATE INDEX idx_trade_flows_partner ON trade_flows(partner_country);
CREATE UNIQUE INDEX idx_trade_flows_unique 
    ON trade_flows(reporter_country, partner_country, hs_code, period);
```

> **Doğrulama gerekli (§10):** Tablo şeması belleğe dayalı yazıldı; gerçek `db/schema.sql` veya migration dosyası incelenmedi.

### 4.3 ETL Pipeline — `scrapers/trade_flows.py`

**Çalışma akışı:**
1. UN Comtrade REST endpoint'e çağrı:
   ```
   GET https://comtradeapi.un.org/data/v1/get/C/M/HS
   ?reporterCode=792    # TUR
   &flowCode=X          # Export
   &cmdCode=5407        # Her HS için ayrı çağrı
   &period=202501,...   # Dönem listesi
   &subscription-key=COMTRADE_API_KEY
   ```
2. JSON response parse → trade_flows tablosuna upsert
3. `--months 12` flag ile cold-start backfill
4. Rate limit handling: free tier ~100-500 query/day; her HS × ay birden çok partner döner

**Auth:** `COMTRADE_API_KEY` (`.env` dosyasında, GitHub Actions secret olarak da var).

### 4.4 API Endpoint — `/api/exports`

`dashboard/server.py` içinde tanımlı.

**Beklenen response yapısı (verify edilecek):**
```json
{
  "summary": {
    "latest_period": "2025-11",
    "total_value_usd": 12500000,
    "mom_change_pct": 5.2,
    "top_destination": "USA"
  },
  "top_partners": [
    {"country": "USA", "value_usd": 4500000, "rank": 1},
    {"country": "KAZ", "value_usd": 3800000, "rank": 2},
    ...
  ],
  "monthly_trend": [
    {"period": "2024-12", "value_usd": ...},
    ...
  ]
}
```

> **Doğrulama gerekli:** Backend endpoint'in tam şekli ve query parametreleri (HS filter, country filter, date range) frontend kodundan teyit edilmeli.

### 4.5 Frontend — Export Intelligence Tab

Streamlit MVP (Mart 2026) sırasındaki yapı:

| Bileşen | İçerik |
|---|---|
| **Metric cards** (üst sıra) | HS 5407 & 6006 son ay toplam + MoM % değişim + top destination |
| **Horizontal bar chart** | Top 10 hedef ülke (HS kodu dropdown ile seçilebilir) |
| **Multi-line trend chart** | Seçilen HS kodları üzerinden aylık ihracat değeri zaman serisi |

FastAPI dashboard'a geçişte (Nisan-Mayıs 2026) UI muhtemelen revize edildi — mevcut state `dashboard/static/app.v6.js`'in `loadExports` veya benzer fonksiyonu incelenerek netleştirilmeli.

---

## 5. Veri Kapsamı

### 5.1 Mevcut Durum (14 Mayıs 2026 itibarıyla)

| Metrik | Değer |
|---|---|
| Toplam satır | 1,714 |
| Dönem aralığı | 2024-12 → 2025-11 (12 ay) |
| HS kodu sayısı | 7 |
| Partner ülke sayısı | 83 |
| Reporter | TUR (Türkiye, sabit) |
| Flow | Export only |
| Source | UN_COMTRADE |

### 5.2 Top Partner Ülkeler (Kasım 2025 örneği, HS 5407)

| Ülke | İhracat Değeri (USD) |
|---|---:|
| ABD | $4.5M |
| Kazakistan | $3.8M |
| Hollanda | $3.7M |
| Belarus | $3.6M |
| İspanya | $3.6M |
| Almanya | $3.3M |
| İngiltere | $2.9M |

**Stratejik gözlem:** Rayon'un mevcut pazarları (Belarus, Kazakistan, Rusya, Ukrayna gibi) Türkiye'nin toplam ihracat sıralamasında **top 20 içinde** görünüyor — bu, Rayon'un seçtiği pazarların Türkiye'nin makro ihracat haritasıyla **örtüşmesinin** kanıtı.

### 5.3 HS Kodu Bazında Toplam Değer (12 ay)

> **Doğrulama gerekli:** Bu rakamlar memory'de yok — `trade_flows` tablosundan SQL ile çıkartılmalı:
>
> ```sql
> SELECT hs_code, COUNT(*) AS rows, SUM(trade_value_usd)::bigint AS total_usd
> FROM trade_flows
> GROUP BY hs_code ORDER BY total_usd DESC;
> ```

---

## 6. Rayon İçin Somut Use Case'ler

### 6.1 Use Case: Pazar Haritalama

**Senaryo:** Yönetim toplantısında "yeni pazar açılım stratejisi" gündemde.

**Soru:** "Türkiye'nin son 12 ayda en hızlı büyüyen sentetik kumaş ihracat ülkeleri hangileri, biz orada mıyız?"

**Dashboard aksiyonu:**
1. Tab → Export Intelligence
2. HS 5407 + 6006 birleştir
3. Top 20 ülke listesini son 12 ay büyüme oranına göre sırala
4. Rayon'un mevcut müşterileri yok ülkeleri vurgula

**Çıktı:** Aile şirketinin bir sonraki açılım hedefini hissiyat değil veri ile destekle.

---

### 6.2 Use Case: Trend Takip — Erken Uyarı

**Senaryo:** Belarus, Rayon'un büyük müşterilerinden biri. Son aylarda siparişler azalmış görünüyor.

**Soru:** "Bu sadece Rayon'a özel mi, yoksa tüm Türkiye Belarus'a ihracatta düşüş mü yaşıyor?"

**Dashboard aksiyonu:**
1. Country filter → Belarus
2. HS 6006 + 5407 trend chart
3. Son 6 ay vs önceki 6 ay karşılaştırma

**Çıktı:**
- Eğer Türkiye geneli de düşüyorsa: makro problem (sanksiyonlar, kur, yerel talep) — Rayon'a özgü değil, alternatif pazar zorunlu
- Eğer sadece Rayon düşüyorsa: müşteri-spesifik problem (kalite, fiyat, rekabet) — satış ekibine "müşteri kaybediyoruz" sinyali

---

### 6.3 Use Case: Müşteri Görüşmesi Referansı (Pricing Leverage)

**Senaryo:** Mısırlı müşteri HS 5407 için $2.40/m teklif etti. Satış müdürü pazarlığa hazırlanıyor.

**Soru:** "Türkiye Mısır'a HS 5407 ortalama $/kg nedir?"

**Dashboard aksiyonu:**
1. Country filter → Egypt
2. HS 5407 filter
3. trade_value_usd / netweight_kg → ortalama $/kg

**Çıktı:**
- Türkiye Mısır'a ortalama $5.20/kg satıyorsa, $2.40/m muhtemelen düşük (m → kg dönüşüm gerek, kumaş gramajı ile)
- Pazarlıkta "piyasa ortalaması daha yüksek, kalite seviyemiz bunu hak ediyor" söylemi veri-destekli

---

### 6.4 Use Case: Rakip Benchmark (Implicit)

**Senaryo:** Müşteri "Çinli rakipler $X veriyor, sen $Y istiyorsun" diyor.

**Soru:** "Doğru mu, Çin'den o ülkeye gerçekten $X civarında ihracat var mı?"

**Dashboard aksiyonu (Phase 2 ile mümkün):**
- Şu an Comtrade'de **reporter=TUR** sabit. Phase 2'de reporter çoğullaştırılırsa Çin, Hindistan, Pakistan'ın aynı pazara ihracat fiyatları karşılaştırmalı görülebilir.

**Çıktı:** Müşteri iddiasını doğrula/çürüt.

---

## 7. Bilinen Limitasyonlar

| # | Limit | Etki | Mitigation |
|---|---|---|---|
| 1 | **Veri gecikmesi 1-2 ay** | Kasım verisi Ocak'ta uygun olur. Son ayın canlı durumu görülemez | Trend analizi için yeterli; spot decision için Texhibition + haber sinyalleri ile birleştir |
| 2 | **HS-6 seviyesi** | 5407.42 vs 5407.43 alt detay sınırlı | Rayon'un ürün karması zaten HS-6'da kabaca temsil ediliyor — yeterli detay |
| 3 | **FOB/CIF ayrımı yok** | Kullanılan ihracat değeri toplam (terim ayrımsız) | Phase 2'de Comtrade `customsCode` ile bölünebilir |
| 4 | **Sadece volume + value, fiyat değil** | Implied $/kg = value ÷ volume, kabaca | Volume sıfır veya çok düşük olduğunda ilgisiz rakam çıkar; outlier filter gerek |
| 5 | **Mirror discrepancy** | TR export verisi vs alıcı ülke import verisi farklı (timing, undervaluation, ofset programları) | Phase 2'de Eurostat mirror data ile cross-check |
| 6 | **Şirket-bazlı bilgi yok** | HS × ülke aggregat — hangi TR firması ne kadar ihracat ettiği gizli | Texhibition exhibitors + competitor_monitor ile bir nebze indirek tespit |
| 7 | **TR-only reporter** | Şu an sadece Türkiye'nin ihracatı; Çin/Hindistan'ın aynı pazara ihracatı karşılaştırılamıyor | Phase 2'de reporter genişlet (CHN, IND, PAK, VNM) |
| 8 | **Volatil aylık dalga** | Tek bir ay anomalisi yanıltıcı | 3-aylık veya 6-aylık moving average + trend line |

---

## 8. Roadmap ve Sonraki Adımlar

### Phase 2 (Önerilen — kısa-orta vadeli, ~1-2 ay)

| # | Özellik | Effort | Değer |
|---|---|---|---|
| 8.1 | **Implied $/kg hesabı** sütunu (trade_value_usd / netweight_kg) | 1-2 saat | Müşteri pazarlığı için temel metrik |
| 8.2 | **Ülke-bazlı drilldown sayfası** (Belarus, Kazakistan, Rusya, Ukrayna detay) | 4-6 saat | Rayon'un kritik pazarları için derinleşme |
| 8.3 | **Eurostat (Comext) entegrasyonu** — EU mirror data | 6-8 saat | UN Comtrade gecikmesi telafi + cross-check |
| 8.4 | **Alarm sistemi**: %20+ MoM düşüş → Market Signals tab'ına otomatik sinyal | 2-3 saat | Erken uyarı | 
| 8.5 | **3-aylık moving average + trend line** | 1 saat | Volatil aylık dalga sorunu mitigasyon |

### Phase 3 (Stratejik — orta-uzun vadeli, 3+ ay)

| # | Özellik | Açıklama |
|---|---|---|
| 8.6 | **Multi-reporter karşılaştırma** | CHN, IND, PAK, VNM gibi rakip TR ülkelerinin aynı pazara ihracatı yan yana |
| 8.7 | **Rayon kendi export verisi ile karşılaştırma** | `lescon_sales` / yeni `rayon_exports` tablosundan Rayon'un kendi rakamları → "Bizim payımız Türkiye geneline göre %X" |
| 8.8 | **CIF/FOB ayrımı** | `customsCode` parametresi ile teslim şartı bazında ayrı |
| 8.9 | **Price seasonality detection** | HS × ülke × ay matrix → otomatik mevsimsel desen tespiti |
| 8.10 | **TR top exporters tahmini** | Texhibition + competitor_monitor + market_signals birleştirip kabaca firma-bazlı pay tahmini |

### İlişkili olduğu diğer modüller

- **Market Signals**: Phase 2.4 (alarm sistemi) çıktısı buraya beslenir
- **Price Intelligence**: $/kg trendleri burada raw material maliyetiyle çapraz okunabilir (margin pressure analizi)
- **Yarn Intelligence**: Sentetik kumaş ihracatı = polyester/PA hammadde tüketim proxy'si

---

## 9. Operasyonel Notlar

| Parametre | Değer |
|---|---|
| Refresh sıklığı | **Haftalık** (Comtrade aylık güncellenir, daily gereksiz) |
| Çalıştırma yeri | GitHub Actions cron (`.github/workflows/weekly_trade_flows.yml` — doğrulanmalı) |
| API key env var | `COMTRADE_API_KEY` (.env + GitHub Secrets) |
| Cold-start backfill | İlk yükleme `--months 12` → 1,714 satır |
| Ortalama query süresi | ~30 sn per HS × ülke batch (rate limit kontrolü) |
| Idempotency | UPSERT (UNIQUE INDEX on reporter+partner+hs_code+period) |
| Hata yönetimi | Rate limit → exponential backoff; partner missing → skip + log |

---

## 10. Doğrulanması Gereken Noktalar

Bu belge memory + konuşma geçmişine dayalı yazıldı. Mert'in ya da kodun teyit etmesi gereken noktalar:

| # | Konu | Doğrulama Yöntemi |
|---|---|---|
| ✅ 1 | **Birincil motivasyon** hangisi? (A/B/C/D) | Mert kararı netleştirsin (§1.2) |
| ✅ 2 | `trade_flows` tablo şeması — gerçek `db/schema.sql` ile birebir mi? | `SELECT column_name, data_type FROM information_schema.columns WHERE table_name='trade_flows'` |
| ✅ 3 | `/api/exports` endpoint response yapısı | `curl http://localhost:8000/api/exports \| jq` |
| ✅ 4 | Frontend tam UI durumu (FastAPI versiyonunda neye benziyor) | `dashboard/static/app.v6.js` içinde `loadExports` veya benzer fonksiyon |
| ✅ 5 | GitHub Actions weekly cron dosyası var mı? | `ls .github/workflows/*trade*` veya `*comtrade*` |
| ✅ 6 | UNIQUE INDEX gerçekten var mı? | `\d trade_flows` (psql) |
| ✅ 7 | `scrapers/trade_flows.py` mevcut implementation detayı | Dosyayı oku |
| ✅ 8 | HS kodu sayısı 7 mi 6 mı? (Memory'de iki kez farklı bilgi geçti: 6 ve 7) | `SELECT DISTINCT hs_code FROM trade_flows` |

Bu 8 noktayı netleştirmek için `inspect_export.py` benzeri bir DB + kod tarama script'i çalıştırılabilir.

---

## Ek A — Komşu Modüllerle İlişki Diyagramı

```
                ┌───────────────────────┐
                │  Yarn Intelligence    │
                │  (polyester/PA/cotton │
                │   raw material price) │
                └───────────┬───────────┘
                            │ raw material cost
                            ↓
┌───────────────────────────────────────────────┐
│  Price Intelligence                           │
│  (SunSirs, IndexMundi → margin pressure)      │
└───────────────────┬───────────────────────────┘
                    │ price floor
                    ↓
┌───────────────────────────────────────────────┐
│  Export Intelligence ← THIS DOCUMENT          │
│  (UN Comtrade → market value $/kg, demand)    │
└───────────────────┬───────────────────────────┘
                    │ MoM drop > 20%
                    ↓
┌───────────────────────────────────────────────┐
│  Market Signals                               │
│  (alarms, competitor moves, trade events)     │
└───────────────────────────────────────────────┘
                    │
                    ↓
            Decision support
            (sales team, management)
```

---

## Ek B — Referanslar

- **UN Comtrade**: https://comtradeplus.un.org
- **UN Comtrade API docs**: https://comtradeapi.un.org
- **HS Code reference (WCO)**: https://www.wcoomd.org/en/topics/nomenclature
- **TİM (alt mal grubu durduruldu)**: https://www.tim.org.tr
- **Eurostat Comext**: https://ec.europa.eu/eurostat
- **ITC Trade Map**: https://www.trademap.org

---

*Belge sürüm: v1.0 — 14 Mayıs 2026. Sonraki revizyon §10 doğrulamaları sonrası v1.1 olarak commit edilecek.*
