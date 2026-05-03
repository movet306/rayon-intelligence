# Yarn Intelligence Phase B — Market-Common Starter Library Methodology

**Status:** `FINAL`
**Date:** 2026-05-03 (DRAFT → FINAL same day, post-review)
**Author:** Mert Ovet
**Module:** Yarn Intelligence (Rayon Intelligence Platform)

---

## One-line purpose

Bu doküman, Yarn Intelligence Phase B için **market-common starter library**'nin nasıl kanıtlanacağını ve sisteme nasıl taşınacağını tanımlar.

---

## 1. Purpose / Scope

### Mevcut durum
Yarn Intelligence şu an **driver-linked estimate** sistemidir, **quote-validated yarn pricing** sistemi değildir. Phase B starter library bu durumu değiştirmez — sadece kapsamı genişletir. Quote-validation ve gerçek tedarikçi fiyat kanıtı Phase D ve sonrasının konusudur.

### Phase B'nin görevi
Phase A (Migration 009) ile `dim_yarn_master` üzerine 3-layer universe model kuruldu: `is_market_common` / `is_rayon_confirmed` / `is_active_tracked`. Phase A sadece **meta-model**'di — yani yapıyı kurdu, içeriği değiştirmedi.

Phase B'nin görevi: bu yapıyı, Rayon'un gerçekten yüzleştiği yarn evrenine yakın bir başlangıç noktası ile doldurmak. Bunu yaparken iki hata tuzağına düşmemek lazım:

1. **Sahte kesinlik** — Claude'un sezgisiyle uydurulan spec listelerini "piyasada yaygın" diye işaretlemek.
2. **Kapsam çöküşü** — sadece poly+nayl ile sınırlı kalıp viscose/modal/blend tarafını boş bırakmak.

Bu doküman, ikisini de engelleyecek bir araştırma mimarisi tanımlar.

### Indicative effort range
İndikatif efor tahmini: Phase B toplam ~10–15 saat, birden fazla oturuma yayılır. Gerçek maliyet ilk family (polyester) bittiğinde kalibre edilecek ve gerekirse bu tahmin revize edilecektir.

### Scope dahil
- Yarn-level spec'ler (filament, staple, spun)
- Family'ler: polyester, polyamide, viscose, modal, blends
- Database tabloları: `dim_yarn_master`, `dim_yarn_price_driver`, `dim_yarn_label_alias`

### Scope dışı (bu phase'de değil)
- Fabric-level intelligence (ayrı methodology)
- Premium-rules JSON expansion (Phase C)
- Supplier quote ingestion (Phase D sonrası)
- Rayon-confirmed enrichment'in tamamı (Phase D'de yapılır)

### Terminoloji kuralı
Bu doküman ve tüm Phase B çıktıları için sabit kural:

- **Stratejik metin / akış / talimat:** Türkçe
- **Teknik tanımlı terimler:** İngilizce — `is_market_common`, `is_rayon_confirmed`, `is_active_tracked`, `pricing_basis`, `canonical_code`, `direct/benchmark/proxy/estimate`, `Tier 0–5`
- **Fiber family adları:** İngilizce kabul edilen formda — `polyester`, `polyamide`, `viscose`, `modal`, `blend`. İlk geçtiği yerde gerekirse parantezli Türkçe açıklama olabilir, sonra sadece İngilizce kullanılır.

---

## 2. Source Hierarchy

Phase B'nin temel ilkesi: **kaynaklar eşit ağırlıkta değildir**. Aşağıdaki sıralama, bir spec'in `is_market_common = true` adayı olabilmesi için kanıt değerini belirler.

### Tier 0 — Internal Rayon truth
**En güçlü katman.** Rayon'un gerçek alış/satış/quote geçmişinden gelen kanıt. Bu katmandan gelen spec'ler `is_rayon_confirmed = true` olur (Phase D'de daha sistematik genişletilecek), aynı zamanda otomatik market_common adayıdır.

Mevcut Tier 0 kaynakları:
- `yarn_costs` (245 satır, 2015–2025) — sadece poly+nayl
- `lkp_yarn_taxonomy` (52 tip) — aynı evrenden
- Manuel teyit (ustabaşı / satın alma / planlama) — dijital değil

**Önemli caveat:** Tier 0 cellulosic ve blend tarafında neredeyse boş. Bu, family'lere göre kanıt katmanlarının dağılımını değiştirir (bkz. Section 6 / C1).

### Tier 1 — Turkish producer catalogs
Türk üretici katalogları **family-spesifik** olarak değerlendirilmeli. Tek bir Türk üreticisini "ana referans" yapmak yanlış — her üretici farklı bir alanda güçlü.

**Bu segmentasyon Phase B3 başında, family-by-family web research'ün ilk adımı olarak teyit edilecektir.** Kanıt: üreticilerin resmi ürün katalogları + grup/ürün dokümanları + sektör sanity kaynakları. Bu doküman, spesifik üretici-family eşlemesini bilerek **finalize etmemektedir**.

### Tier 2 — Global producer catalogs
Türk piyasasında karşılığı doğrulanmasa bile global ortak spec'leri yakalamak için. Özellikle cellulosic tarafında kritik.

Beklenen kaynaklar (B3 araştırmasıyla teyit edilecek):
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

### Karar kuralı (universal 2-of-5 rule)
Bir spec `is_market_common_candidate = true` olabilmek için aşağıdaki kanıtlardan **en az 2'sini** sağlamalı:

1. En az 1 Türk üretici kataloğunda görünür (Tier 1)
2. En az 2 global üretici / seller kaynağında tekrar eder (Tier 2)
3. Normalize edilmiş canonical formda en az 3 ayrı B2B listing'de görünür (Tier 3)
4. Buna uygun bir benchmark / driver mantığı kurulabilir (Tier 4)
5. İlgili family'de **mainstream commercial** veya **technical mainstream** use-case'i vardır

**Bu kural family-spesifik istisnasız uygulanır.** Tier 0 zayıflığı (cellulosic/blend) gibi durumlar threshold sayılarına değil, evidence sheet'teki `evidence_strength` ve `reviewer_notes` alanlarına yansıtılır. Methodology omurgasının basit kalması esastır.

### Önemli kısıt
- `is_market_common = true` olması, `is_rayon_confirmed = true` anlamına **gelmez**
- `is_market_common = true` olması, `is_active_tracked = true` anlamına **gelmez**
- Bunlar üç bağımsız doğrudur (Migration 009'daki üç boolean mantığı)

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

Her family için ayrı evidence sheet sayfası doldurulacak. Family geçişlerinde durup özetlenecek.

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
- Methodology doc finalize (✓ tamamlandı)
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

**Sonuç:** Polyester ve polyamide starter library'sinin kanıt gücü, viscose/modal/blend tarafından **daha yüksek** olacak. Evidence sheet'te per-spec `evidence_strength` alanı bu farkı yakalayacak.

### C2 — Türk üretici evidence family-spesifik doğrulanmalı
Türk üreticilerin hangi family'de güçlü olduğuna dair sektör bilgisi mevcut, ancak bu kanıtlanacak başlangıç hipotezleri olarak ele alınır. Phase B3 başında resmi katalog üzerinden teyit edilmeli. Tek bir Türk üreticiyi "tüm family'lerin referansı" yapmak yanlış olur.

### C3 — `is_market_common` ≠ `is_rayon_confirmed`
Bu üç katman üç ayrı doğrudur. Phase B sadece `is_market_common` set eder. `is_rayon_confirmed` Phase D'de manuel review ile, `is_active_tracked` Mert'in seçimiyle ayarlanır.

### C4 — Starter library, gerçek şirket evreni gibi sunulmayacak
UI tarafında `is_market_common = true` ve `is_rayon_confirmed = false` olan spec'ler net görsel ayrım ile gösterilmeli. Aksi halde model sahte kesinlik üretir.

### C5 — Modal, viscose'un alt-tipi olarak seed edilmeyecek
Lenzing'in resmi ürün yapısı modal'ı ayrı family olarak tutar. Textile Exchange MMCF dağılımına göre viscose çok daha geniş, modal daha dar bir evrendir. Bu yüzden modal subfamily değil, ayrı `fiber_family` değeri olarak modellenmeli.

---

## 7. Evidence Workflow

### Toplama katmanı — Google Sheets
Active research, normalize, review ve note'lar Google Sheets üzerinde kollaboratif olarak yürütülür. Sebep:
- Real-time kollaboratif düzenleme
- Formül ve filtreleme desteği
- Comment + review iş akışı
- Mert + Claude (ve gerekirse başkaları) aynı anda çalışabilir

### Snapshot katmanı — CSV in repo
Periyodik olarak (her family bittiğinde + final review öncesi) Sheets'ten CSV export alınır ve `docs/yarn-intelligence/evidence/` altına commit'lenir. Sebep:
- Versiyon kontrolü ile takip
- GitHub diff görünürlüğü
- Methodology + evidence aynı yerde arşivlenir
- Sheets erişimi kaybolsa bile snapshot kalır

### Kolon kategorileri (full liste Phase B2'de)
Evidence sheet'in kolonları beş kategoride toplanır:
1. **Identification** — family, raw_label, canonical_code
2. **Spec attributes** — form, count, denier, ply, twist, luster, recycle_flag, blend_ratio_json
3. **Source evidence** — source_type, source_name, source_url, repeat_count, evidence_strength
4. **Decision support** — benchmark_available, pricing_basis_candidate, market_common_candidate
5. **Review** — reviewer_notes, status

Tam kolon listesi ve validasyon kuralları (regex pattern'ları, kontrollü vocabulary) Phase B2'de tasarlanacak.

---

## 8. Next Session Checklist

Bir sonraki oturumda yapılacaklar:

- [x] Bu DRAFT'ı baştan sona oku, finalize edilecek noktaları işaretle ✓
- [x] Section 7'deki tabloda olan kararları al ✓
- [x] Status'ı `DRAFT` → `FINAL` yap ✓
- [ ] `is_active_tracked` UPDATE (5–10 spec) — Mert'in seçimi
- [ ] Phase B2 (evidence sheet template) tasarımına geç — kolon listesi + validasyon
- [ ] Phase B3 (polyester research) için ilk web search query'lerini hazırla

---

## Appendix — Cross-references

- **Migration 009** (`migrations/009_yarn_universe_tier.sql`) — Phase A meta-model, bu doc'un altyapısı
- **Phase A commit** — `3559211`
- **Phase B methodology DRAFT commit** — `c2dd855`
- **3-layer universe model kararı** — 3 May 2026 oturumu
- **Yarn Intelligence forensik analizi** — 3 May 2026 oturumu

---

## Revision History

| Version | Date | Status | Notes |
|---|---|---|---|
| 1.0-draft | 2026-05-03 | DRAFT | İlk taslak, 6 açık karar Section 7'de |
| 1.0-final | 2026-05-03 | FINAL | 6 açık karar netleştirildi, Section 1'e current state + indicative effort, Section 7 evidence workflow oldu |

---

*Bu doküman canlı bir karar metnidir. Status `FINAL` olduktan sonra büyük yapısal değişiklikler ayrı bir revizyon notu ile yapılmalıdır.*
