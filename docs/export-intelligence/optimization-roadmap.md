# Export Intelligence — Optimization Roadmap v1.1

> **Repo path:** `docs/export-intelligence/optimization-roadmap.md`  
> **Belge sürümü:** v1.1 (14 Mayıs 2026)  
> **Tasarım belgesinin (rationale-and-data-flow.md v1.0) tamamlayıcısı**  
> **Revizyon notu:** v1.0 → v1.1 değişiklikleri için bkz. §0

---

## İçindekiler

0. [Sürüm Geçmişi](#0-surum-gecmisi)
1. [Yönetici Özeti](#1-yonetici-ozeti)
2. [Üç Katmanlı Mimari Çerçevesi](#2-uc-katmanli-cerceve)
3. [ChatGPT Analizinin Değerlendirmesi](#3-chatgpt-degerlendirmesi)
4. [Eksik Kalan Boyutlar](#4-eksik-kalan-boyutlar)
5. [Önceliklendirme Matrisi (Impact × Effort)](#5-onceliklendirme-matrisi)
6. [5-Phase Implementation Roadmap](#6-implementation-roadmap)
7. [Mimari Genişleme](#7-mimari-genisleme)
8. [Claude API Kullanım Bölgesi](#8-claude-api-kullanim)
9. [Doğrulanması Gereken Sorular](#9-dogrulanmasi-gereken)
10. [Toplam Effort & Beklenen ROI](#10-toplam-effort-roi)
11. [Ek: ChatGPT v1 Hataları](#11-ek-chatgpt-hatalar)

---

## 0. Sürüm Geçmişi

### v1.1 (14 Mayıs 2026)
**ChatGPT ikinci-tur değerlendirmesi sonrası revize edildi.**

Değişiklikler:
1. **§2 YENİ:** Üç katmanlı mimari çerçevesi (Trade Flow / Competitive Positioning / Rayon Relevance) — her phase'in hangi katmana katkı yaptığını netleştirir
2. **§6 Phase X3 ↔ X4 SWAP:**
   - **Yeni X3** = Rayon Position Layer (eski X4 ana içeriği — own export overlay)
   - **Yeni X4** = Competitive Layer (eski X3 ana içeriği — multi-reporter + Eurostat mirror)
   - Gerekçe: "Önce kendini bil → sonra rakiplerle karşılaştır" karar değeri sıralaması
3. **§6 İçerik reorganizasyonu:**
   - Alert engine X4 → X5 (cross-platform yapısına daha uyumlu)
   - "Why this matters to Rayon" narrative X3 → X4 (Claude API integration competitive layer'la birleşti)
   - Eurostat mirror data X4 → X4 (aynı, competitive context'e ait)
4. **§5 Matrix:** Phase tag'leri güncellendi (toplam effort değişmedi)

### v1.0 (14 Mayıs 2026 — erken)
İlk versiyon. Tasarım belgesi v1.0'ın ardından ChatGPT v1 analizine cevaben hazırlandı.

---

## 1. Yönetici Özeti

Mevcut Export Intelligence sayfası **MVP seviyesinde** (4 KPI + 1 bar chart + 1 line chart). Veri omurgası (1,714 satır × 7 HS × 83 ülke × 12 ay) zengin, ama UI tarafında %20 oranında temsil ediliyor.

**Stratejik framing (v1.1 ile netleşti):**

Bu sayfanın değeri **daha fazla chart eklemekte** değil, şu dört soruya cevap vermesinde:
1. Hangi ürün ailesinde Türkiye pazar olarak güçleniyor / zayıflıyor?
2. Rayon bu trendin üstünde mi altında mı performans gösteriyor?
3. Hangi pazarda fiyat baskısı artıyor?
4. Hangi ürün grubunda rakip ülke baskısı yükseliyor?

Bu cevaplar 3 katmanlı bir mimaride üretilir (§2).

**Önerilen yol:** 5-phase implementation (~58-78 saat toplam), ilk phase 6-8 saatte tamamlanır ve sayfanın stratejik değerini iki katına çıkarır.

---

## 2. Üç Katmanlı Mimari Çerçevesi

```
┌─────────────────────────────────────────────────────┐
│ Layer 1 — Trade Flow                                │
│ (monthly value, $/kg implied, top destinations,     │
│  concentration, winners/losers)                     │
│                                                     │
│ Soru: "Türkiye'nin bu ürünü hangi pazara, ne fiyata │
│        ve ne hacimle ihraç ediyor?"                 │
└─────────────────────┬───────────────────────────────┘
                      │
                      ↓
┌─────────────────────────────────────────────────────┐
│ Layer 2 — Competitive Positioning                   │
│ (TR vs CHN/IND/PAK/VNM, mirror discrepancy,         │
│  multi-reporter benchmarks)                         │
│                                                     │
│ Soru: "Türkiye rakip ülkelere göre nerede?          │
│        Aynı pazara Çin ne fiyatla giriyor?"         │
└─────────────────────┬───────────────────────────────┘
                      │
                      ↓
┌─────────────────────────────────────────────────────┐
│ Layer 3 — Rayon Relevance                           │
│ (business line mapping, why-it-matters narrative,   │
│  rayon own export overlay, market share,            │
│  customer support)                                  │
│                                                     │
│ Soru: "Bu trend Rayon'un hangi divizyonu için ne    │
│        anlama geliyor? Biz pay kazanıyor muyuz?"    │
└─────────────────────────────────────────────────────┘
```

**Her phase'in katman katkısı:**

| Phase | Layer 1 | Layer 2 | Layer 3 |
|---|:---:|:---:|:---:|
| X1 Foundation | 🟢 Temel | ⚪ | 🟡 Başlar |
| X2 Market Depth | 🟢 Olgun | ⚪ | 🟡 Devam |
| **X3 Rayon Position** | ⚪ | ⚪ | 🟢 Olgun |
| **X4 Competitive** | ⚪ | 🟢 Olgun | 🟡 Tamamlanır |
| X5 Cross-Platform | ⚪ | ⚪ | 🟢 Tamamlanır + entegrasyon |

Bu çerçeve sayesinde her phase sonunda Mert şunu net görebilir: "Şu an hangi sorunun cevabını ekledim, hangi katman olgunlaştı."

---

## 3. ChatGPT Analizinin Değerlendirmesi

### 3.1 ✅ Sağlam Noktalar

| # | ChatGPT Önerisi | Niye Doğru | Phase |
|---|---|---|---|
| 1 | **HS 5510 eklenmesi** (artificial staple yarn — viscose/modal) | Rayon viscose ve modal kullanıyor (PV blend yarn araştırması). 5509 sentetik staple, 5510 yapay staple — ikisi farklı evren. | X1 |
| 2 | **3M rolling + YoY metrics** | Tek-ay MoM gürültülü; tasarım belgesi §7 limit #8'de zaten kabul | X1 |
| 3 | **Implied $/kg hesabı** | Tasarım §8.1'de Phase 2'de zaten vardı; ChatGPT aynı sonuca varmış | X1 |
| 4 | **Concentration metrics** (top-3/top-5, HHI) | Belarus/Rusya gibi yoğun pazarlar için risk metriği | X2 |
| 5 | **HS code → Rayon business line mapping** | Sayfanın "Rayon karar yüzeyi" olması için zorunlu | X1 |
| 6 | **Multi-source validation** (Eurostat Comext) | Mirror data ile undervaluation tespiti | X4 |
| 7 | **"Why this matters to Rayon" narrative** | P3 C1'de Market Signals'a uyguladığımız pattern | X4 |
| 8 | **Cross-platform integration** (Market Signals ↔ Export) | Tasarım §8.4 alarm sistemi ile aynı yön | X5 |
| 9 | **Claude API'yi narrative + exception için, ETL için deterministic** | Doğru iş bölümü | (tüm phase'ler) |
| 10 | **Winner/loser markets** (fastest growth/decline) | Pazar haritalama use case için kritik | X2 |
| 11 | **5903 erken önceliklendirme (v2'de)** | Rayon coating/lamination var — koşullu değil kesin Phase X1 | X1 |
| 12 | **Phase sıralaması revize (v2'de Rayon-first, sonra Competitive)** | "Önce kendini bil, sonra rakiplere bak" doğru karar değeri sırası | X3 → X4 |
| 13 | **3-katman framework (v2'de)** | Mental model her phase'in nereye katkı yaptığını netleştirir | §2 |

### 3.2 ⚠️ İhtiyatlı Yaklaşılması Gerekenler

| # | ChatGPT Önerisi | Eleştirim | Düzeltme |
|---|---|---|---|
| 1 | **HS 5516 eklenmesi** (woven artificial staple) | Rayon viscose/modal **woven** yapıyorsa relevant — doğrulanmalı | §9 Soru 1, evet ise Phase X1, hayır ise X2 |
| 2 | **HS 6005** (warp knit) / **6004** (elastane knit) | Rayon technical knit / performance yapıyor mu net değil | §9 Soru 2, koşullu Phase X2 |
| 3 | **TÜİK entegrasyonu** | JS-rendered, scraping çok zor | Yerine T.C. Ticaret Bakanlığı PDF + manuel sanity check |
| 4 | **ITC Trade Map** | Free tier 5 query/day, paid $675/yıl — ROI düşük | Phase X5'e ötele veya çıkar |
| 5 | **İHKİB/İTHİB narrative** | Otomatize edilemez (PDF/web) | Manuel monthly context note + Claude API summarization |
| 6 | **"Sprint" terminolojisi** | Solo dev, agile değil | "Phase" daha uygun |

### 3.3 ChatGPT v2 ile Tam Mutabık Olduğumuz Eksikler

ChatGPT v1'de atlamış, v2'de kabul etti:

| # | Eksik | v1 Durumu | v2 Durumu | Phase |
|---|---|:---:|:---:|:---:|
| A | Rayon'un kendi export verisi overlay'i | ❌ Atlanmış | ✅ Kritik | **X3** |
| B | Multi-reporter karşılaştırma (CHN/IND/PAK/VNM) | ❌ Atlanmış | ✅ Kritik | **X4** |
| C | 5903 erken önceliklendirme (koşullu değil, kesin) | ⚠️ Koşullu | ✅ Kesin | X1 |

---

## 4. Eksik Kalan Boyutlar (Detaylı)

### 4.1 🎯 [KRITIK] Rayon'un Kendi Export Verisi Overlay (Phase X3)

**Sorun:** Mevcut sayfada "Türkiye Spain'e $3.6M HS 5509 ihraç etti" gibi rakamlar var. Rayon'un kendi rakamları sistemde yok.

**Çözüm:** Yeni tablo `rayon_exports` + her HS × ülke × ay için iki rakam:
- `country_value_usd` (Türkiye toplam, Comtrade)
- `rayon_value_usd` (Rayon'un kendisi, internal)

**Türetilen metrik:** `rayon_market_share = rayon_value / country_value`

**Use case:** 
> Spain HS 5407 — Türkiye toplam $42M/ay, Rayon $0.8M/ay → **%1.9 pay**.  
> Pay 6 ay önce %3.1 idi → kayıp.  
> Sebep aranır: müşteri kaybı mı, rakip avantajı mı, fiyat sıkışıklığı mı?

Mevcut sayfanın hiçbir metriği bu kadar güçlü değil. **Bu yüzden Phase X3'te (eski plandaki X4'ten öne taşındı).**

**Veri kaynağı seçenekleri:**
- SAP/ERP'den aylık export raporu (en temiz)
- `lescon_sales` tablosunu inceleyip Rayon'un kendi rakamları içeriyor mu kontrol (§9 Soru 5)
- Manuel monthly entry (en pratik MVP)

### 4.2 🎯 [KRITIK] Multi-Reporter Karşılaştırma (Phase X4)

**Sorun:** UN Comtrade API'sinin **reporter parametresi değiştirilebilir**. Şu an sadece `reporterCode=792 (TUR)` kullanılıyor.

**Çözüm:** Rayon'un rakip ihracatçı ülkeleri için ayrı sorgu:
- CHN (Çin)
- IND (Hindistan)
- PAK (Pakistan)
- VNM (Vietnam)
- KOR (Güney Kore — niş)

**Türetilen metrik:** Aynı hedef ülkeye 4-5 ihracatçının karşılaştırması:
> Spain HS 5407 import — Türkiye'den $3.6M ($4.85/kg), Çin'den $12M ($3.20/kg), Hindistan'dan $4M ($3.95/kg)

**Use case:**
> Müşteri "Çinli rakipler $3 veriyor, sen $4 istiyorsun" diyor.  
> Dashboard'da: Spain'in Çin'den ortalama ithalatı $3.20/kg gerçekten — ama Türkiye ortalama $4.85/kg, fark **kalite ve teslim süresi** lehine  
> Pazarlık veriye dayanır.

**Effort:** ETL pipeline'da 4 ek `reporterCode` parametresi + storage 4x → ~6-8 saat.

### 4.3 [ÖNEMLİ] Mirror Data Validation (Phase X4)

**Sorun:** Türkiye'nin export verisi vs alıcı ülkenin import verisi farklı olabilir (undervaluation, denetim gecikmesi, transit trade).

**Çözüm:** Aynı HS × ülke × ay için iki kayıt:
- `value_export_tr` (TR reporter)
- `value_import_partner` (alıcı reporter — Eurostat Comext EU için)

**Türetilen metrik:** `discrepancy_pct = (value_import_partner - value_export_tr) / value_export_tr`

**Use case:**
- %5 fark normal (timing, currency)
- %20+ fark → policy/compliance anomalisi (Belarus için yaygın), transit trade, customs declaration issue
- Alarm sinyali Market Signals'a beslenir

**Effort:** ~6-8 saat (Eurostat API auth + ETL).

### 4.4 [ÖNEMLİ] Texhibition / Fuar Korelasyonu (Phase X2)

**Sorun:** Memory'de Texhibition scraper var (500 exhibitor, 9 rakip sinyal). Bu data Export Intelligence ile birleştirilmemiş.

**Çözüm:** Rakip Türk firmanın fuara katıldığı + sonraki 2-3 ayda o pazara TR ihracatının değişimi → indirek müşteri kazanım sinyali.

**Use case:**
> Texhibition Istanbul Eylül 2026 — Karsu Tekstil + Lenzing AG + Kipaş katıldı.  
> Sonraki ay Spain HS 5407 ihracatı %18 arttı → muhtemelen fuardan müşteri kazanıldı.  
> Sinyal: "Rayon'un fuarda daha aktif olmamasının maliyeti $X olabilir."

**Effort:** ~3-4 saat.

### 4.5 [DEĞERLİ] Currency / FX Overlay (Phase X5)

**Sorun:** TR ihracatı USD bazında ama TRY/USD kuru ihracat rekabetini etkiliyor.

**Çözüm:** Aylık TRY/USD ortalama vs aynı ay TR export hacmi (volume_kg) lag analysis.

**Pattern:** "TRY 1 ay önce %10 zayıfladığında, sonraki ay TR HS 5407 ihracat hacmi tipik olarak %3-5 artıyor (price competitiveness etkisi)."

**Effort:** ~4 saat.

### 4.6 [DEĞERLİ] Sanctions / Policy Event Awareness (Phase X4)

**Sorun:** Belarus, Rusya, İran gibi pazarlar için ticaret kısıtlamaları aylık dalgalanma yapıyor — mevcut sayfada görünmüyor.

**Çözüm:** Market Signals'tan gelen `tag='sanctions'` veya `tag='trade_policy'` signal'lar → Export Intelligence'ta o ülke kartına "policy context" badge.

**Effort:** ~2-3 saat.

### 4.7 [İLERİ] Customer-Bazlı Detay (Phase X5)

**Sorun:** Aggregate HS × ülke veri. Müşteri-bazlı kırılım yok.

**Çözüm:** `rayon_exports.customer_name` field — müşteri-bazlı drilldown.

**Effort:** ~6 saat (UI + detail layer).

---

## 5. Önceliklendirme Matrisi (v1.1)

**Score formülü:** `Impact² / Effort`

| # | Özellik | Impact | Effort (saat) | Score | Phase |
|---|---|---:|---:|---:|:---:|
| 1 | HS 5510 + 5903 ekle | 5 | 1.5 | 16.7 | **X1** |
| 2 | HS code → Rayon business line map | 5 | 1.5 | 16.7 | **X1** |
| 3 | Implied $/kg metric | 5 | 2 | 12.5 | **X1** |
| 4 | 3M rolling + YoY | 4 | 2 | 8.0 | **X1** |
| 5 | Rayon own export overlay | 5 | 8 | 3.1 | **X3** |
| 6 | "Market share %" metric | 5 | 4 | 6.3 | **X3** |
| 7 | Concentration metrics (top-3/5, HHI) | 4 | 2 | 8.0 | **X2** |
| 8 | Country drilldown sayfası | 4 | 3 | 5.3 | **X2** |
| 9 | Winner/loser markets ribbon | 4 | 3 | 5.3 | **X2** |
| 10 | Texhibition korelasyon | 4 | 4 | 4.0 | **X2** |
| 11 | Multi-reporter (CHN/IND/PAK/VNM) | 5 | 6 | 4.2 | **X4** |
| 12 | "Why it matters to Rayon" narrative | 5 | 3 | 8.3 | **X4** |
| 13 | Sanctions/policy context badge | 4 | 3 | 5.3 | **X4** |
| 14 | Eurostat mirror data validation | 4 | 6 | 2.7 | **X4** |
| 15 | Alert engine (drop/concentration/price) | 4 | 4 | 4.0 | **X5** |
| 16 | Market Signals bi-directional integration | 4 | 4 | 4.0 | **X5** |
| 17 | Customer-bazlı drilldown | 5 | 6 | 4.2 | **X5** |
| 18 | FX overlay | 3 | 4 | 2.3 | **X5** |

**Phase 1 toplam:** 7 saat → 4 yüksek-değer özellik  
**Phase 1 sonrası:** sayfa MVP'den **yetenekli karar yüzeyine** sıçrar  
**Tüm phase'ler toplam:** 58-78 saat (3-4 hafta yarı zamanlı)

---

## 6. 5-Phase Implementation Roadmap (v1.1 — SWAP UYGULANDI)

### Phase X1 — Foundation Layer
**Effort:** 6-8 saat  
**Layer katkısı:** L1 temel + L3 başlangıç  
**Hedef:** Sayfayı "trade dashboard"dan "Rayon karar yüzeyi"ne yükseltmek

| İş | Effort | Çıktı |
|---|---:|---|
| HS 5510 + 5903 ETL'e ekle, Comtrade backfill 12 ay | 1.5h | DB'de 2 yeni HS, ~500 yeni satır |
| `dim_hs_rayon_mapping` tablosu — her HS için business_line, material_family, importance_tier, relevance_note | 1.5h | Yeni dim tablosu, 9 HS için kayıt |
| Implied $/kg sütunu — view + metric card | 2h | `/api/exports` response'da yeni field, frontend new card |
| 3M rolling + YoY metrics — materialized view | 2h | `mv_export_metrics_monthly`, server.py query update |
| Frontend: business line tag her HS satırına, $/kg metrikleri görünür | 1h | UI revision |

**Görsel sonuç:** Mevcut sayfada her HS kartı yanında **"Rayon: Woven Synthetic" / "Knit Technical" / "Coating"** etiketi + her hücrede `$X.XX/kg` + 3M rolling line.

---

### Phase X2 — Market Depth Layer
**Effort:** 12-14 saat  
**Layer katkısı:** L1 olgunlaşır, L3 devam  
**Hedef:** "Hangi pazar nasıl gidiyor" sorusuna derinlemesine cevap

| İş | Effort | Çıktı |
|---|---:|---|
| Concentration metrics (top-3 share, top-5 share, HHI) | 2h | 3 yeni metric card |
| Country drilldown sayfası — bir ülkeye tıklayınca 12 aylık trend + tüm HS detayı | 3h | Yeni modal/page |
| Winner/loser markets ribbon — son 3 ay growth/decline top 5 | 3h | Yeni section |
| Top 10 bar chart'ı timeframe selectable yap (1M / 3M / 12M / YoY) | 2h | UI enhancement |
| Monthly trend chart'ı dropdown HS koduna tepki versin | 1h | UI bug fix |
| Texhibition correlation — fuar ayı + sonraki 3 ay ihracat değişimi cross-table | 3h | Yeni "fair impact" panel |

**Görsel sonuç:** Spain'e tıklayınca açılan panel: 12 aylık HS bazında trend + Karsu/Kipaş fuara gitti mi badge + concentration risk uyarısı.

---

### Phase X3 — Rayon Position Layer ⭐ [v1.0'dan SWAP]
**Effort:** 14-22 saat  
**Layer katkısı:** L3 olgunlaşır  
**Hedef:** "Rayon market trend'in üstünde mi altında mı?" sorusuna cevap

| İş | Effort | Çıktı |
|---|---:|---|
| `rayon_exports` tablosu + ETL/manuel entry mekanizması | 6h | DB tablosu + admin UI veya import script |
| `lescon_sales` mapping check — Rayon'un kendi mi yoksa Lescon müşteri mi (§9 Soru 5) | 2h | Source-of-truth decision |
| "Bizim payımız Türkiye'nin %X'i" metric — her HS × ülke için | 3h | Yeni metric col, "market share %" KPI |
| Divergence detection — Rayon vs market trend ayrışma uyarısı | 3h | Anomaly flagging |
| Frontend: her ülke kartında "Rayon payı %X (6 ay önce %Y)" overlay | 2h | UI enhancement |

**Görsel sonuç:** Her ülke kartında "Türkiye toplam $42M, Rayon $0.8M (pay %1.9, 6 ay önce %3.1 — **pay kaybı**)" + divergence alert.

**Kritik:** Bu phase'in başlaması için **§9 Sorular 4 ve 5** mutlaka cevaplanmış olmalı (veri kaynağı belirsizliği).

---

### Phase X4 — Competitive Layer ⭐ [v1.0'dan SWAP]
**Effort:** 12-16 saat  
**Layer katkısı:** L2 olgunlaşır + L3 narrative tamamlanır  
**Hedef:** "Rakip ülkelerle karşılaştırınca Rayon/Türkiye nerede?" sorusuna cevap

| İş | Effort | Çıktı |
|---|---:|---|
| Multi-reporter ETL — CHN/IND/PAK/VNM ekle | 6h | DB'de ~7000 ek satır (5 reporter × 7 HS × 12 ay × ~20 partner) |
| Multi-reporter karşılaştırma chart'ı — "Spain'e kim ne kadar gönderiyor" | 2h | Yeni section |
| Eurostat Comext partial integration — EU 27 mirror data | 6h | Yeni source, %20+ discrepancy alarm |
| Mirror data discrepancy alarm — alarm sinyali Market Signals'a | 1h | Bi-directional event |
| "Why this matters to Rayon" narrative — Claude API ile sentence generation | 3h | Her HS card için 1-2 cümle |
| Sanctions/policy context badge — Market Signals'tan join | 2h | UI badge |
| TR Ticaret Bakanlığı PDF aylık rapor — manuel periodic sanity check workflow | 1h | Notebook prosedürü |

**Görsel sonuç:** Her HS kartında: "Why it matters: Rayon woven divizyonu için PES filament fiyat benchmark'ı. Türkiye Spain'e $4.85/kg, Çin $3.20/kg, Hindistan $3.95/kg — Rayon teklif aralığı $4.50-$5.20 müsait."

---

### Phase X5 — Cross-Platform & Advanced
**Effort:** 12-16 saat  
**Layer katkısı:** Tüm katmanlar entegre olur  
**Hedef:** Platform içi sinyal akışı + müşteri-bazlı detay

| İş | Effort | Çıktı |
|---|---:|---|
| Alert engine — export drop / concentration spike / price compression | 4h | Alert table + sinyal akışı |
| Market Signals → Export Intelligence bi-directional integration | 3h | Cross-tab events |
| Yarn Intel ↔ Export Intelligence — "cost pressure + export weakness" birleşik sinyal | 3h | Cross-platform alert |
| Customer-bazlı drilldown (rayon_exports.customer_name detail) | 4h | Müşteri segmentasyonu |
| FX overlay — TRY/USD vs export hacmi lag analysis | 3h | Macro context panel |
| Negotiation support view — müşteri toplantısı öncesi 1-pager generator | 3h | PDF/print-friendly view |

**Görsel sonuç:** Satış müdürü "Spain müşteri X ile toplantı" der → 1-pager: müşteri X son 6 ay siparişi, Spain TR ortalama $/kg, Çin/Hindistan benchmark, Rayon teklif aralığı önerisi + Yarn Intel'den geçen ay yarn cost pressure uyarısı.

---

## 7. Mimari Genişleme

### 7.1 Yeni / Genişletilen DB Tabloları

```sql
-- (Phase X1) HS code → Rayon business mapping
CREATE TABLE dim_hs_rayon_mapping (
    hs_code            TEXT PRIMARY KEY,
    hs_description_en  TEXT,
    hs_description_tr  TEXT,
    rayon_business_line TEXT,    -- 'woven_synthetic', 'knit_technical', 'coated_laminated', 'yarn_upstream'
    material_family     TEXT,    -- 'polyester', 'viscose', 'cotton_blend', 'cellulosic', 'mixed'
    importance_tier     TEXT,    -- 'primary', 'secondary', 'niche', 'context'
    relevance_note      TEXT
);

-- (Phase X1) Pre-computed export metrics
CREATE MATERIALIZED VIEW mv_export_metrics_monthly AS
SELECT
    hs_code, partner_country, period,
    SUM(trade_value_usd) AS value_usd,
    SUM(netweight_kg) AS volume_kg,
    NULLIF(SUM(trade_value_usd),0) / NULLIF(SUM(netweight_kg),0) AS implied_usd_per_kg,
    AVG(SUM(trade_value_usd)) OVER (
        PARTITION BY hs_code, partner_country
        ORDER BY period ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rolling_3m_value,
    LAG(SUM(trade_value_usd), 12) OVER (
        PARTITION BY hs_code, partner_country ORDER BY period
    ) AS yoy_value,
    SUM(trade_value_usd) / NULLIF(
        SUM(SUM(trade_value_usd)) OVER (PARTITION BY hs_code, period), 0
    ) AS country_share_of_hs
FROM trade_flows
GROUP BY hs_code, partner_country, period;

-- (Phase X3) Rayon's own export records
CREATE TABLE rayon_exports (
    id              SERIAL PRIMARY KEY,
    period          TEXT NOT NULL,
    partner_country TEXT NOT NULL,
    hs_code         TEXT NOT NULL,
    customer_name   TEXT,
    rayon_value_usd NUMERIC,
    rayon_volume_kg NUMERIC,
    source          TEXT,
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(period, partner_country, hs_code, COALESCE(customer_name, ''))
);

-- (Phase X4) Multi-reporter — trade_flows schema same, just more rows
-- (Phase X5) Export alerts
CREATE TABLE export_alerts (
    id            SERIAL PRIMARY KEY,
    alert_type    TEXT NOT NULL,
    hs_code       TEXT,
    partner_country TEXT,
    period        TEXT,
    severity      TEXT,
    metric_value  NUMERIC,
    threshold     NUMERIC,
    message_tr    TEXT,
    triggered_at  TIMESTAMP DEFAULT NOW(),
    acknowledged  BOOLEAN DEFAULT FALSE
);
```

### 7.2 Yeni / Genişletilen API Endpoint'leri

| Endpoint | Phase | Purpose |
|---|:---:|---|
| `GET /api/exports` (extend) | X1 | Mevcut + implied_usd_per_kg, rolling_3m, yoy fields |
| `GET /api/exports/business_map` | X1 | dim_hs_rayon_mapping list |
| `GET /api/exports/country/{cc}` | X2 | Country drilldown |
| `GET /api/exports/concentration/{hs}` | X2 | Top-3/5/HHI per HS |
| `GET /api/exports/movers` | X2 | Winner/loser markets |
| `GET /api/exports/fair_impact` | X2 | Texhibition correlation |
| `GET /api/exports/rayon_share/{hs}/{partner}` | **X3** | **Rayon market share** |
| `GET /api/exports/divergence` | **X3** | **Rayon vs market divergence** |
| `GET /api/exports/competitor_reporters/{hs}/{partner}` | **X4** | Multi-reporter karşılaştırma |
| `GET /api/exports/narratives/{hs}` | **X4** | "Why this matters" cümleleri |
| `GET /api/exports/mirror/{hs}/{partner}` | **X4** | Mirror data discrepancy |
| `GET /api/exports/alerts` | X5 | Active alerts |
| `GET /api/exports/customer_drilldown/{customer}` | X5 | Customer-bazlı detay |

### 7.3 Frontend Bileşen Hiyerarşisi

```
ExportIntelligence (page-level)
├── HeaderSection
│   ├── BusinessLineFilter (X1)
│   └── TimeframeSelector (1M/3M/12M/YoY) (X2)
├── KpiStrip
│   ├── HsCard × 9 (X1: business_line label + implied $/kg)
│   ├── ConcentrationCard (X2)
│   ├── RayonShareCard (X3) ⭐
│   └── AlertsBadge (X5)
├── MainGrid
│   ├── TopDestinationsBar (mevcut, timeframe-aware) (X2)
│   ├── MonthlyTrendChart (X2)
│   ├── WinnersLosersRibbon (X2)
│   ├── FairImpactPanel (X2)
│   ├── RayonOverlayPanel (X3) ⭐
│   ├── MultiReporterPanel (X4)
│   └── NarrativePanel (X4)
├── CountryDetailModal (X2)
└── NegotiationSupportView (X5)
```

### 7.4 ETL Genişlemesi

```python
# scrapers/trade_flows.py — Phase X1 + X4 birleşik

HS_CODES = [
    # Core (mevcut)
    ("5407", "Woven synthetic filament", "primary", "woven_synthetic"),
    ("6006", "Other knit fabrics", "primary", "knit_technical"),
    # Eklenecek (X1)
    ("5510", "Yarn of artificial staple", "primary", "yarn_upstream"),
    ("5903", "Coated/laminated textiles", "primary", "coated_laminated"),
    # Mevcut secondary
    ("5509", "Yarn of synthetic staple", "secondary", "yarn_upstream"),
    ("5512", "Woven ≥85% synth staple", "secondary", "woven_synthetic"),
    ("5515", "Other woven synth staple", "secondary", "woven_synthetic"),
    ("6001", "Pile/velour knit", "niche", "knit_technical"),
    ("5402", "Synthetic filament yarn", "context", "yarn_upstream"),
    # Koşullu (§9 Soru 1, 2 cevabına göre)
    # ("5516", "Woven artificial staple", "secondary", "woven_cellulosic"),
    # ("6005", "Warp knit", "niche", "knit_technical"),
]

REPORTERS = [
    ("792", "TUR", "primary"),
    # Phase X4
    # ("156", "CHN", "competitor"),
    # ("699", "IND", "competitor"),
    # ("586", "PAK", "competitor"),
    # ("704", "VNM", "competitor"),
]
```

---

## 8. Claude API Kullanım Bölgesi

### 8.1 Claude API Kullanılacak

| Görev | Phase | Tip |
|---|:---:|---|
| Her HS kartı için "Why this matters to Rayon" 1-2 cümle | **X4** | LLM narrative |
| Anomaly açıklaması ("Spain share %30 düştü çünkü...") | X4 | Pattern → plain language |
| Customer negotiation talking points (1-pager) | X5 | Structured output |
| Aylık dış ticaret özet raporu (PDF) | X5 | Long-form generation |
| Cross-pattern detection ("price up, volume down → margin compression") | X5 | Reasoning |

### 8.2 Claude API Kullanılmayacak

| Görev | Niye |
|---|---|
| trade_flows tablosuna upsert | Deterministic ETL — psycopg2 yeter |
| 3M rolling / YoY hesabı | SQL window function |
| Concentration index (HHI) | SQL aggregate |
| Multi-reporter ETL | UN Comtrade API direct |
| Eurostat Comext fetch | REST + auth |
| Alert threshold check | Cron job + SQL |
| Rayon market share calculation | Pure math (rayon_value / country_value) |

### 8.3 Maliyet Tahmini

Phase X4 + X5 LLM kullanımı:
- 9 HS kartı × her ülke için 1 narrative ≈ 1000 token output × 50 = 50K token/refresh
- Haftada 1 refresh → ~200K token/ay
- Claude Haiku ile: ~$0.50/ay
- Sonnet ile: ~$5/ay

Minimum maliyet, yüksek değer.

---

## 9. Doğrulanması Gereken Sorular

| # | Soru | Karara Etkisi |
|---|---|---|
| 1 | Rayon viscose/modal staple **woven** kumaş üretiyor mu? | Evet → HS 5516 Phase X1, Hayır → Phase X2 koşullu |
| 2 | Rayon **warp knit** kumaş üretiyor mu? | Evet → HS 6005 Phase X2, Hayır → kapat |
| 3 | Coating/lamination tarafı ciroda **%X**? | %15+ → 5903 birincil (X1, zaten kabul), <%15 → X2 |
| 4 | **Rayon'un kendi export verisi nereden gelecek?** | SAP varsa direct integration, yoksa manuel entry UI — Phase X3 başlamadan netleşmeli |
| 5 | **`lescon_sales` tablosu Rayon'un kendi mi yoksa Lescon adlı müşteri mi?** | Rayon'un ise = X3 data source hazır |
| 6 | Birincil ihtiyaç: pazar haritalama mı, müşteri pazarlık desteği mi? | Haritalama → X3 öncelik (mevcut sıra), pazarlık → X4'ü öne çek |
| 7 | Müşteri-bazlı drilldown öncelikli mi yoksa ülke-bazlı yeterli mi? | Müşteri öncelikli → X5'i öne çek |
| 8 | Rayon hangi rakip ülkelerle gerçekten yarışıyor? | Çin kesin; Hindistan/Pakistan/Vietnam'dan hangileri sahada karşımıza çıkıyor? |

**Sorular 4 ve 5** Phase X3'e başlamadan önce mutlaka cevaplanmalı — yoksa veri kaynağı belirsiz kalır.

---

## 10. Toplam Effort & Beklenen ROI

### 10.1 Effort Özeti (v1.1)

| Phase | Effort (saat) | Cumulative |
|---|---:|---:|
| X1 — Foundation | 6-8 | 8 |
| X2 — Market Depth | 12-14 | 22 |
| **X3 — Rayon Position** | **14-22** | **44** |
| **X4 — Competitive** | **12-16** | **60** |
| X5 — Cross-Platform | 12-16 | 76 |
| **TOPLAM** | **~58-78 saat** | |

Yarı zamanlı (haftada 8-10 saat) → **6-10 hafta**.

### 10.2 Karar Değeri (Phase-by-Phase)

| Phase | Cevapladığı Yeni Soru |
|---|---|
| X1 | "Bu HS Rayon'un hangi divizyonu için relevant" + "Birim fiyat ne" |
| X2 | "Hangi ülkede yoğunlaşma riski var, hangi pazar büyüyor, fuar etkisi var mı" |
| **X3** | **"Rayon pay kazanıyor mu kaybediyor mu — biz market trend'in nerede"** |
| **X4** | **"Rakip ülkeler aynı pazara ne fiyatla giriyor — pazarlık leverage"** |
| X5 | "Belirli müşteri için 1-pager + cross-platform birleşik sinyal" |

### 10.3 Önerilen İlk Adım

**Phase X1 — 6-8 saat — Bu hafta sonu yapılabilir.**

Çıktı: Sayfanın stratejik değeri **MVP'den orta seviye karar yüzeyine** sıçrar.

Sonra Phase X2 (1-2 hafta) → sayfa **olgun seviye**ye gelir.

Phase X3 başlamadan **§9 Soru 4 + 5** cevaplanmalı (paralel olarak X1-X2 boyunca araştırılabilir).

---

## 11. Ek: ChatGPT v1 Hataları

| # | ChatGPT v1 İddiası | Gerçek | v2'de Düzeltildi mi? |
|---|---|---|:---:|
| 1 | "TÜİK sanity check için değerli" | JS-rendered, scraping zor; PDF raporu daha pragmatik | ✅ |
| 2 | "ITC Trade Map monthly/quarterly" | Free 5 query/day, paid $675/yıl — ROI düşük | ✅ |
| 3 | "Sprint 1, 2, 3..." | Solo dev, "Phase" daha uygun | ✅ |
| 4 | "İHKİB/İTHİB narrative Phase 3'te otomatize" | PDF/web — otomatize edilemez; manuel + Claude summarization | ✅ |
| 5 | "5516 ekleyin koşullu" | Koşullu doğru ama 5903 koşullu değil **kesin** Phase X1 | ✅ |
| 6 | Mirror data validation atlanmış | EU partner discrepancy %20+ alarm yüksek değer | ✅ |
| 7 | Rayon'un kendi export verisi atlanmış | En yüksek-impact tek metrik — "bizim pay %X" | ✅ |
| 8 | Multi-reporter karşılaştırma atlanmış | Pazarlık leverage için kritik | ✅ |
| 9 | Phase sıralaması (X3 multi-reporter / X4 own overlay) | Doğru sıra: X3 own / X4 multi-reporter (önce kendini bil) | ✅ |
| 10 | 3-katman framework yok | L1 Trade / L2 Competitive / L3 Rayon Relevance — net mental model | ✅ |

---

*Belge sürüm: v1.1 — 14 Mayıs 2026. Phase X1 implementasyonu sonrası v1.2 olarak revize edilecek (gerçek sonuçlar + öğrenilen dersler ile).*
