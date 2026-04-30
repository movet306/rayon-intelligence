# Rayon Intelligence Platform — Handoff Document
## Yeni chat oturumu için tam bağlam (29 Nisan 2026)

Bu dokümanı yeni chat'in **ilk mesajına yapıştır**. İçinde projenin tam durumu, son 2 günde yapılan iş, mevcut kod yapısı, ROADMAP ve devam edileceği nokta var. Bu dokümandan sonra direkt çalışmaya başlanabilir, hiçbir bilgi kaybı olmaz.

---

## 1. KİMSİN — KISA ÖZET

Mert Ovet (LinkedIn: mertovet, GitHub: movet306). Aile şirketi: **Rayon Tekstil Sanayi ve Dış Tic. Ltd. Şti.** İstanbul/Çorlu Tekirdağ, 1989 kurulu. İki taraf: (1) Örme — iplikten bitmiş kumaşa tam entegre, (2) Dokuma — Uzak Doğu'dan ham kumaş ithal + boyama/kaplama/laminasyon. İhracat: Doğu Avrupa, Orta Doğu, Kafkas, Rusya, Ukrayna.

Kişisel hedef: Python/SQL/Power BI/Excel arka planı var (kendi kendine öğrendi), AI/automation uzmanlaşması peşinde, eninde sonunda freelance AI automation consulting tekstil/üretim sektörüne odaklı.

## 2. RAYON INTELLIGENCE PLATFORM — MEVCUT DURUM

Aile şirketi için yapılan market intelligence + iç analytics platformu.

**Local dir:** `C:\Projects\rayon-intelligence`
**Repo:** `github.com/movet306/rayon-intelligence` (private)
**Son commit:** `7eb5f15` (29 Nisan 2026) — "Operations Intelligence M2 Phase 1 — Cost Structure & Overview, plus Procurement re-scope"

**Stack:**
- n8n (Railway) orchestration
- PostgreSQL (Railway, talented-prosperity project, mainline.proxy.rlwy.net:56047)
- Python + BS4 scraping
- OpenAI gpt-4o-mini direct HTTP (SDK kaldırıldı proxies bug yüzünden)
- Cloudflare R2 file storage
- FastAPI + HTML/JS + Plotly dashboard
- Uvicorn port 8000, conda env `rayon-dashboard`
- GitHub Actions daily 11:00 İstanbul

**Dashboard sub-tab'ları (Operations Intelligence):**
- Overview (default) — top signals strip + KPI wall + sparklines + health badges
- Procurement — KPI strip + concentration trend + currency mix + Top 10 Suppliers
- Cost Structure — KPI strip + movers strip + absolute chart + mix % chart + Top 10 Cost Suppliers
- Revenue Reality — KPI strip + concentration trend + Top 10 Customers
- Counterparty — supplier/customer detail explorer (CSS bug var, SIRADAKİ İŞ)

## 3. SON 2 GÜNDE YAPILAN İŞ (28-29 Nisan 2026)

### Procurement Phase 1 (önceki commit a154a72'de tamamlanmıştı)
- M2.2.1: Top 10 Suppliers tablosu enrichment (Migration 015)
- M2.2.2: KPI strip (Migration 016b)
- M2.2.3: Mix % chart
- M2.2.4: Concentration trend (Migration 017)
- M2.2.5: Currency mix chart (Migration 018)
- M2.2.6/7: DEFERRED to Phase 2 (drawer + bottleneck refactor — Railway US-West→TR latency dominates, gain limited)

### Revenue Phase 1 (önceki commit a154a72'de tamamlanmıştı)
- M2.3.1: Top 10 Customers enrichment (Migration 019)
- M2.3.2: KPI strip — 4 anchor + 4 context cards, KPI 6 = Top 3 customer share Δ INVERTED color (rising = red) (Migration 020/020b)
- M2.3.3: Concentration trend (Migration 021)
- M2.3.4: DEFERRED — sales 98.84% USD, chart effectively flat

### Cost Structure Phase 1 (BU CHATTE TAMAMLANDI)
- **M2.4.1**: Top 10 Cost Suppliers tablosu, bucket spread column (primary + secondary). Migration 022 (`v_top_cost_suppliers_overall`). Cost scope: utilities, maintenance_factory, packaging, factory_overhead, outsourced_processing, logistics_distribution.
- **M2.4.2**: KPI strip 6 metric (operating cost share of revenue, outsourced share, supplier count, maintenance share, avg monthly, cost/revenue ratio Δ). KPI 6 = INVERTED color (rising = margin compression = red). Migration 023 (`v_cost_kpis`). Window labels (recent_3m vs prior_3m).
- **M2.4.3**: Cost mix % chart (frontend-only over existing endpoint). Hook bug çözüldü: `loadInternal()`'a doğrudan call eklendi (`fix_mix_chart.py`).
- **M2.4.4**: Movers strip — 3 separate cards: biggest_increase (RED), biggest_decrease (GREEN), highest_volatility CV-based (AMBER). ±5% threshold for movers, CV ≥0.20 for volatility, 12m window. Migration 025 (`v_cost_movers`). User explicitly rejected merging into KPI strip.

### Procurement Re-scope (BU CHATTE — KRİTİK KARAR)
**Sorun:** AKSA ELEKTRİK, MARMARA ÇORLU GAZ, İBRİCE ENERJİ supplier'ları **HEM Procurement HEM Cost Structure** tablolarında görünüyordu. Çünkü Procurement scope = `is_cost_model_relevant=TRUE` (geniş — utilities/maintenance/fason hepsi dahil).

**Çözüm: Migration 024** — 4 Procurement view'ını DROP+RECREATE, scope sadece raw_material_yarn/chemical/dye/greige_fabric. Etkilenen view'lar:
- `v_top_suppliers_overall` (Mig 015)
- `v_procurement_kpis` (Mig 016b)
- `v_procurement_concentration_trend` (Mig 017)
- `v_monthly_procurement_by_currency` (Mig 018)

**Bonus fix:** `top_bucket` kolonu eskiden `MAX(business_bucket)` kullanıyordu (alfabetik). ROW_NUMBER ORDER BY bucket_amount_tl DESC ile değiştirildi (gerçek "en yüksek harcama bucket'ı").

**Sayılar değişti:**
- Top 3 supplier share: 32.83% → **42.85%**
- FX share: 37% → **45.98%**
- Active suppliers: 433 → **112**
- Top 5: EKİN DOKUMA %22.80, AY-ÇİL %12.28, KUTLUCAN %7.78, SETAŞ %5.50, KORTEKS %4.52

### Overview Phase 1 (BU CHATTE TAMAMLANDI)
- **M2.5.1**: Top signals strip — 4 sabit kart üstte, rule-based severity. customer_concentration / procurement_concentration / contra_revenue / margin_trend. Migration 026 (`v_overview_signals`). Bug fix: ARRAY_AGG `business_bucket::text` cast gerekti `@>` operator için.
- **M2.5.2**: Mini sparklines — 11 KPI kartına 12-ay trend SVG. Frontend-only, `_opsData.proc/cost/rev` reuse. `_kpiSparklineSeries()` resolver, `_renderSparklineSvg()` helper. Trend renkler: lastHalfAvg vs firstHalfAvg ±5% → up/down/flat.
- **M2.5.3**: Section health badges — 3 section title (Procurement / Cost / Revenue) renkli dot + chevron + click navigation. Health rollup frontend'de:
  - Procurement = procurement_concentration severity
  - Cost = margin_trend severity
  - Revenue = WORST(customer_concentration, contra_revenue)
  - **BUG fix:** `.sub-tabs [data-sub="..."]` selector tutmadı. Doğru selector: `.sub-nav-btn[data-sub="${target}"]` (button class direkt, parent değil).

### Counterparty UI fix (BU CHATTE BAŞLANDI, BİTMEDİ)
- Kullanıcı şikayet etti: Counterparty sub-tab'da bar chart parlak ama altındaki tüm tablolar (Purchase-side bucket split, Currency split, Top accounts, Subtype split, Recent rows, Classification quality) **açık gri/şeffaf — neredeyse görünmüyor**.
- Kök neden: CSS selector `#section-counterparty` (eski section ID) yazılmıştı ama HTML'de **`sub-ops-counterparty`** (Operations Intelligence sub-tab'a entegre edilince ID değişmiş, CSS güncellenmemiş). Tüm 240 satır Counterparty CSS **ölü**. Browser default light theme görünüyor.
- Ek: Dashboard dark theme. CSS variables: `--bg #0d1117`, `--card #161b22`, `--border #30363d`, `--text #e6edf3`, `--muted #8b949e`, `--blue #58a6ff`, `--green #3fb950`, `--orange #f0883e`, `--red #f85149`.
- **Fix yazıldı (`scripts/cp_ui_fix.py`)** — komple CSS rewrite, dark theme + var() tokens + `#sub-ops-counterparty` selector. Patch uygulandı (`python scripts/cp_ui_fix.py` çalıştı, "✓ Counterparty CSS block replaced" raporladı).
- **DURUM:** Browser refresh ile görsel kontrol YAPILMADI. Commit edilmedi.

## 4. ŞU AN NEREDESİN

**Henüz commit edilmemiş değişiklikler:**
- `dashboard/static/style.v5.css` (Counterparty UI rewrite, ~240 satır değişti)
- `dashboard/static/index.html` (cache buster timestamp, cp_ui_fix tarafından)
- `scripts/cp_ui_fix.py` (yeni dosya, untracked)

**Bekleyen aksiyonlar:**
1. Browser'da Ctrl+Shift+R, Operations → Counterparty, bir supplier seç. Tablolar düzgün görünüyor mu görsel kontrol.
2. Eğer tamamsa commit:
   ```powershell
   git add dashboard/static/style.v5.css dashboard/static/index.html scripts/cp_ui_fix.py
   git commit -m "Counterparty UI fix: selector mismatch and dark theme migration"
   git push
   ```

## 5. ROADMAP — PHASE 1 SONRASI

### Phase 2 deferrals (sıralı, atlanmadı)
- **M2.2.6/7**: Counterparty drawer + detail-endpoint single-connection refactor. `@with_shared_conn` decorator zaten kod'da var ama Railway US-West→TR latency dominates, gain limited.
- **M2.3.4**: Sales-side currency composition chart. Sales 98.84% USD, chart effectively flat. Phase 2'de gelirse "FX composition" karşılaştırma chart'ı olarak gelir.
- **M2.6 Phase 2 deepening:**
  - Counterparty Phase 2 — drawer (KPI'a tıklayınca detail panel açılır)
  - Filter architecture (time range, customer/supplier filter)
  - Monthly variance drivers (KPI'a tıklayınca "neden ay üzerinde değişti" breakdown)
  - Fiber/material family mix
  - Logistics_distribution split (originally tagged for M2.1) — inbound vs outbound
- **M2.7 cross-cutting:**
  - Time period filtering (month picker)
  - Comparison views (2025 vs 2024)
  - Drill-down to source invoices
  - Annotations/events ("New customer X onboarded on date Y")
  - Forecast/projection
  - Export to CSV/PDF
  - Printable layout

### Threshold tuning
- KPI 6 (margin trend) "Stable" at -0.9pp may want more sensitive threshold (e.g. ≤-0.5 → "Pressure easing"). Phase 2 calibration iş.

### Diğer projeler (Rayon dışı)
- **Tekstil Haber Botu v3** debug:
  - 504 textileworld.com errors
  - Zero-new-article on other sources
- **Faz 2 öğrenme roadmap'i** (paused during Rayon push):
  - LLM API/Prompt Engineering → RAG → AI Agents w/ LangGraph
  - 4.5 ay plan, haftada 5-7 saat
- **Portfolio çalışması:**
  - Rayon Intelligence için LinkedIn post
  - GitHub README screenshot'ları (yeni temiz UI ile)
  - Notion case study (diagnostic uplift somut sinyallerle)

## 6. LIVE DIAGNOSTIC SİNYALLER (29 NİSAN 2026 — Rayon Intelligence Platform üretiyor)

Platform şu an gerçekten **diagnostic** seviyede sinyal üretiyor:

- 🔴 **Customer concentration breach**: Top 3 share 36.5% (+10.2pp shift), latest top-1 = 30.11% (SPEC TEKSTİL), active customers 100→89 (-12% in 3 months)
- 🟡 **Procurement concentration**: Top 3 supplier share 42.85%, EKİN DOKUMA dominant at %22.80 (greige fabric)
- 🟡 **Contra revenue elevated**: 6.81% of gross, single customer LLC UKRTAC UA = 49% of total contra (3.2× 24-month median)
- 🟢 **Margin trend stable**: cost/revenue ratio -0.9pp (3m vs prior 3m), pressure easing
- 📊 **FX asymmetry**: sales 98.84% USD/EUR vs procurement 45.98% — natural TL devaluation hedge confirmed
- 📈 **Cost movers latest**: logistics_distribution +23.0% MoM (red), maintenance −72.2% MoM (green, single-month volatility), factory_overhead 12m CV 0.60
- 📈 **Procurement mover (latest)**: raw_material_yarn +74.5% MoM (+₺9.5M)

## 7. DISCIPLINE KURALLARI (BU PROJE İÇİN ÖNEMLİ)

1. **"Hiçbir şey atlama"** — Phase 1/Phase 2 sıralaması korundu, M2.2.6/7 ve M2.3.4 deferred not skipped.
2. **Browser cache buster** — Her JS/CSS patch sonrası `app.v5.js?v={timestamp}` mandatory. Patch script'leri zaten otomatik update ediyor.
3. **Manuel decorator approach** over auto-indent patches — M2.2.6c'den ders.
4. **Commit messages with non-ASCII** (Δ, em-dash, percent symbols, escape quotes) PowerShell parse error verir → her zaman `commit_msg.txt` + `git commit -F file` kullan. Latin equivalents: "minus", "percent", "change", parantez yerine köşeli parantez kullanma.
5. **Color semantics rule:** Rising metric green/red depending on whether rising is good or bad.
   - Procurement mover ▲ green (volume growth fine)
   - Revenue concentration ▲ red (risk)
   - Cost/revenue ratio ▲ red (margin compression)
   - Sparkline ▲ green (just trend direction, neutral)
6. **Sub-tab buttons class:** `.sub-nav-btn` not `.sub-tabs` — common selector mistake.
7. **Section scope discipline:**
   - Procurement = raw materials only (4 buckets: yarn, chemical, dye, greige_fabric)
   - Cost Structure = operational (utilities, maintenance, packaging, overhead, outsourced, logistics)
   - Revenue = core_product_sales + outsourced_service_revenue (yarn_resale excluded)

## 8. KEY FILES IN REPO (commit 7eb5f15 sonrası mevcut hali)

### Migrations (this push, all applied)
- `migrations/022_v_top_cost_suppliers.sql` — cost-bucket-scoped top suppliers with bucket spread
- `migrations/023_v_cost_kpis.sql` — 6-metric cost KPI view + 3m window labels
- `migrations/024_rescope_procurement_to_raw_materials.sql` — 4 view DROP+RECREATE
- `migrations/025_v_cost_movers.sql` — 3-slot UNION ALL (increase/decrease/volatility)
- `migrations/026_v_overview_signals.sql` — 4-slot rule-based signal engine

### Earlier migrations (before this chat)
- `migrations/015_v_top_suppliers_overall.sql`
- `migrations/016b_v_procurement_kpis.sql`
- `migrations/017_v_procurement_concentration_trend.sql`
- `migrations/018_v_monthly_procurement_by_currency.sql`
- `migrations/019_v_top_customers_overall.sql`
- `migrations/020_v_revenue_kpis.sql` (and `020b` correction)
- `migrations/021_v_customer_concentration_trend.sql`

### Scripts (this push)
- `scripts/m24_1_top_cost_suppliers.py`
- `scripts/m24_2_kpi_strip.py`
- `scripts/m24_3_mix_chart.py`
- `scripts/m24_4_movers_strip.py`
- `scripts/m25_1_signals_strip.py`
- `scripts/m25_2_sparklines.py`
- `scripts/m25_3_section_badges.py`

### Scripts (uncommitted, Counterparty UI fix)
- `scripts/cp_ui_fix.py`

### Frontend (modified)
- `dashboard/server.py` — endpoints: `/api/internal/top-cost-suppliers`, `/api/internal/cost-kpis`, `/api/internal/cost-movers`, `/api/internal/overview-signals`, plus pre-existing top-customers, top-suppliers etc.
- `dashboard/static/index.html` — Overview signals strip container, Cost sub-section KPI/movers/mix containers, Cost suppliers table container, section header IDs (data-target attrs)
- `dashboard/static/app.v5.js` — many additions: loadCostSuppliersTable, loadCostKpis, loadCostMovers, loadOverviewSignals, renderSectionHealthBadges, renderOpsCostMixChart, _kpiSparklineSeries, _renderSparklineSvg, sub-tab activation hooks
- `dashboard/static/style.v5.css` — `.proc-kpi-context-3`, `.cost-mover-card` (3 kind variants), `.signal-card` (3 severity variants), `.kpi-sparkline-*`, `.ops-section-header` + `.section-health-*`, plus new Counterparty CSS rewrite (uncommitted)

## 9. YAPACAĞIN İLK İŞ YENİ CHAT'TE

Kullanıcı (Mert) muhtemelen yeni chat'e geçtiğinde önce **Counterparty UI fix kontrolü** yapacak. Sen şu adımı sor:

> "Counterparty UI fix patch'i uygulanmış ama browser'da görsel kontrol yapılmamıştı. Önce Operations → Counterparty'e bak, bir supplier seç, tablolar düzgün okunuyor mu? Screenshot atarsan veya 'tamam' dersen, Counterparty UI fix'ini commit edeceğiz, sonra ne istersen ona geçeriz."

Kontrol sonrası seçenekler:
- **A) Counterparty UI fix commit et**, sonra ROADMAP.md'yi güncelle (M2.4/M2.5 ✅ + Counterparty UI fix ✅), Phase 2 deferred listesi netleştir
- **B) Phase 2 işlerine başla** — M2.6 (deepening: drawer, filter architecture, monthly variance drivers) için scope çıkar
- **C) Portfolio çalışması** — Rayon Intelligence için LinkedIn post + GitHub README screenshot + Notion case study
- **D) Tekstil Haber Botu v3 debug** — 504 textileworld + zero-new-article
- **E) Faz 2 öğrenme** — LLM API/Prompt → RAG → AI Agents

## 10. ÖNEMLİ DETAYLAR

- **YARN MASTER Phase 1 ✅** zaten tamamlanmış (önceki chat'lerde): dim_yarn_master (21 canonical spec), dim_yarn_price_driver (20 active), dim_yarn_label_alias (31 alias), fact_supplier_quotes, fact_yarn_price_pressure. Coverage: PES FDY/DTY + PA6/PA66. Phase 2'de cotton/blend/viscose/elastane gelecek.
- **Texhibition scraper ✅** — 500 katılımcı, 9 rakip sinyal (Karsu E-6, Lenzing A-1, Zorlu C-15, vs).
- **İç veri ✅** — yarn_costs (245 kayıt), orders (1484), order_invoices (2459), trade_flows (1714, 7 HS kod).
- **Lescon ETL ✅** — 532 satır lescon_sales (örme 481, dokuma 51).

---

**Son söz:** Bu doküman yeni chat'in ilk mesajı olarak yapıştırılmalı. Yeni chat'teki Claude bunu okuyunca tüm proje bağlamı + kaldığımız yer + sırada ne var net olarak elinde olur. Hiçbir bilgi kaybı olmaz.
