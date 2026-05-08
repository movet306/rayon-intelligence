# Phase E — Market Signals Roadmap

> **Status:** Draft v1.0 · Created 8 May 2026
> **Owner:** Mert Övet
> **Repo:** [movet306/rayon-intelligence](https://github.com/movet306/rayon-intelligence)
> **Predecessor:** Phase D — Yarn Intelligence (closed 8 May 2026, 5 commits)

---

## 1. North Star

Bu bölümün en yüksek potansiyeli **"textile news monitor"** olmak değil, **"Rayon exposure intelligence layer"** olmak.

Hedef değer denklemi:

```
raw news → classified signal → Rayon exposure → priority → action
```

Şu an birinci ve ikinci adımdayız (haber çekme + sınıflandırma). Asıl operasyonel değer üçüncü ve dördüncü adımdadır (Rayon'a etkisi + aksiyon önerisi).

**Phase E'nin sonunda her sinyal kullanıcıya şu üç soruyu cevaplamış olmalı:**

1. Bu olay Rayon'a hangi koldan dokunuyor? (raw material / export / competitor / regulation / sustainability)
2. Hangi iş birimini ve malzeme ailesini etkiliyor? (woven/knit/technical/laminated × polyester/nylon/viscose/modal/cotton/FR/membrane)
3. Bu hafta ne yapmalıyım? (monitor / call supplier / re-price / re-quote / watch account)

---

## 2. Mevcut Durum Diagnostiği (8 May 2026)

### 2.1 Pipeline Sağlığı

| Metrik | Değer | Yorum |
|---|---|---|
| Toplam news_items (son 30 gün) | 330 | Sağlıklı ingest |
| Source breakdown | just_style 170 / textilegence 119 / fibre2fashion 25 / tekstil_teknik 16 | just_style dominant |
| Hepsi analyze edilmiş mi | 330/330 ✅ | LLM analiz çalışıyor |
| `published_at` doluluğu | 0/330 ❌ | Scraper bug — tüm article'lar NULL |
| `signal_category` doluluğu | 26/118 (sadece market_signals'da) | LLM prompt zorunlu listede değil |
| Threshold geçen article (≥0.25) | 40/330 (%12) | %88 noise rate |
| Son 13 günde threshold geçen | 1 article | Sektör sakin, **pipeline kopuk DEĞİL** |
| market_signals son kayıt | 2026-04-25 | Doğru çalışıyor, akış seyrek |

**Kritik teyit:** "13-day signal hiatus" bir bug değil. Diagnostic kanıtı: son 13 günde threshold geçen tek 1 article (Şişman flame-retardant news) market_signals tablosuna düzgün INSERT edilmiş. ARTICLES WITH NO SIGNAL: 0.

### 2.2 Veri Modeli Eksiklikleri

| Eksiklik | Durum | Etki |
|---|---|---|
| `companies` tablosunda 32 firma'nın hepsi `competitor` kategorisinde | Enum mevcut (competitor/customer/supplier/association/other), ama **kullanılmıyor** | SASA "rakip" gibi saklanıyor → semantically yanlış |
| Her sinyale "Rayon için anlamı" alanı yok | LLM prompt'unda field yok | Feed haber panosundan öteye geçemiyor |
| Entity-role bilgisi sinyallerde yok | LLM extraction yapmıyor | "Toray hangi rolde mention edildi?" cevaplanamıyor |
| Affected business line / material family çoğu kayıtta NULL | Optional field | Rayon exposure mapping yapılamıyor |

### 2.3 Source Universe Yetersizliği

Mevcut 4 kaynak generic textile news. Decision-grade kaynaklar yok:

- ❌ Türk resmi kaynaklar (İHKİB, İTHİB, Ticaret Bakanlığı duyuruları)
- ❌ EU policy kaynakları (EURATEX, ECHA, EC Textiles Strategy)
- ❌ World trade kaynakları (WTO, USTR)
- ❌ Şirket bazlı resmi newsroom (SASA, Korteks, UNIFI, Aquafil)

---

## 3. Stratejik Yaklaşım

### 3.1 Yaklaşım Önceliklendirmesi

**Önce semantics, sonra source.** Mevcut 4 kaynak %88 noise üretirken yeni kaynak eklemek değil, mevcut sinyalleri Rayon perspektifinde zenginleştirmek önceliklidir. LLM prompt'u sertleştirilmeden eklenen İHKİB/EURATEX article'ları yine yarı-jenerik özetler üretir.

**Sıralama:** P0 (reliability) → P1 (entity & relevance) → P2 (source expansion) → P3 (UI) → P4 (productization)

### 3.2 Faydalanılan Mimari Avantaj

`llm_analyzer.py:79` competitor list'i DB'den dinamik çekiyor. Yani:

- Yeni entity INSERT'i kod deploy gerektirmez
- Yarınki 11:00 daily run'da yeni firmalar otomatik prompt'a girer
- Bu, Phase E'nin entity expansion adımını bir SQL script'e indirir

---

## 4. Phased Plan

### P0 — Quick Wins · 1-2 gün · ~5 saat

**Goal:** Mevcut pipeline'ı kalibre et, ucuz fix'leri kapat. Yeni kod yazmadan mevcut sistem kalitesini yükselt.

#### Tasks

1. **`published_at` scraper fix** — 4 scraper için
   - `fibre2fashion_scraper.py`, `just_style_scraper.py`, `tekstilteknik_scraper.py`, `textilegence_scraper.py`
   - Sıralı parse stratejisi: `<meta property="article:published_time">` → JSON-LD `datePublished` → `<time datetime="...">` → URL'den regex
   - Backfill script (`scripts/backfill_published_at.py`) — son 330 article için yeniden parse

2. **LLM prompt tightening** — `scrapers/llm_analyzer.py`
   - `signal_category`, `material_form`, `affected_segment` alanlarını **REQUIRED** olarak işaretle
   - Hâlâ NULL gelirse fallback: `signal_category = 'OTHER'`, server-side validation
   - Test: 5 article üzerinde dry-run

3. **Existing enum'ı kullanmaya başla**
   - SQL: `UPDATE companies SET category='customer' WHERE name='TDU Savunma';` (varsayılan değil, doğrula önce)
   - Sektör derneklerini ayır (varsa)

#### Files Affected

```
scrapers/fibre2fashion_scraper.py
scrapers/just_style_scraper.py
scrapers/tekstilteknik_scraper.py
scrapers/textilegence_scraper.py
scrapers/llm_analyzer.py
scripts/backfill_published_at.py (yeni)
```

#### Definition of Done

- [ ] Yeni article'larda `published_at` fill rate > %80
- [ ] Backfill sonrası mevcut 330 article'da fill rate > %50
- [ ] Yeni signal'larda `signal_category` NULL rate < %5
- [ ] companies tablosunda en az 1 entity reclassify (TDU Savunma örneği)
- [ ] Daily run yarınki 11:00'de problem üretmeden tamamlanır

#### Risk

- Düşük. Tüm değişiklikler additive, mevcut akışı bozmaz. Backfill idempotent olmalı (UPDATE WHERE published_at IS NULL).

---

### P1 — Entity & Relevance Refactor · 3-5 gün · ~14 saat

**Goal:** ChatGPT analizinin en güçlü içgörüsü. Entity model'i genişlet, LLM prompt'una Rayon exposure layer ekle, 15 priority entity'i doğru kategorilerle ekle.

#### Sub-tasks

##### P1-A · DB Migration: Entity Taxonomy Expansion

**Migration:** `migrations/010_entity_taxonomy_expansion.sql`

```sql
-- Add three array columns to companies table
ALTER TABLE companies
  ADD COLUMN signal_priority_profile text[] DEFAULT ARRAY[]::text[],
  ADD COLUMN business_line_tags text[] DEFAULT ARRAY[]::text[],
  ADD COLUMN material_tags text[] DEFAULT ARRAY[]::text[];

-- Allowed values (validated at application layer; no enum to keep flexibility)
-- signal_priority_profile: cost / demand / regulation / sustainability / export
-- business_line_tags: woven / knit / technical / laminated
-- material_tags: polyester / nylon / viscose / modal / cotton / FR / membrane

-- Backfill existing 32 competitors with sensible defaults
UPDATE companies
SET signal_priority_profile = ARRAY['demand', 'export'],
    business_line_tags = ARRAY['woven', 'knit'],
    material_tags = ARRAY['polyester', 'nylon']
WHERE category = 'competitor' AND signal_priority_profile = ARRAY[]::text[];

-- Index for tag-based filtering
CREATE INDEX idx_companies_signal_priority ON companies USING GIN (signal_priority_profile);
CREATE INDEX idx_companies_business_line ON companies USING GIN (business_line_tags);
CREATE INDEX idx_companies_material ON companies USING GIN (material_tags);
```

##### P1-B · LLM Prompt Schema Expansion

`scrapers/llm_analyzer.py` system prompt'una eklenecek REQUIRED output fields:

```json
{
  "rayon_why_it_matters": "string (TR, 1 cümle, REQUIRED, <140 char)",
  "affected_business_line": "woven|knit|technical|laminated|none (REQUIRED)",
  "affected_material_family": "polyester|nylon|viscose|modal|cotton|FR|membrane|none (REQUIRED)",
  "commercial_exposure_type": "raw_material|export|competitor|regulation|sourcing|sustainability|none (REQUIRED)",
  "entity_name": "string (REQUIRED if entity mentioned, else null)",
  "entity_role": "competitor|supplier|customer|association|regulator|benchmark (REQUIRED if entity_name not null)"
}
```

`market_signals` tablosuna gerekli kolon eklemeleri:

```sql
-- Migration 011 alt-step
ALTER TABLE market_signals
  ADD COLUMN rayon_why_it_matters text,
  ADD COLUMN commercial_exposure_type text,
  ADD COLUMN entity_role text;
```

##### P1-C · Priority Entity Seed (15 firma)

**Migration:** `migrations/011_priority_entity_seed.sql`

| # | Entity | category | country | signal_priority_profile | business_line_tags | material_tags |
|---|---|---|---|---|---|---|
| 1 | SASA Polyester ⭐ | supplier | TR | cost, sustainability | — | polyester, FR |
| 2 | Korteks (Zorlu) | supplier | TR | cost, sustainability | knit | polyester |
| 3 | Indorama Ventures | supplier | TH | cost | — | polyester |
| 4 | Reliance Industries | supplier | IN | cost | — | polyester |
| 5 | Hyosung TNC | supplier | KR | cost, demand | knit, technical | nylon, polyester |
| 6 | Toray Industries | supplier | JP | demand, sustainability | technical, laminated | polyester, nylon, membrane |
| 7 | UNIFI / Repreve | supplier | US | sustainability | knit, woven | polyester |
| 8 | Aquafil / ECONYL | supplier | IT | sustainability | technical, knit | nylon |
| 9 | Yeşim Tekstil | competitor | TR | export, demand | knit | polyester, cotton |
| 10 | Bossa Tekstil | competitor | TR | export | woven | cotton, polyester |
| 11 | Söktaş | competitor | TR | export | woven | cotton |
| 12 | W.L. Gore | competitor | US | demand | technical, laminated | membrane |
| 13 | İHKİB | association | TR | export, regulation | woven, knit, technical, laminated | — |
| 14 | EURATEX | association | BE | regulation, sustainability | woven, knit, technical, laminated | — |
| 15 | ECHA | regulator | FI | regulation | technical, laminated | FR, membrane |

#### Files Affected

```
migrations/010_entity_taxonomy_expansion.sql (yeni)
migrations/011_priority_entity_seed.sql (yeni)
migrations/012_market_signals_exposure_columns.sql (yeni)
scrapers/llm_analyzer.py (system prompt + output parsing)
scripts/reanalyze_recent_articles.py (yeni — son 30 gün için yeni schema ile re-run)
```

#### Definition of Done

- [ ] Migration 010, 011, 012 prod'da uygulandı
- [ ] 15 priority entity DB'de mevcut
- [ ] companies count: 32 → 47 (32 mevcut + 15 yeni)
- [ ] LLM analyzer yeni schema'yı üretiyor
- [ ] Test: 10 article üzerinde yeni schema validation %100 dolu
- [ ] Reanalyze script çalıştırıldı: son 30 gün article'ları yeni alanlarla zenginleştirildi
- [ ] `companies.category` dağılımı: en az 4 farklı kategori dolu (competitor + supplier + association + regulator)

#### Risk

- Orta. LLM prompt değişimi token cost'u %10-15 artırabilir (input prompt uzar). Daily cost mevcut ~$0.01 → ~$0.012. Önemsiz.
- Backward compat: yeni kolonlar nullable, eski signal'lar etkilenmez.

---

### P2 — Source Expansion · 5-7 gün · ~22 saat

**Goal:** Decision-grade kaynaklar ekle. Generic news değil, policy/upstream/regulation odaklı kaynaklar.

#### Tier A · İlk Eklemeler (en yüksek ROI)

##### Tier A.1 · İHKİB News Scraper

- **URL:** https://www.ihkib.org.tr/haberler-duyurular
- **Frekans:** Günlük
- **Beklenen volume:** ~2-5 article/hafta
- **Değer:** TR ihracat policy, sektör narrative, ihracatçı birliği duyuruları
- **Tech:** BeautifulSoup + requests (büyük ihtimalle JS-light site)
- **File:** `scrapers/ihkib_scraper.py`

##### Tier A.2 · EURATEX News + Economic Update

- **URL:** https://euratex.eu/news/ ve https://euratex.eu/economic-update/
- **Frekans:** Haftalık
- **Beklenen volume:** ~3-5 article/hafta
- **Değer:** EU tekstil policy, ESPR/PFAS lobi pozisyonları, ihracat baskısı analizi
- **Tech:** BeautifulSoup veya RSS feed varsa direkt
- **File:** `scrapers/euratex_scraper.py`

##### Tier A.3 · Ticaret Bakanlığı Tekstil Duyuruları

- **URL:** https://ticaret.gov.tr/haberler (filter: tekstil)
- **Frekans:** Olay-odaklı
- **Beklenen volume:** ~1-3 article/ay
- **Değer:** İthalat denetimi, kotalar, AB uyum mevzuatı
- **Tech:** BeautifulSoup + keyword filter
- **File:** `scrapers/ticaret_bakanligi_scraper.py`

#### Tier B · Sonraki Eklemeler

| Source | URL | Volume | Değer |
|---|---|---|---|
| ECHA Restriction Proposals | echa.europa.eu/restrictions-under-consideration | ~1-2/ay | PFAS, FR chemical kısıtlamaları |
| İTHİB News | ithib.org.tr/haberler | ~2-3/hafta | Hammadde/iplik tarafı |
| SASA Newsroom | sasa.com.tr/tr/haber-merkezi | ~1-2/ay | Direct upstream signal |
| Korteks Press | korteks.com.tr/haberler | ~1-2/ay | TR polyester filament direct |

#### Tier C · Episodic / Low Frequency

| Source | URL | Volume | Değer |
|---|---|---|---|
| WTO Textile Updates | wto.org/english/tratop_e/texti_e/texti_e.htm | ~1/ay | Global trade diversion |
| USTR Textile Actions | ustr.gov/issue-areas/textiles | Event-driven | ABD safeguard, tariff |

#### Files Affected

```
scrapers/ihkib_scraper.py (yeni)
scrapers/euratex_scraper.py (yeni)
scrapers/ticaret_bakanligi_scraper.py (yeni)
.github/workflows/daily_intelligence.yml (yeni scraper'ları ekle)
dashboard/server.py (source filter UI desteği)
```

#### Definition of Done

- [ ] En az 3 Tier A scraper canlı ve daily run'a eklenmiş
- [ ] news_items.source kolonunda yeni source kodları görünüyor (ihkib / euratex / ticaret_bakanligi)
- [ ] LLM analyzer yeni source'ları işleyebiliyor (özellikle TR sources)
- [ ] Bir hafta sonra: yeni source'lardan en az 5 article promote edilmiş

#### Risk

- Orta. Site değişiklikleri scraper kırabilir; her scraper için failed_jobs tracking şart.
- Türkçe natural language LLM prompt'ta zaten destekli, yeni problem değil.

---

### P3 — UI/UX Upgrade · 3-5 gün · ~14 saat

**Goal:** Frontend'i Rayon exposure odaklı hâle getir. "Haber panosu" görünümünden "decision board" görünümüne geçiş.

#### Tasks

1. **"Rayon için anlamı" satırı (zorunlu kart elemanı)**
   - `_renderSignalCard` içinde yeni satır
   - Italic/farklı renkte, "💡 Rayon için anlamı:" prefix
   - Boş ise kartı dim göster (data quality cue)

2. **Exposure chips**
   - Chip türleri: 🧵 Raw Material / 🌍 Export / 🏢 Competitor / ⚖️ Regulation / 🔬 Technical
   - Geography sub-chips: 🇺🇸 US / 🇪🇺 EU / 🇪🇬 Egypt / 🇹🇷 TR
   - `commercial_exposure_type` + entity location'dan derive

3. **Entity chip her kartta**
   - Tek dominant entity (LLM extracted)
   - Tıklanınca entity-filtered feed view

4. **Feed split**
   - Tab 1: **Action Required** (action_tag IN ('RISK','OPPORTUNITY'))
   - Tab 2: **Background Monitor** (action_tag = 'MONITOR')
   - Default: Action Required

5. **Tema chip'lerini tıklanabilir yap**
   - Şu an statik, click → feed filter aktif olmalı
   - URL'e `?theme=...` query param

6. **Dedup cluster view**
   - Aynı tema'da 3+ article ise: parent card + collapsed children
   - "3 related articles" expandable
   - Strongest score parent olarak gösterilir

#### Files Affected

```
dashboard/static/index.html (struktur)
dashboard/static/app.v5.js → app.v6.js (cache buster bump)
dashboard/static/style.v5.css → style.v6.css
dashboard/server.py (/api/signals output: rayon_why_it_matters, exposure_type, entity dahil)
```

#### Definition of Done

- [ ] Tüm kartlarda "Rayon için anlamı:" satırı render
- [ ] Exposure + geography chips doğru render
- [ ] Entity chip görünüyor ve filtreleyebiliyor
- [ ] Feed Tab 1 / Tab 2 ayrımı çalışıyor
- [ ] Theme chip click → filter aktif
- [ ] Dedup cluster en az 1 örnekle test edildi
- [ ] Cache buster v6 → v7 bumped

#### Risk

- Düşük. Frontend değişiklikleri reversible. Backend signal output schema P1'de hazırlanmış olacak.

---

### P4 — Productization · 1-2 hafta · ~28 saat

**Goal:** Sayfa "günlük açılan dashboard" olmaktan "haftalık özet + entity drill-down" platformuna evrilsin.

#### Tasks

1. **Weekly Digest Generator**
   - Her Pazartesi 09:00 İstanbul
   - Geçen hafta top 3 critical + top 5 themes + entity moves
   - Telegram'a structured format
   - File: `scrapers/weekly_digest.py`

2. **"Top 3 This Week" Panel (Dashboard)**
   - Critical Signals'ın üstüne yerleşir
   - Hafta bazlı, manuel curated değil — algorithmic (impact + recency + uniqueness)

3. **Entity Detail Pages**
   - `/entity/{entity_id}` route
   - Son 90 günde mention edildiği signal'lar
   - Eğer supplier ise: ilgili price_metrics_daily overlay (örn. SASA → polyester FDY chart)
   - Bu yarın Yarn Intelligence'taki Entity-Yarn linking ile entegrasyon noktası olabilir

4. **Theme Detail Views**
   - `/theme/{theme_slug}` route
   - Tema timeline + ilgili tüm signal'lar + entity participation map

5. **Telegram Structured Digest**
   - Mevcut `telegram_reporter.py` plain text → structured (markdown + emoji + linkler)
   - Action Required / Background ayrımı
   - Inline keyboard: "Full feed" / "Entity X" buttons

#### Files Affected

```
scrapers/weekly_digest.py (yeni)
scrapers/telegram_reporter.py (refactor)
dashboard/static/entity_detail.html (yeni)
dashboard/static/theme_detail.html (yeni)
dashboard/server.py (yeni route'lar)
.github/workflows/weekly_digest.yml (yeni cron)
```

#### Definition of Done

- [ ] İlk weekly digest gönderildi ve Mert tarafından onaylandı
- [ ] Dashboard'da "Top 3 This Week" görünüyor ve makul sonuçlar üretiyor
- [ ] En az 3 entity detail page çalışıyor (SASA, Korteks, EURATEX)
- [ ] En az 3 theme detail page çalışıyor
- [ ] Telegram digest structured + action button'lı

#### Risk

- Düşük-orta. Yeni route'lar isolated; mevcut sayfayı etkilemez.

---

## 5. Cross-cutting Concerns

### 5.1 Data Protection Constraint

P1 boyunca migration'lar **append-safe ve idempotent** olmalı. Kritik tablo listesi (DROP/TRUNCATE/overwrite **yasak**):

- `price_metrics_daily`
- `price_signals`
- `price_intelligence_signals`
- `price_chain_spreads`
- `news_items`
- `market_signals`
- `competitor_snapshots`

P1 migration'ları yalnız `ALTER TABLE ADD COLUMN` ve `INSERT ... ON CONFLICT DO NOTHING` paternleri kullanmalı.

### 5.2 Cache Buster Discipline

Her JS/CSS değişikliğinde:

```
v5 → v6 (P3'te) → v7 (P4'te)
```

`index.html` → `?v={timestamp}` parametresi mecburi.

### 5.3 Git Commit Discipline

Non-ASCII karakter içeren commit message'lar için:

```bash
git commit -F docs/commit_messages/phase_e_p1_a.txt
```

Commit message file pattern: `docs/commit_messages/phase_e_{phase}_{subtask}.txt`

### 5.4 LLM Cost Monitoring

P1'de prompt expansion sonrası `llm_cost_summary` view'ı haftada 1 kontrol edilmeli. Beklenen artış: günlük $0.01 → $0.012 (kabul edilebilir). Eğer $0.02'ye çıkarsa prompt optimization gerekir.

---

## 6. Success Metrics (Phase E sonu için)

| Metrik | Baseline (8 May 2026) | Hedef (Phase E sonu) |
|---|---|---|
| Source count | 4 | 7+ (Tier A tamamlandığında) |
| Entity count | 32 (hepsi competitor) | 47+ (4+ kategoride) |
| Articles with `rayon_why_it_matters` | %0 | >%95 |
| Articles with `affected_business_line` | <%20 | >%90 |
| `published_at` fill rate | %0 | >%85 |
| `signal_category` NULL rate | %78 | <%5 |
| Threshold-passing rate (signal/total article) | %12 | %18-25 (target) |
| Daily LLM cost | ~$0.01 | <$0.015 |
| Telegram digest format | plain | structured + action |
| Weekly digest | yok | aktif |

---

## 7. Sequencing & Dependencies

```
P0 (1-2 gün)
  └─→ P1-A: DB migration (1 gün)
       └─→ P1-B: LLM prompt update (1 gün)
            ├─→ P1-C: Priority entity seed (yarım gün)
            └─→ P3: UI upgrade (paralel başlayabilir, P1-B'den schema bekler)
       └─→ P2: Source expansion (P1-B sonrası anlamlı, paralel ilerleyebilir)
            └─→ P4: Productization (P2 + P3 sonrası)
```

**Critical path:** P0 → P1-A → P1-B → P3
**Parallelizable:** P1-C ile P2 birlikte
**Independent:** P4 weekly digest (P0 sonrası bağımsız başlatılabilir)

---

## 8. Open Questions / Future Considerations

Phase E kapanırken veya ilerleyen fazlarda değerlendirilecek:

1. **Çoklu entity per signal** — şu an entity_name tek field. Bir haberde 3 firma geçtiğinde nasıl handle edilecek? `entities jsonb` array'e geçiş?
2. **Confidence score per signal** — LLM'in kendi confidence'ı tracking edilebilir, low-confidence'lar ayrı bucket'a düşürülebilir.
3. **Time-decay weighting** — eski high-impact signal'lar 30 gün sonra otomatik dim edilmeli mi?
4. **Multi-language support** — Türkçe/İngilizce dual output (özet TR, technical EN)?
5. **Yarn Intelligence ile bağlantı** — entity_role=supplier ise, yarn_pressure overlay otomatik gösterilebilir mi?
6. **Customer-account-risk monitoring** — North Face / Adidas gibi büyük müşteri haberlerini ayrı kategori (yeni `category='customer'` kullanımı genişletilmeli)
7. **Source tier weighting** — İHKİB official duyurusu vs just-style anonim haber aynı ağırlıkta mı? Source-level priority weight gerekebilir.

---

## 9. Glossary

| Terim | Açıklama |
|---|---|
| **Decision-grade source** | Sektör derneği, regülatör, resmi kurum gibi yüksek güvenilirlikte kaynak |
| **Trend-grade source** | Generic news site (fibre2fashion, just-style) gibi orta güvenilirlikte kaynak |
| **Entity** | Firma, dernek, regülatör — sinyalin merkezindeki aktör |
| **Exposure** | Rayon'un sinyale hangi koldan dokunduğunu (raw material / export / regulation vb.) |
| **Action tag** | RISK / OPPORTUNITY / MONITOR — önerilen aksiyon türü |
| **Theme** | Sinyal kümesinin ortak alt-konusu (örn. "Polyester Cost Pressure") |
| **Action Required Feed** | action_tag IN ('RISK','OPPORTUNITY') — operasyonel müdahale gerektirir |
| **Background Monitor Feed** | action_tag = 'MONITOR' — bağlam, izleme |

---

## 10. Changelog

| Tarih | Versiyon | Değişiklik | Yapan |
|---|---|---|---|
| 2026-05-08 | v1.0 | İlk draft, Phase E komple roadmap | Mert + Claude |

---

> **Sıradaki adım:** Bu dokümanı GitHub'a commit ettikten sonra **P0**'dan başla. Tahmini başlangıç: 8 May 2026 akşam veya 9 May 2026 sabah. Tahmini tamamlanma: P0 → 9 May, P1 → 14 May, P2 → 21 May, P3 → 26 May, P4 → 5 Haz 2026.
