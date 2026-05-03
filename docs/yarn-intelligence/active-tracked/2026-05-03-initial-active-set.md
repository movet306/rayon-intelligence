# Yarn Intelligence — Initial `is_active_tracked` Set

**Date:** 2026-05-03
**Decision-maker:** Mert Ovet
**Operator (executed):** Claude (rayon-intelligence assistant)
**Type:** Versioned operational decision artifact (NOT a schema migration)
**Related migration:** `migrations/009_yarn_universe_tier.sql`
**Methodology reference:** `docs/yarn-intelligence/phase-b-methodology.md`

---

## Karar özeti

`dim_yarn_master` tablosundaki 21 spec'in **8'i** ilk default watchlist olarak `is_active_tracked = true` olarak işaretlendi. Bu set, UI'da default görünecek olan ve fiyat hareketinin gerçekten ticari karar değiştirebileceği çekirdek spec'leri temsil eder.

### Aktif edilen 8 spec

| yarn_id | yarn_code | display_name | family | driver |
|---:|---|---|---|---|
| 1  | PES_100D_144F                | PES 100D/144F            | polyester | polyester_fdy |
| 11 | PES_75D_72F                  | PES 75D/72F              | polyester | polyester_fdy |
| 19 | PA6_70D_68F_DTY_S            | PA6 70D/68F FD S         | polyamide | pa6_chip      |
| 26 | PA66_470D_140F_HT            | PA66 470D/140F HT        | polyamide | pa66_chip     |
| 34 | PES_100D_96F_ECRU            | PES 100D/96F Ecru        | polyester | polyester_fdy |
| 45 | PES_50D_72F_ECRU             | PES 50D/72F Ecru         | polyester | polyester_fdy |
| 49 | PES_75D_72F_DTY_ECRU_RECYCLE | PES 75D/72F FD Ecru GRS  | polyester | polyester_dty |
| 51 | PES_75D_72F_ECRU_RECYCLE     | PES 75D/72F Ecru GRS     | polyester | polyester_fdy |

---

## Seçim mantığı

Watchlist tasarımının iki kuralı:
- 5 fazla dar → ilk genişleme zorlaşır
- 10 fazla dağınık → ilk sürümde focus kaybolur
- 8 → temsil + disiplin dengesi

### 1. Çekirdek baz polyester spec'leri (4)
`PES_75D_72F`, `PES_100D_144F`, `PES_100D_96F_ECRU`, `PES_50D_72F_ECRU` — bunlar niche varyant değil, watchlist'in omurgası. Default ekranda önce bu baz spec'ler görünmeli.

### 2. Recycle gerçek ticari tema (2)
`PES_75D_72F_DTY_ECRU_RECYCLE` ve `PES_75D_72F_ECRU_RECYCLE` — recycle artık küçük teknik varyant değil, ticari karar nesnesi. Sürdürülebilir ürün tarafının ilk sürümde temsili olmalı. Tamamen dışarıda bırakmak yanlış olur.

### 3. Polyamide tarafı dengeli (2)
- `PA66_470D_140F_HT` (id 26) — yüksek denier / HT teknik taraf
- `PA6_70D_68F_DTY_S` (id 19) — daha ince / DTY taraf

İki spec birlikte polyamide evreninin iki ticari yüzünü temsil ediyor.

---

## Şimdilik aktif edilmeyenler

### Placeholder (kesin dışarıda)
- `29` — `PA66` — placeholder, mantıksal olarak izlenecek spec değil. Constraint zaten `pricing_basis NOT NULL` istediği için aktif edilemezdi.

### Cationic (niche, ileride değerlendir)
- `17` — `PES_100D_96F_CATIONIC`
- `18` — `PES_75D_72F_CATIONIC`

Şu an ticari ağırlığı belirsiz. Gerçek volume varsa sonra eklenir.

### Channel / specialty profile (specialty)
- `14` — `PES_150D_144F_KANALLI`
- `15` — `PES_150D_96F_KANALLI`
- `48` — `PES_75D_48F_KANALLI`

`is_market_common = true` olarak duruyor ama default active set'i şişirmemeli.

### Renk varyantları (ana volume olunca eklenir)
- `3` — `PES_100D_48F_BLACK`
- `5` — `PES_150D_48F_ANTH`
- `6` — `PES_150D_48F_BLACK`

İlk sürümde renk varyantları değil baz spec'ler öne çıksın. Eğer siyah/anth gerçek ana volume ise sonra biri aktif sete alınır.

### PA66 varyantları (ikinci dalga aday)
- `22` — `PA66_470D_136F_HT_B` — kalite varyantı, `26` baz olarak yeterli
- `27` — `PA66_78D_68F` — ikinci dalga aday

---

## İkinci dalga adaylar

Watchlist 8'den 10'a çıkarılırsa, en mantıklı iki ek:

1. `6` — `PES_150D_48F_BLACK` — boyalı 150D, dokuma tarafında ana volume olabilir
2. `22` — `PA66_470D_136F_HT_B` — PA66 kalite seviyesi takibi

Bu adaylar 1-2 oturum içinde gerçek alış pattern'ine bakılarak değerlendirilecek.

---

## Constraint doğrulaması

`migrations/009_yarn_universe_tier.sql` ile gelen iki CHECK constraint, bu UPDATE öncesi pre-flight script'inde teyit edildi:

- `chk_active_requires_confirmed`: 8 spec → `is_rayon_confirmed = true` ✓
- `chk_active_requires_pricing_basis`: 8 spec → `pricing_basis = 'estimate'` (NOT NULL) ✓

Pre-flight script atomik transaction içinde çalıştı, hata durumunda rollback garantili idi.

---

## Sonraki adımlar

Bu watchlist değiştirilmek istendiğinde aynı pattern uygulanacak:
- Yeni tarihli markdown karar kaydı: `YYYY-MM-DD-active-set-update.md`
- Yanında SQL: `YYYY-MM-DD-active-set-update.sql`
- Migration olarak ele alınmaz

Watchlist'in zamanla evrimi `docs/yarn-intelligence/active-tracked/` klasöründe tarihlenmiş şekilde takip edilecek.

---

## Revision History

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-05-03 | İlk active set, 8 spec |
