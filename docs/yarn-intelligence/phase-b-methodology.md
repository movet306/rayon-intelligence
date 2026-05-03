# Yarn Intelligence Phase B — Market-Common Starter Library Methodology

**Status:** `DRAFT`
**Date:** 2026-05-03
**Author:** Mert Ovet
**Module:** Yarn Intelligence (Rayon Intelligence Platform)

---

## One-line purpose

Bu doküman, Yarn Intelligence Phase B için **market-common starter library**'nin nasıl kanıtlanacağını ve sisteme nasıl taşınacağını tanımlar.

---

## 1. Purpose / Scope

Phase A (Migration 009) ile `dim_yarn_master` üzerine 3-layer universe model kuruldu: `is_market_common` / `is_rayon_confirmed` / `is_active_tracked`. Phase A sadece **meta-model**'di — yani yapıyı kurdu, içeriği değiştirmedi.

Phase B'nin görevi: bu yapıyı, Rayon'un gerçekten yüzleştiği yarn evrenine yakın bir başlangıç noktası ile doldurmak. Bunu yaparken iki hata tuzağına düşmemek lazım:

1. **Sahte kesinlik** — Claude'un sezgisiyle uydurulan spec listelerini "piyasada yaygın" diye işaretlemek.
2. **Kapsam çöküşü** — sadece poly+nayl ile sınırlı kalıp viscose/modal/blend tarafını boş bırakmak.

Bu doküman, ikisini de engelleyecek bir araştırma mimarisi tanımlar.

**Scope dahil:**
- Yarn-level spec'ler (filament, staple, spun)
- Family'ler: polyester, polyamide, viscose, modal, blends
- Database tabloları: `dim_yarn_master`, `dim_yarn_price_driver`, `dim_yarn_label_alias`

**Scope dışı (bu phase'de değil):**
- Fabric-level intelligence (ayrı methodology)
- Premium-rules JSON expansion (Phase C)
- Supplier quote ingestion (Phase D sonrası)
- Rayon-confirmed enrichment'in tamamı (Phase D'de yapılır)

---

## 2. Source Hierarchy

Phase B'nin temel ilkesi: **kaynaklar eşit ağırlıkta değildir**. Aşağıdaki sıralama, bir spec'in `is_market_common = true` adayı olabilmesi için kanıt değerini belirler.

### Tier 0 — Internal Rayon truth
**En güçlü katman.** Rayon'un gerçek alış/satış/quote geçmişinden gelen kanıt. Bu katmandan gelen spec'ler `is_rayon_confirmed = true` olur (Phase D'de daha sistematik genişletilecek), aynı zamanda otomatik market_common adayıdır.

Mevcut Tier 0 kaynakları:
- `yarn_costs` (245 satır, 2015-2025) — sadece poly+nayl
- `lkp_yarn_taxonomy` (52 tip) — aynı evrenden
- Manuel teyit (ustabaşı / satın alma / planlama) — dijital değil

**Önemli caveat:** Tier 0 cellulosic ve blend tarafında neredeyse boş. Bu, family'lere göre kanıt katmanlarının dağılımını değiştirir (bkz. Section 8).

### Tier 1 — Turkish producer catalogs
Türk üretici katalogları **family-spesifik** olarak değerlendirilmeli. Tek bir Türk üreticisini "ana referans" yapmak yanlış — her üretici farklı bir alanda güçlü.

Beklenen alt-segmentasyon:
- Cotton & blended yarn (apparel) → likely Sanko, İskur, Kıvanç (TBD verify)
- Industrial / high-denier PA66 / PET → likely Kordsa (TBD verify)
- Mainstream filament polyester → ayrı üreticiler taranacak (TBD)

**Bu segmentasyon Phase B3 başında web research ile teyit edilecek.** Şu anda taslakta isimler "candidate" olarak listelenmiştir.

### Tier 2 — Global producer catalogs
Türk piyasasında karşılığı doğrulanmasa bile global ortak spec'leri yakalamak için. Özellikle cellulosic tarafında kritik.

Beklenen kaynaklar:
- Lenzing (modal, lyocell, viscose family ayrımı için)
- Indorama, Reliance (polyester filament evren)
- Asian filament üreticileri (PA / PET aile dağılımı)
- Textile Exchange raporları (MMCF aile payları için)

### Tier 3 — Repeated B2B listings
Alibaba, Made-in-China, IndiaMART, Fibre2Fashion gibi platformlardaki listing tekrarları. **Tek başına truth değildir** — sadece "hangi denier × filament × count kombinasyonları sürekli tekrarlıyor" sorusuna cevap verir.

Kullanım kuralı: Tier 3 kanıtı tek başına `is_market_common = true` üretmez. Diğer tier'larla birleşince güçlenir.

### Tier 4 — Benchmark availability
Spec için `pricing_basis` ne olabilir? Bu katman karar üretir, market_common adaylığını doğrudan etkilemez ama sonraki seed adımında `pricing_basis` sütununu doldurur:
- `direct` = doğrudan fiyat referansı (ICE, SunSirs spot)
- `benchmark` = takip edilen dış benchmark
- `proxy` = ilişkili upstream commodity
- `estimate` = driver-linked modeled estimate

### Tier 5 — Industry sanity sources
ITMF cost reports, sektör raporları, Textile Exchange. Bunlar **spec üretmez**, sadece model mantığını sağlık kontrolünden geçirir. "Hangi family'de conversion ağırlıktır?" gibi sorularda referans.

---

## 3. Market-Common Identification Logic

### Karar kuralı
Bir spec `is_market_common_candidate = true` olabilmek için aşağıdaki kanıtlardan **en az 2'sini** sağlamalı:

1. En az 1 Türk üretici kataloğunda görünür (Tier 1)
2. En az 2 global üretici / seller kaynağında tekrar eder (Tier 2)
3. Normalize edilmiş canonical formda en az 3 ayrı B2B listing'de görünür (Tier 3)
4. Buna uygun bir benchmark / driver mantığı kurulabilir (Tier 4)
5. İlgili family'de **mainstream commercial** veya **technical mainstream** use-case'i vardır

### Önemli kısıt
- `is_market_common = true` olması, `is_rayon_confirmed = true` anlamına **gelmez**
- `is_market_common = true` olması, `is_active_tracked = true` anlamına **gelmez**
- Bunlar üç bağımsız doğrudur (Migration 009'daki üç boolean mantığı).

### Internal sınıflandırma (DB'ye değil, evidence sheet'e)
Market-common adayları evidence sheet üzerinde 3 alt-tip olarak işaretlenecek:
- `mainstream` — commercial apparel'da yaygın
- `technical` — teknik tekstil / industrial alanda yaygın
- `niche-but-repeatable` — dar ama sürekli tekrar eden

Bu ayrım şu an `dim_yarn_master`'a kolon olarak eklenmiyor. İhtiyaç doğarsa Phase E'de değerlendirilir.

---

## 4. Family-by-Family Research Order

Karışık ilerlemek karmaşa üretir. Kilitli sıra:

| # | Family | Öncelik nedeni |
|---|---|---|
| 1 | Polyester | Phase 1 zaten burada, Tier 0 kanıt güçlü, starter en kolay |
| 2 | Polyamide | Phase 1 evren, PA6/PA66 ayrımı net |
| 3 | Viscose | Cellulosic tarafının ana family'si (Textile Exchange MMCF payı) |
| 4 | Modal | Viscose'tan ayrı tutulmalı (Lenzing yapısı), daha dar evren |
| 5 | Blends | Saf family'ler oturmadan blend seed edilmez |

Her family için ayrı evidence sheet sayfası / CSV doldurulacak. Family geçişlerinde durup özetlenecek.

---

## 5. Claude Role vs Human Role

### Claude'un yapacağı işler
- Web kaynaklarını family bazında taramak
- Spec text'leri canonical forma normalize etmek (regex parser)
- Tekrar frekansını saymak
- Benchmarkability notu çıkarmak
- Candidate `market_common` listesi üretmek
- Evidence sheet'e düzenli dökmek
- Seed SQL taslağı hazırlamak

### Claude'un YAPMAYACAĞI işler
- "Bu kesinlikle yaygın" diye tek başına hüküm vermek
- Türkiye gerçeğini katalog teyidi olmadan varsaymak
- `market_common` ile `rayon_confirmed`'i karıştırmak
- Blend ratio veya spec'leri kanıtsız uydurmak
- Final seed kararını vermek

### İnsanın (Mert) yapacağı işler
- Methodology doc finalize
- Tier 0 manuel teyit (kullanıyoruz / kullanmıyoruz)
- Türk üretici kataloglarının teyidi
- Candidate library'nin son review'u
- `is_active_tracked` listesinin seçimi
- Seed apply onayı

---

## 6. Known Caveats

Bu caveats'lar Phase B uygulanırken sürekli akılda tutulmalı.

### C1 — Cellulosic ve blend tarafında Tier 0 zayıf
Mevcut `yarn_costs` ve `lkp_yarn_taxonomy` tabloları sadece poly+nayl içeriyor. Viscose/modal/blend için **dijital iç kayıt yok**. Bu, Phase B3-B5 sırasında manuel teyit aşamasında kapatılmalı.

**Sonuç:** Polyester ve polyamide starter library'sinin kanıt gücü, viscose/modal/blend tarafından **daha yüksek** olacak. Methodology body'sinde ayrı dahili "confidence note" tutulacak.

### C2 — Türk üretici evidence family-spesifik doğrulanmalı
Sanko'nun cotton/blend'de güçlü olduğu, Kordsa'nın industrial'da güçlü olduğu sektör bilgisi. **Ama bu Phase B3 başında web research ile resmi katalog üzerinden teyit edilmeli.** Tek bir Türk üreticiyi "tüm family'lerin referansı" yapmak yanlış.

### C3 — `market_common` ≠ `rayon_confirmed`
Bu üç katman üç ayrı doğrudur. Phase B sadece `market_common` set eder. `rayon_confirmed` Phase D'de manuel review ile, `active_tracked` Mert'in seçimiyle ayarlanır.

### C4 — Starter library, gerçek şirket evreni gibi sunulmayacak
UI tarafında `market_common = true` ve `rayon_confirmed = false` olan spec'ler net görsel ayrım ile gösterilmeli. Aksi halde model sahte kesinlik üretir.

### C5 — Modal, viscose'un alt-tipi olarak seed edilmeyecek
Lenzing'in resmi ürün yapısı modal'ı ayrı family olarak tutar. Textile Exchange MMCF dağılımına göre viscose çok daha geniş, modal daha dar bir evrendir. Bu yüzden modal subfamily değil, ayrı `fiber_family` değeri olarak modellenmeli.

---

## 7. What This Document Does NOT Yet Decide

Aşağıdaki konular bu DRAFT'ta **kasıtlı olarak finalize edilmemiştir**. Bir sonraki oturumda taze kafayla netleştirilecek.

| Konu | Şu an | Sonraki oturum |
|---|---|---|
| Spesifik Türk üretici isimleri (kesin liste) | Candidate liste | Web research sonrası kilit |
| Acceptance threshold sayıları (tam değerler) | "En az 2-3 kaynak" | Family bazında özelleşmiş eşikler |
| Evidence sheet kolon listesi | Genel hatlar | Final kolon yapısı + validasyon kuralları |
| Phase B toplam efor tahmini | ~10-15 saat (kaba) | Family bazında detaylı tahmin |
| Methodology doc'un Türkçe terminolojisi | İlk yaklaşım | Tutarlılık review |
| Format: CSV mi Google Sheets mi evidence için? | Henüz seçilmedi | Workflow'a göre seç |

---

## 8. Next Session Checklist

Bir sonraki oturumda yapılacaklar:

- [ ] Bu DRAFT'ı baştan sona oku, finalize edilecek noktaları işaretle
- [ ] Section 7'deki tabloda olan kararları al
- [ ] Status'ı `DRAFT` → `FINAL` yap
- [ ] Phase B2 (evidence sheet template) tasarımına geç
- [ ] Phase B3 (polyester research) için ilk web search query'lerini hazırla

---

## Appendix — Cross-references

- **Migration 009** (`migrations/009_yarn_universe_tier.sql`) — Phase A meta-model, bu doc'un altyapısı
- **Phase A commit** — `3559211`
- **3-layer universe model kararı** — 3 May 2026 oturumu
- **Yarn Intelligence forensik analizi** — 3 May 2026 oturumu

---

*Bu doküman canlı bir karar metnidir. Status `FINAL` olduktan sonra büyük yapısal değişiklikler ayrı bir revizyon notu ile yapılmalıdır.*
