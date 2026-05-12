# Phase F: Tender Intelligence Engine — Design Document

**Version:** 1.1 (Approved for implementation)
**Date:** 12 Mayıs 2026
**Owner:** Mert Övet
**Architecture:** Mert + Claude (joint design)
**Status:** Approved. F0 implementation in progress.
**Phase E status at design time:** P1 step 5+6 committed (b489019, pushed). P1 step 7–10 deferred until Phase F initial scope (F0 + F1) is complete.

### Changelog

| Ver | Date | Changes |
|---|---|---|
| 1.0 | 12 May 2026 14:00 | Initial draft. Awaiting review of three approval points. |
| 1.1 | 12 May 2026 14:30 | Mert review complete. A.1 frozen as canonical mandatory core. A.2 supplementary recall layer approved with Mert's exact list (yanmaz kumaş replaces güç tutuşmaz kumaş; outdoor kıyafet replaces outdoor kumaş; teknik tekstil + flame retardant added; koruyucu giysi removed). A.3 confirmed as soft-reject (REJECTED flag + history log, no row deletion). CPV scoring deferred to F3 per Mert. |

---

## Table of Contents

1.  [Executive Summary](#1-executive-summary)
2.  [Strategic Context](#2-strategic-context)
3.  [Scope & Non-Goals](#3-scope--non-goals)
4.  [Data Source Strategy](#4-data-source-strategy)
5.  [Architecture Overview](#5-architecture-overview)
6.  [Database Schema](#6-database-schema)
7.  [Ingestion Layer (Bronze)](#7-ingestion-layer-bronze)
8.  [Normalization Layer (Silver)](#8-normalization-layer-silver)
9.  [Relevance Engine (Gold)](#9-relevance-engine-gold)
10. [LLM Enrichment](#10-llm-enrichment)
11. [Integration with Market Signals](#11-integration-with-market-signals)
12. [Dashboard Tab Design](#12-dashboard-tab-design)
13. [Notification Layer](#13-notification-layer)
14. [Operational Concerns](#14-operational-concerns)
15. [Rollout Roadmap (F0 → F5)](#15-rollout-roadmap-f0--f5)
16. [Risk Analysis & Mitigations](#16-risk-analysis--mitigations)
17. [Success Metrics](#17-success-metrics)
18. [Appendix A: Canonical Keyword List](#appendix-a-canonical-keyword-list)
19. [Appendix B: CPV Codes Reference](#appendix-b-cpv-codes-reference)
20. [Appendix C: Known False Positive Patterns](#appendix-c-known-false-positive-patterns)

---

## 1. Executive Summary

The Tender Intelligence Engine is a new module of the Rayon Intelligence Platform that monitors Turkish public procurement (and, in later phases, defence and international procurement) sources, automatically detecting tenders relevant to Rayon Tekstil's product portfolio (technical textiles, protective clothing, military and operational fabrics, FR/waterproof/coated fabrics, uniforms).

The system is NOT a keyword scraper. It is a **relevance-filtered intelligence engine** built to deliver **few, high-precision signals** rather than a large noisy feed. The primary KPI is **relevance precision** (false-positive rate), not coverage.

**Key inputs (locked by Mert):**

-   Seed keyword set (11 phrases with aksanız/aksanlı variants — see Appendix A)
-   Status filter: *only* `teklif vermeye açık / katılıma açık` (currently open for bidding)
-   Geography: Turkish public procurement initially; future expansion to MSB / SSB / NATO / UN / EU
-   Integration target: existing Market Signals architecture, including signal cards, Telegram bot, and dashboard

**Architecture:** Bronze (raw) → Silver (normalized) → Gold (relevance-scored). Each layer is independently testable and idempotent.

**Initial source:** EKAP (Elektronik Kamu Alımları Platformu) — both the public bulletin PDF (deterministic) and the web search interface (real-time). Multi-source from F2 onwards.

**Initial cost envelope:** ~$0.50–2.00 / month in LLM costs at F1 scope (~20–50 tenders/day post-filter), well below the existing Market Signals envelope.

---

## 2. Strategic Context

### 2.1 Why this matters for Rayon

Rayon Tekstil already supplies a customer segment described in the company's profile as *"tender suppliers"*. Today, that segment is served reactively: tender suppliers find Rayon and request fabric quotes. The Tender Intelligence Engine flips this to proactive: Rayon sees the tender as soon as it is published and can either (a) approach the eventual tender bidders directly with a pre-built fabric proposal, or (b) consider bidding directly via a trusted partner.

In addition, three secondary benefits:

1.  **Demand visibility.** Aggregating textile-related public tenders over time yields a unique view of public-sector textile demand patterns (uniform refresh cycles, FR clothing tenders by region, etc.). No competitor in TR has this.
2.  **Pricing pressure inference.** Estimated values on textile tenders are a leading indicator of public-sector fabric pricing expectations.
3.  **Defence pipeline.** SSB / MSB tenders specifically intersect with Rayon's technical fabric capability (FR, coated, laminated). Tracking these systematically opens a defence-adjacent channel.

### 2.2 Competitive context

Most Turkish textile manufacturers (per Mert's industry observation) monitor EKAP manually, by individual operators searching for keywords. There is no intelligence layer, no relevance scoring, no alerting, no historical trend. The Tender Intelligence Engine, embedded in a platform that also covers market signals, raw-material price signals, export intelligence, and yarn intelligence, becomes a category-defining capability for Rayon and a future consulting product.

### 2.3 Phase F's relationship to Phase E

Phase E's Market Signals module already handles unstructured external information (news articles) through an LLM-assisted relevance pipeline. Phase F is the same architectural pattern applied to a structured-but-noisy data source (tender listings). Lessons from Phase E P0/P1 directly inform Phase F:

-   **Threshold + LLM hybrid** (not pure keyword) is required for acceptable precision.
-   **Exposure layer** (Mig 011's `commercial_exposure_type`, `affected_business_line`, etc.) generalizes to tenders.
-   **Failed jobs + retry** infrastructure already exists; reuse, do not rebuild.
-   **Telegram reporter** already exists; extend the same channel rather than open a new one.

---

## 3. Scope & Non-Goals

### 3.1 In scope (F1 MVP)

-   Ingest all newly published tenders from EKAP daily (PDF bulletin + web search hybrid).
-   Filter to tenders matching the canonical keyword list (Appendix A) at title or body level.
-   Filter to `tender_status = 'open'` AND `deadline_at > NOW()`.
-   Apply rule-based + keyword-weighted relevance scoring.
-   Persist all raw + scored tenders in PostgreSQL (Bronze + Gold).
-   Surface HIGH / MEDIUM relevance tenders as Market Signals (signal_type = `tender_active`).
-   Render a new dashboard tab: **Tender Intelligence** (active tenders, sorted by deadline + relevance).
-   Telegram alert on HIGH-relevance new tenders.

### 3.2 In scope (F2–F5)

-   LLM enrichment (semantic relevance, false-positive reduction, Rayon-fit scoring).
-   Multi-source ingestion (MSB, SSB, municipality portals, defence procurement feeds).
-   Historical archive (closed tenders) for demand-trend dashboards.
-   Per-tender competitive analysis ("likely bidders" based on past awards).

### 3.3 Explicitly out of scope (any phase)

-   Auto-bidding or e-tender submission on Rayon's behalf.
-   Direct integration with EKAP's authenticated APIs (would require KİK registration and is not necessary for public tender visibility).
-   Forecasting tender awards (statistical inference on tender outcomes) — possible long-term but not Phase F.
-   Building a stand-alone product. Phase F lives inside the Rayon Intelligence Platform; productization is a Phase G+ consideration.

---

## 4. Data Source Strategy

EKAP exposes tender data through several surfaces, each with different trade-offs. The F1 design uses **two primary surfaces** in parallel for redundancy and freshness:

### 4.1 Source matrix

| Source | URL | Update frequency | Format | Auth required | F1 use |
|---|---|---|---|---|---|
| **EKAP Kamu İhale Bülteni (PDF)** | `ekap.kik.gov.tr/ekap/ilan/bultenindirme.aspx` | Daily (≈ 18:00 Istanbul, contains tenders for the next ~30 days) | PDF | No | **PRIMARY** — deterministic, structured, authoritative |
| **EKAP V2 Web Search** | `ekapv2.kik.gov.tr/ekap/search` | Real-time as tenders are published | SPA / JSON API (to be confirmed via DevTools) | No (anonymous search works) | **SECONDARY** — fills the gap between daily bulletin drops |
| **EKAP V1 KSP Search (legacy)** | `ekap.kik.gov.tr/ekap/ortak/ksp/kspihalearama.aspx` | Same as V2 | ASP.NET WebForms (POST-back) | No | Fallback only if V2 is unavailable |
| **EKAP API (mobile)** | Discoverable via mobile app traffic capture | Real-time | JSON | Possibly | Future (F2) — pending API contract |

### 4.2 Why the PDF bulletin first

The **Kamu İhale Bülteni** PDF is, per KİK's own statement (see `bultenindirme.aspx`), the authoritative source: *"EKAP üzerinden arama yapılarak erişilen ilan bilgileri ile Kamu İhale Bülteninde yer alan ilan bilgileri metni arasında farklılık olması durumunda pdf formatındaki Kamu İhale Bülteni esas alınacaktır."*

In other words: **if the web search and the PDF bulletin disagree, the PDF wins.**

Operationally this means:

-   The PDF gives us the **canonical** record per tender (we never have to second-guess the data).
-   It is structured enough to parse reliably (each tender has a fixed-shape entry).
-   Daily fetch + parse is a simple, robust cron with predictable failure modes.

The web search adds **intraday freshness** but is treated as a "preview" feed — values are eventually reconciled against the next day's PDF.

### 4.3 PDF parsing approach

The bulletin is structured: each tender appears as a section with consistent headers (`İhale Kayıt Numarası`, `İdarenin adı`, `İhale konusu`, `İhale tarih ve saati`, etc.). Parsing strategy:

1.  Use `pdfplumber` or `pypdfium2` to extract text per page.
2.  Apply a section splitter (regex on "İhale Kayıt Numarası" headers) to chunk the document into per-tender records.
3.  For each chunk, parse fixed-position fields with a small set of regex patterns.
4.  Fallback: if a chunk fails strict parsing, store raw text in `raw_text` and flag for manual review.

We do not attempt OCR — the bulletin is text-native PDF.

### 4.4 Web scraping approach (EKAP V2)

The V2 search is a SPA. The approach is to **reverse-engineer the JSON API** that the SPA uses internally:

1.  Manual step (one-time): Open `ekapv2.kik.gov.tr/ekap/search` in Chrome DevTools, perform a search, capture the XHR requests in the Network tab.
2.  Identify the search endpoint URL, request shape, and pagination contract.
3.  Replay the request from Python (`requests`) with the same headers and body.
4.  If the API rejects anonymous requests, fall back to Playwright (headless browser).

This work is **F2**, not F1. F1 ships PDF-only.

### 4.5 robots.txt + rate limiting policy

`robots.txt` for `ekapv2.kik.gov.tr` could not be fetched in the design session due to an SSL handshake failure (likely an upstream proxy issue, not a real policy block). Before F1 ingestion goes live we must:

-   Manually verify the robots.txt from a browser.
-   Default to **conservative** rate limiting: at most 1 request per 2 seconds, with daily request cap < 1000 for F1 (vastly below typical commercial scrapers).
-   Set a descriptive `User-Agent` identifying the platform (`RayonIntelligence/F1 (research; contact: ...)`).
-   Honour any `Retry-After` headers immediately.

Public procurement is by law (4734 sayılı Kanun) a public-transparency function. Scraping for industry intelligence is a legitimate, non-commercial-resale use. We are not republishing the data; we are filtering it for one company's internal decision-making.

---

## 5. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                  EXTERNAL SOURCES (Section 4)                   │
│                                                                 │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────────┐      │
│  │ Daily PDF     │  │ EKAP V2      │  │ Future (F2+):    │      │
│  │ Bulletin      │  │ Web Search   │  │ MSB / SSB /      │      │
│  │ (~18:00 TR)   │  │ (intraday)   │  │ NATO / UN / EU   │      │
│  └───────┬───────┘  └──────┬───────┘  └────────┬─────────┘      │
└──────────┼─────────────────┼───────────────────┼────────────────┘
           │                 │                   │
           ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  BRONZE: scrapers/tender_ingestion/                             │
│  - ekap_bulletin_scraper.py      (daily, 19:00 IST)             │
│  - ekap_v2_search_scraper.py     (every 30 min)                 │
│  - <future source>_scraper.py                                   │
│                                                                 │
│  Writes:  tenders_raw (raw_html, raw_text, raw_payload JSONB)   │
│  Idempotency: UNIQUE(source, ekap_id)                           │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  SILVER: scrapers/tender_normalize.py                           │
│  - Turkish text normalization (aksanlı → aksanız, lowercase)    │
│  - Field extraction & validation                                │
│  - Status interpretation (`open` / `closed` / etc.)             │
│  - Deduplication (same tender across PDF + V2 sources)          │
│                                                                 │
│  Writes:  tenders (normalized, deduped record)                  │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  GOLD: scrapers/tender_relevance_engine.py                      │
│  - Keyword matcher (canonical list + variants)                  │
│  - Exclusion rule engine (false-positive patterns)              │
│  - Rule-based scoring → preliminary relevance_level             │
│  - F3+: LLM enrichment for HIGH/MEDIUM candidates               │
│                                                                 │
│  Writes:  tenders.relevance_*, matched_keywords[],              │
│           rejection_reason; emits market_signals rows           │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  INTEGRATION                                                    │
│  - market_signals INSERT (signal_type='tender_active')          │
│  - Telegram bot ping for HIGH (instant alert)                   │
│  - Dashboard tab "Tender Intelligence" reads tenders + signals  │
└─────────────────────────────────────────────────────────────────┘
```

Each layer is:

-   **Idempotent**: rerunning the same input produces the same output (UNIQUE constraints + UPSERT semantics).
-   **Independently testable**: Bronze can be unit-tested against fixture PDFs; Silver against raw fixtures; Gold against normalized fixtures.
-   **Recoverable**: if Gold logic changes, we can replay Gold over Silver without re-ingesting Bronze.

This is the **same pattern** used by the existing news-scraping pipeline (`scrapers/llm_analyzer.py` operates on `news_items`), so the cognitive overhead for the engineer (Mert) is minimal.

---

## 6. Database Schema

Three new tables (`tenders`, `lkp_tender_keywords`, `tender_relevance_history`) plus a small extension to `market_signals` (no schema change — new signal_type values).

### 6.1 `tenders` (Gold layer; the canonical record)

```sql
CREATE TABLE tenders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source identification
    source TEXT NOT NULL,                  -- 'ekap_bulletin' | 'ekap_v2_search' | 'msb' | ...
    ekap_id TEXT NOT NULL,                 -- İhale Kayıt Numarası (e.g. '2026/123456')
    source_url TEXT,

    -- Core fields
    title TEXT NOT NULL,
    description TEXT,
    institution TEXT NOT NULL,             -- İdarenin adı (e.g. 'İstanbul Büyükşehir Belediyesi')
    institution_city TEXT,                 -- Best-effort city extraction
    procurement_type TEXT,                 -- 'Mal' | 'Hizmet' | 'Yapım' | 'Danışmanlık' | NULL
    procurement_method TEXT,               -- 'Açık ihale' | 'Belli istekliler' | 'Pazarlık' | NULL
    cpv_code TEXT,                         -- e.g. '18221000' (waterproof clothing)
    cpv_description TEXT,

    -- Financial
    estimated_value_try NUMERIC(18, 2),    -- Yaklaşık maliyet, if disclosed
    estimated_value_disclosed BOOLEAN DEFAULT FALSE,
    currency TEXT DEFAULT 'TRY',

    -- Timestamps
    published_at TIMESTAMP WITH TIME ZONE, -- İlan tarihi
    deadline_at TIMESTAMP WITH TIME ZONE,  -- İhale tarih ve saati (teklif son tarihi)
    discovered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Status
    tender_status TEXT NOT NULL,           -- 'open' | 'closed' | 'cancelled' | 'evaluating' | 'awarded' | 'unknown'
    status_last_checked_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Raw payload (preserved for replay / audit)
    raw_text TEXT,
    raw_payload JSONB,

    -- Relevance assessment (filled by Gold layer)
    relevance_level TEXT,                  -- 'HIGH' | 'MEDIUM' | 'LOW' | 'REJECTED'
    relevance_score INTEGER,               -- 0..100
    matched_keywords TEXT[],               -- Distinct keywords from Appendix A that hit
    rejection_reason TEXT,                 -- For relevance_level='REJECTED', why

    -- Rayon-specific scoring (filled by LLM in F3+)
    fit_technical_textile INTEGER,         -- 0..100
    fit_protective_clothing INTEGER,
    fit_military INTEGER,
    fit_waterproof INTEGER,
    fit_fr INTEGER,
    estimated_competition TEXT,            -- 'low' | 'medium' | 'high' | NULL
    likely_buyer_type TEXT,                -- e.g. 'Defense', 'Police', 'Hospital', 'Municipality', 'Other'

    -- LLM trace
    llm_model TEXT,
    llm_tokens_in INTEGER,
    llm_tokens_out INTEGER,
    llm_cost_usd NUMERIC(10, 6),
    llm_processed_at TIMESTAMP WITH TIME ZONE,

    -- Exposure layer (mirrors Mig 011 on market_signals for consistency)
    rayon_why_it_matters TEXT,
    affected_business_line JSONB,          -- ["woven","knit","technical","coated","OTHER"]
    affected_material_family JSONB,        -- ["polyester","nylon","FR","membrane",...]
    category TEXT,                         -- Free-form, LLM-assigned

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    UNIQUE (source, ekap_id),
    CHECK (tender_status IN ('open','closed','cancelled','evaluating','awarded','unknown')),
    CHECK (relevance_level IS NULL OR relevance_level IN ('HIGH','MEDIUM','LOW','REJECTED')),
    CHECK (relevance_score IS NULL OR (relevance_score BETWEEN 0 AND 100)),
    CHECK (procurement_type IS NULL OR procurement_type IN ('Mal','Hizmet','Yapım','Danışmanlık'))
);

-- Generated column for the very common "active right now" predicate
-- (separate column rather than a view so it can be indexed efficiently)
ALTER TABLE tenders
    ADD COLUMN is_active BOOLEAN GENERATED ALWAYS AS (
        tender_status = 'open' AND deadline_at > NOW()
    ) STORED;
-- NOTE: NOW() in a STORED generated column is NOT supported in PostgreSQL
-- (immutable functions only). In practice this needs to be a VIEW or a
-- regular column maintained by the application + a daily sweep job.
-- DESIGN DECISION (final): use a VIEW (v_active_tenders) instead.

CREATE INDEX idx_tenders_status        ON tenders(tender_status);
CREATE INDEX idx_tenders_deadline      ON tenders(deadline_at) WHERE tender_status = 'open';
CREATE INDEX idx_tenders_relevance     ON tenders(relevance_level);
CREATE INDEX idx_tenders_published     ON tenders(published_at DESC);
CREATE INDEX idx_tenders_kw_gin        ON tenders USING GIN(matched_keywords);
CREATE INDEX idx_tenders_bizline_gin   ON tenders USING GIN(affected_business_line);
CREATE INDEX idx_tenders_matfam_gin    ON tenders USING GIN(affected_material_family);
```

The `is_active` line above is left in the doc deliberately as a teaching note. The final schema uses a view:

```sql
CREATE VIEW v_active_tenders AS
SELECT *
FROM tenders
WHERE tender_status = 'open'
  AND deadline_at > NOW();
```

### 6.2 `lkp_tender_keywords` (canonical keyword lookup)

```sql
CREATE TABLE lkp_tender_keywords (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword TEXT NOT NULL UNIQUE,           -- Original form, e.g. "kumaş"
    normalized TEXT NOT NULL,               -- Aksanız + lowercase, e.g. "kumas"
    keyword_class TEXT NOT NULL,            -- 'high_priority' | 'medium_priority' | 'exclusion'
    weight INTEGER NOT NULL DEFAULT 10,     -- Points contributed to relevance_score on match
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CHECK (keyword_class IN ('high_priority','medium_priority','exclusion')),
    CHECK (weight BETWEEN -100 AND 100)     -- Exclusion keywords have negative weights
);

CREATE INDEX idx_tender_kw_class ON lkp_tender_keywords(keyword_class);
CREATE INDEX idx_tender_kw_norm  ON lkp_tender_keywords(normalized);
```

Seed values per Appendix A are populated by migration `015_seed_tender_keywords.sql`.

### 6.3 `tender_relevance_history` (audit log)

Every time the relevance engine assesses a tender, we log it. This lets us see *why* a tender was rejected (or accepted) historically, and replay analyses when rules change.

```sql
CREATE TABLE tender_relevance_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tender_id UUID NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    assessed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    engine_version TEXT NOT NULL,          -- e.g. 'rule_v1', 'rule_v1+llm_v1', 'rule_v2'
    method TEXT NOT NULL,                  -- 'keyword_rule' | 'llm_enrichment' | 'manual_override'
    relevance_level TEXT,
    relevance_score INTEGER,
    matched_keywords TEXT[],
    rejection_reason TEXT,
    reasoning TEXT,                        -- LLM-generated, or human note if manual
    llm_model TEXT,
    llm_cost_usd NUMERIC(10, 6),
    CHECK (relevance_level IS NULL OR relevance_level IN ('HIGH','MEDIUM','LOW','REJECTED'))
);

CREATE INDEX idx_trh_tender   ON tender_relevance_history(tender_id, assessed_at DESC);
CREATE INDEX idx_trh_assessed ON tender_relevance_history(assessed_at DESC);
```

### 6.4 `market_signals` extension (no schema change)

We add a new value to the existing `signal_type` column. No DDL needed (the column is free-form `TEXT`).

```
signal_type = 'tender_active'    -- A newly discovered, currently-open relevant tender
signal_type = 'tender_closing'   -- A tender about to expire in <72h that we've already surfaced (optional reminder)
signal_type = 'tender_status_change'  -- A tracked tender moved open → closed / cancelled
```

The `source_table` column gets a new value: `'tenders'`. The `source_id` column stores the `tenders.id` UUID. From the dashboard's perspective, tender signals join cleanly with the existing `market_signals` feed.

### 6.5 Migration plan

Three new migrations:

-   **`013_create_tenders.sql`** — `tenders` table + view + indexes
-   **`014_create_tender_keywords_history.sql`** — `lkp_tender_keywords` + `tender_relevance_history`
-   **`015_seed_tender_keywords.sql`** — INSERT seed keywords (Appendix A)

No changes to existing tables. Phase F is purely additive at the database level.

---

## 7. Ingestion Layer (Bronze)

### 7.1 PDF Bulletin Scraper

**File:** `scrapers/tender_bulletin_scraper.py`
**Schedule:** Daily, 19:00 Istanbul (PDF typically posted ~18:00; we leave a 1h buffer).
**Idempotency:** Each tender keyed by `(source='ekap_bulletin', ekap_id)`. UPSERT semantics: if the tender already exists, update fields that may have changed (status, deadline if amended, raw_text), preserve relevance assessment.

**Algorithm:**

1.  Compute today's bulletin URL (KİK pattern: known once we inspect `bultenindirme.aspx`).
2.  `GET` the PDF. On 404, retry every 10 minutes for up to 2 hours, then record `failed_jobs` and exit cleanly.
3.  Parse the PDF into per-tender chunks using a section-header regex.
4.  For each chunk:
    -   Extract `ekap_id`, `title`, `institution`, `deadline_at`, `procurement_type`, `procurement_method`, `cpv_code`, `estimated_value_try` (if disclosed), `source_url` (link back to EKAP detail page).
    -   Set `tender_status = 'open'` (bulletin only contains open tenders by definition).
    -   Set `source = 'ekap_bulletin'`.
    -   Store the full chunk in `raw_text`.
    -   UPSERT into `tenders`.
5.  At end, log per-day counts (tenders ingested, parsing failures) to `failed_jobs` only on failure.

**Failure modes:**

| Failure | Detection | Recovery |
|---|---|---|
| Bulletin not yet published | 404 from GET | Retry loop, then defer to tomorrow |
| PDF format change | Section regex matches < 90% of expected entries | Alert via Telegram, halt ingestion, store raw PDF for inspection |
| Single tender chunk fails parsing | Per-chunk try/except | Store chunk in `failed_jobs.payload` with `job_type='parse_tender_chunk'`, continue with next chunk |
| DB unique violation on UPSERT | DBError | Should never happen with proper ON CONFLICT clause |

### 7.2 EKAP V2 Search Scraper (F2)

**File:** `scrapers/tender_ekap_v2_scraper.py`
**Schedule:** Every 30 minutes during Turkish business hours (08:00–20:00).
**Idempotency:** Same `(source='ekap_v2_search', ekap_id)` keying.

This scraper is intentionally **deferred to F2**. Implementing it requires API reverse-engineering work that adds calendar time without adding much value beyond what the daily bulletin already provides. F1 ships with PDF-only and a clear note that intra-day freshness is a known F2 deliverable.

### 7.3 Source reconciliation (F2+)

When the same tender (same `ekap_id`) appears in both `ekap_bulletin` and `ekap_v2_search` sources, we keep both records (different `source` values). The downstream Silver layer treats the bulletin record as canonical and uses the V2 record only to fill in fields the bulletin omitted (or to detect status changes faster).

This is not an F1 concern; documented here for completeness.

---

## 8. Normalization Layer (Silver)

**File:** `scrapers/tender_normalize.py`
**Trigger:** Runs as part of the same cron as the relevant ingestion scraper, immediately after Bronze write succeeds (in-process), so that each tender hits Gold within the same job.

**Tasks:**

### 8.1 Turkish character normalization

A small utility for matching purposes (not destructive — we keep the original strings in `title`, `description`, etc.):

```python
TR_MAP = str.maketrans({
    'ç':'c', 'Ç':'c', 'ğ':'g', 'Ğ':'g', 'ı':'i', 'İ':'i',
    'ö':'o', 'Ö':'o', 'ş':'s', 'Ş':'s', 'ü':'u', 'Ü':'u',
})

def tr_normalize(text: str) -> str:
    return text.lower().translate(TR_MAP) if text else ''
```

This is used at match time, not at storage time. We store original casing/diacritics; we compare on the normalized form.

### 8.2 Field validation

-   `deadline_at` must be a parseable datetime in `Europe/Istanbul`. If parsing fails, store NULL and mark the record for manual review.
-   `estimated_value_try` must be a positive number when present (KİK occasionally publishes a literal "Bilgi verilmemiştir" for confidential estimates — we map that to NULL + `estimated_value_disclosed = FALSE`).
-   `cpv_code` is sanity-checked against the CPV vocabulary length (8 digits).

### 8.3 Status interpretation

EKAP uses a small set of status strings. Mapping:

| EKAP string | Our `tender_status` |
|---|---|
| "Teklif vermeye açık" / "Katılıma açık" / "İhale ilanı yayımlandı" | `open` |
| "Teklif değerlendirmesi yapılıyor" / "Sözleşme imzalanmadı" | `evaluating` |
| "İptal" / "İhale iptal edildi" | `cancelled` |
| "Sözleşme imzalandı" / "İhale tamamlandı" | `awarded` |
| "Süresi doldu" / Deadline in past | `closed` |
| Anything else | `unknown` |

### 8.4 Cross-source dedup (F2+)

When two records share the same `ekap_id` but different `source`, we treat the bulletin record as canonical and the search record as a freshness signal only.

---

## 9. Relevance Engine (Gold)

**File:** `scrapers/tender_relevance_engine.py`
**Trigger:** Runs immediately after each tender is written to Silver, within the same cron job.

The engine has two stages:

### Stage 1: Rule-based scoring (always runs)

```
relevance_score = 0
matched_keywords = []

For each keyword K in lkp_tender_keywords:
    normalized_target = tr_normalize(tender.title + ' ' + tender.description)
    if K.normalized in normalized_target:
        if K.keyword_class == 'exclusion':
            relevance_level = 'REJECTED'
            rejection_reason = f'Exclusion match: {K.keyword}'
            break
        else:
            relevance_score += K.weight
            matched_keywords.append(K.keyword)

If no exclusion match:
    if relevance_score >= 50:  level = 'HIGH'
    elif relevance_score >= 20: level = 'MEDIUM'
    elif relevance_score >= 1:  level = 'LOW'
    else:                       level = 'REJECTED'
                                rejection_reason = 'No keyword match'
```

Weights (proposed initial values — see Appendix A):

| Keyword class | Weight |
|---|---|
| HIGH priority (`askeri tekstil`, `polis kumaş`, `asker kumaş`, `güvenlik kumaş`) | 40 each |
| MEDIUM priority (`tekstil`, `kumaş`, `konfeksiyon`, `üniforma`) | 25 each |
| LOWER (`personel kıyafeti`, `iş elbisesi`, `iş kıyafeti`) | 15 each |
| EXCLUSION (`tekstil fabrikası`, `tekstil kortlu`, `tekstil atık`, `mefruşat`, `perde`, `çarşaf`, `yapım`) | -100 (instant reject) |

These weights deliberately bias toward **few HIGH-relevance signals**. The first month of operation calibrates them.

### Stage 2: LLM enrichment (F3+, optional in F1)

For tenders with rule-based `relevance_level` ∈ {HIGH, MEDIUM}, optionally call `gpt-4o-mini` to:

1.  Confirm or downgrade the relevance.
2.  Generate `rayon_why_it_matters` (one-sentence Turkish summary, mirroring the exposure-layer pattern from Mig 011).
3.  Populate `fit_technical_textile`, `fit_protective_clothing`, `fit_military`, `fit_waterproof`, `fit_fr`, `likely_buyer_type`, `estimated_competition`, `affected_business_line`, `affected_material_family`.

Cost estimate: ~$0.001 per tender × ~30 HIGH/MEDIUM tenders per day = **~$0.03/day** ($0.90/month).

For tenders with `relevance_level` ∈ {LOW, REJECTED}, no LLM call. They remain in the DB for audit and future re-evaluation if rules change.

### Stage 3: Signal emission

For tenders with final `relevance_level` ∈ {HIGH, MEDIUM}:

```python
INSERT INTO market_signals (
    signal_type, severity, title, body,
    source_table, source_id, source_url,
    signal_category, action_tag, impact_score,
    rayon_why_it_matters, affected_business_line, affected_material_family,
    commercial_exposure_type, entity_name, entity_role,
    signal_priority_profile, ...
) VALUES (
    'tender_active',
    'alert' if HIGH else 'warning',
    f'YENİ İHALE: {tender.title[:100]}',
    f'İdare: {tender.institution}. Son tarih: {tender.deadline_at:%Y-%m-%d %H:%M}. Yaklaşık maliyet: {tender.estimated_value_try:,.0f} TRY.',
    'tenders',
    tender.id,
    tender.source_url,
    'TENDER',
    'OPPORTUNITY',
    tender.relevance_score,
    tender.rayon_why_it_matters,
    tender.affected_business_line,
    tender.affected_material_family,
    'OUTPUT_DEMAND',
    tender.institution,
    'customer',
    'DEMAND',  -- signal_priority_profile
    ...
);
```

This is where the Phase E P1 exposure layer pays for itself: tender signals slot cleanly into the existing Market Signals UI with the same field set.

---

## 10. LLM Enrichment

### 10.1 Prompt design

The system prompt for tender relevance is a sibling of the news LLM prompt (`scrapers/llm_analyzer.py::build_system_prompt`), with these differences:

-   Input is **structured** (title, institution, procurement_type, CPV code, description) rather than free-form article text.
-   Output schema includes Rayon-fit scoring fields, not just market-signal classification.
-   The prompt explicitly enumerates **false-positive patterns** (Appendix C) so the LLM knows what to downgrade.

A separate file is preferable: `scrapers/tender_llm_analyzer.py`. Sharing the existing `build_system_prompt` would couple two distinct prompts and is not advised.

### 10.2 Output schema

```json
{
  "relevance_confirmed": true,
  "relevance_level": "HIGH" | "MEDIUM" | "LOW" | "REJECTED",
  "relevance_reasoning": "Tek cümle Türkçe açıklama.",
  "rayon_why_it_matters": "Bu ihale Rayon için ... ",
  "category": "FR clothing | Military uniform | Police uniform | ...",
  "likely_buyer_type": "Defense | Police | Hospital | Municipality | Other",
  "estimated_competition": "low | medium | high",
  "fit_technical_textile": 0-100,
  "fit_protective_clothing": 0-100,
  "fit_military": 0-100,
  "fit_waterproof": 0-100,
  "fit_fr": 0-100,
  "affected_business_line": ["woven","knit","technical","coated","OTHER"],
  "affected_material_family": ["polyester","nylon","FR","membrane","mixed","OTHER"]
}
```

### 10.3 Validation logic (post-LLM)

Same pattern as `llm_analyzer.py` Phase E P1 validation:

-   Levels not in the valid set → fall back to rule-based level.
-   Scores outside 0–100 → clamp.
-   Empty `rayon_why_it_matters` → placeholder.

---

## 11. Integration with Market Signals

The Tender Intelligence module produces records in **both** new tables (`tenders`) and the existing one (`market_signals`). The mapping is intentionally lossy — `market_signals` is the user-facing surface and only carries what the dashboard needs to render a signal card. `tenders` is the analytics surface and carries everything.

**Lifecycle of a tender's market signal:**

| Event | market_signal change |
|---|---|
| Tender discovered, relevance HIGH/MEDIUM | INSERT new row, `severity='alert'`/`'warning'` |
| Tender's status changes to closed/cancelled | UPDATE: append a closing-note to `body`, no severity change |
| Tender's deadline within 72h | INSERT a *separate* `tender_closing` signal (one-shot reminder) |
| Tender's relevance is re-assessed and downgraded to LOW/REJECTED | UPDATE: `archived_at = NOW()` (we add this column in F1 — small migration) |

This keeps the Market Signals dashboard tab honest: signals reflect *current* relevance and *current* tender status.

---

## 12. Dashboard Tab Design

### 12.1 Tab name & position

**"Tender Intelligence"** — 6th tab, after "Yarn Intelligence". Matches existing tab naming convention.

### 12.2 Layout (top to bottom)

1.  **KPI strip** (4 cards):
    -   Active tenders matching keywords (count)
    -   HIGH relevance (count) — clickable, filters below table
    -   Closing in next 7 days (count) — clickable
    -   Avg estimated value of HIGH tenders (TRY)

2.  **Filter bar** (sticky):
    -   Relevance level: All / HIGH / MEDIUM / LOW
    -   Procurement type: All / Mal / Hizmet / Yapım
    -   Deadline window: All / This week / Next week / Next month
    -   Institution search box (free text)
    -   Keyword chip filter (multi-select from Appendix A)

3.  **Main table** (one row per tender, sortable):

    | Col | Source field |
    |---|---|
    | Relevance badge | `relevance_level` (color: red/orange/grey) |
    | Score | `relevance_score` |
    | Title | `title` (truncated, click to expand) |
    | Institution | `institution` |
    | Type | `procurement_type` |
    | Estimated value | `estimated_value_try` (formatted) |
    | Deadline | `deadline_at` with "X days remaining" |
    | Matched | `matched_keywords` as chips |
    | Action | "EKAP'ta görüntüle" link to `source_url` |

4.  **Detail panel** (when a row is expanded):
    -   Full description
    -   CPV code + meaning
    -   Rayon-fit radar chart (technical/protective/military/waterproof/FR)
    -   `rayon_why_it_matters` paragraph
    -   Historical signals on this tender (from `tender_relevance_history`)

### 12.3 Front-end implementation

-   Add to `dashboard/static/app.v5.js` (or bump to `app.v6.js` if frontend cache strategy warrants — see Phase E memory note re: v6→v7 cache buster planned for P1 step 8). Aligning Phase F's frontend rev with Phase E's saves one cache flush cycle.
-   New module functions: `loadTenderIntelligence()`, `_renderTenderTable()`, `_renderTenderDetail()`, `_filterTenders()`.
-   New backend endpoints: `/api/tenders`, `/api/tender_stats`, `/api/tender/<id>` (detail).

### 12.4 Empty states

-   "No active tenders match your filters." (Reasonable; common during quiet weeks.)
-   "Tender ingestion has not run yet today. Last run: X hours ago."
-   "Tender ingestion is failing. See `failed_jobs` for details." (with a deep-link to the relevant `failed_jobs` rows for admin debug.)

---

## 13. Notification Layer

The existing `scrapers/telegram_reporter.py` already broadcasts daily Market Signals reports to `@tekstil_haber_bot`. Phase F extends this without writing a new bot:

### 13.1 Daily report

Telegram daily report (the existing 08:00 morning push) gets a new section:

```
🔵 Yeni İhaleler (son 24 saat, HIGH/MEDIUM)
  • İBB - İtfaiye Eri Koruyucu Kıyafet Alımı
    Skor: 92 / Son tarih: 23 Mayıs 14:00 / ~2.3M TRY
    https://ekap.kik.gov.tr/...
  • <next tender>
  
🟢 Bu hafta sona eren takip edilen ihaleler
  • <list>
```

### 13.2 Instant alerts (HIGH only)

When the relevance engine emits a HIGH-relevance signal, an immediate Telegram message is dispatched (not batched into the daily report). This is critical because tender deadlines are time-sensitive: a HIGH signal that surfaces only the next morning may have lost a day of preparation time.

Rate limit: at most 1 HIGH alert per 10 minutes (group bursts).

---

## 14. Operational Concerns

### 14.1 Cron schedule (proposed)

| Time (Istanbul) | Job |
|---|---|
| 11:00 | Existing daily cron (news scrape + analyze) — unchanged |
| 19:00 | **NEW**: tender bulletin ingestion (F1) |
| Every 30 min, 08:00–20:00 | **NEW (F2)**: EKAP V2 intra-day scraper |
| 23:00 | **NEW (F1)**: nightly status sweep — re-check `is_active` for all currently-open tenders, transition expired ones to `closed` |
| 23:30 | Existing news scraper cleanup — unchanged |

The 19:00 slot was chosen to align with the bulletin's typical publication time (~18:00 Istanbul), leaving 1h buffer.

### 14.2 GitHub Actions workflow changes

A new workflow `.github/workflows/tender_daily.yml` (mirrors existing `daily_cron.yml`):

```yaml
on:
  schedule:
    - cron: '0 16 * * *'   # 19:00 Istanbul = 16:00 UTC
  workflow_dispatch:

jobs:
  ingest_tenders:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt
      - run: python -m scrapers.tender_bulletin_scraper
        env:
          DATABASE_URL: ${{ secrets.RAYON_DATABASE_URL }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

### 14.3 failed_jobs integration

Tender pipelines use the existing `failed_jobs` table with `pipeline` values: `tender_bulletin_scraper`, `tender_normalize`, `tender_relevance_engine`, `tender_llm_analyzer`. Same retry / resolve workflow as news scrapers.

### 14.4 Backup strategy

The tender data is fully derivable from EKAP's public PDFs (which KİK archives permanently). Therefore we do not need a separate backup beyond the standard Railway PostgreSQL daily backup.

### 14.5 Cost projection

| Component | Monthly cost |
|---|---|
| LLM enrichment (~30 HIGH/MEDIUM tenders/day × $0.001) | ~$0.90 |
| Storage (~1MB/month new tender data) | negligible |
| Railway compute increment for tender cron | negligible |
| Telegram bot | $0 |
| **Total** | **< $2 / month** |

This is well below the existing platform's LLM spend (~$15/month based on Phase E P0-D.3 ~$0.15-0.20 single reanalysis × monthly cadence).

---

## 15. Rollout Roadmap (F0 → F5)

Each phase is independently shippable and useful. Stop conditions are explicit so we can hand off cleanly between sessions.

### F0 — Foundations (4 hours)

**Goal:** Database + project scaffolding in place. No data yet.

-   [ ] `docs/PHASE_F_TENDER_INTELLIGENCE_DESIGN.md` (this doc) committed
-   [ ] Migration `013_create_tenders.sql` written, reviewed, applied
-   [ ] Migration `014_create_tender_keywords_history.sql` written, reviewed, applied
-   [ ] Migration `015_seed_tender_keywords.sql` written and applied (~20 keywords from Appendix A)
-   [ ] `scrapers/tender_ingestion/__init__.py` package skeleton
-   [ ] One smoke test: `SELECT * FROM v_active_tenders LIMIT 1` returns empty without error
-   [ ] One smoke test: `SELECT COUNT(*) FROM lkp_tender_keywords` returns the seed count
-   Commit: `Phase F0: tender schema + seed keywords`

**Stop condition:** Schema applied to prod DB, seed data in place, no code yet.

### F1 — Minimum Viable Ingestion (6 hours)

**Goal:** Daily PDF bulletin → DB → rule-based scoring → Market Signals + dashboard tab. End-to-end thin slice.

-   [ ] `scrapers/tender_bulletin_scraper.py` — fetch + parse + UPSERT
-   [ ] `scrapers/tender_normalize.py` — Turkish normalization, status interpretation
-   [ ] `scrapers/tender_relevance_engine.py` — Stage 1 (rule-based) only, no LLM yet
-   [ ] Emit `market_signals` rows for HIGH/MEDIUM
-   [ ] `dashboard/server.py` — `/api/tenders`, `/api/tender_stats`, `/api/tender/<id>`
-   [ ] `dashboard/static/app.v5.js` — `loadTenderIntelligence()` + table + filters (no detail panel yet)
-   [ ] `.github/workflows/tender_daily.yml` — daily 19:00 IST cron
-   [ ] Live test: manually trigger workflow, verify ≥ 1 row in `tenders` and dashboard tab renders
-   Commit: `Phase F1: tender ingestion + rule-based relevance + dashboard tab MVP`

**Stop condition:** Tomorrow's 19:00 cron runs without manual intervention and produces visible output in the dashboard.

### F2 — Intra-day freshness + status sweep (4 hours)

**Goal:** Don't wait 24 hours to see a new tender; keep statuses fresh.

-   [ ] `scrapers/tender_ekap_v2_scraper.py` — API reverse-engineering done, every-30-min job
-   [ ] `scrapers/tender_status_sweep.py` — nightly 23:00 IST job, transitions expired tenders to `closed`
-   [ ] Cross-source dedup logic in `tender_normalize.py`
-   [ ] GitHub Actions workflow updated with both new cron slots
-   Commit: `Phase F2: intra-day tender refresh + nightly status sweep`

**Stop condition:** A tender published at 10:00 IST appears in the dashboard by 10:30 IST.

### F3 — LLM enrichment + Rayon-fit scoring (4 hours)

**Goal:** Move from keyword precision (~80% expected) to semantic precision (~95% expected). Add the Rayon-fit dimensions.

-   [ ] `scrapers/tender_llm_analyzer.py` — gpt-4o-mini integration mirroring `llm_analyzer.py`'s structure
-   [ ] LLM runs only on rule-based HIGH/MEDIUM (cost containment)
-   [ ] Update `tenders.fit_*` fields, `rayon_why_it_matters`, `affected_business_line`, `affected_material_family`
-   [ ] Dashboard detail panel adds Rayon-fit radar chart
-   [ ] Telegram daily report includes `rayon_why_it_matters` in tender lines
-   Commit: `Phase F3: LLM enrichment + Rayon-fit scoring`

**Stop condition:** Two weeks of HIGH tenders show LLM-explained reasoning paragraphs.

### F4 — Instant alerts + notifications (2 hours)

**Goal:** Don't make Mert wait until the daily 08:00 report to learn about a HIGH tender published yesterday at 16:00.

-   [ ] Telegram instant-alert dispatch on HIGH signal emission (with 10-min rate-limit window)
-   [ ] Tender-closing reminder signal (`signal_type='tender_closing'`) emitted at deadline_at − 72h
-   [ ] Daily Telegram report new section format
-   Commit: `Phase F4: instant alerts + closing reminders`

**Stop condition:** A live HIGH-relevance tender triggers a Telegram alert within 5 minutes of ingestion.

### F5 — Multi-source expansion (planned, not scheduled)

**Goal:** Beyond EKAP. Begin defence and international.

-   [ ] MSB procurement portal scraper
-   [ ] SSB tender announcements scraper
-   [ ] Optional: NATO Support and Procurement Agency feed
-   [ ] Optional: EU TED (Tenders Electronic Daily) feed
-   [ ] Common cross-source dedup
-   [ ] Source attribution shown in dashboard

**Stop condition:** Defined later; this is a "when convenient" phase.

### Total elapsed-time estimate

| Phase | Engineering hours | Calendar days (Mert pace, 2-4h/day) |
|---|---|---|
| F0 | 4 | 1 |
| F1 | 6 | 2 |
| F2 | 4 | 1-2 |
| F3 | 4 | 1-2 |
| F4 | 2 | 0.5 |
| **F0–F4 total** | **20 h** | **~6 working days** |
| F5 | TBD | TBD |

Phase F0–F4 fits inside Phase E's 5 Haziran (June 5) target window with room for Phase E P1 step 7–10 in parallel.

---

## 16. Risk Analysis & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| EKAP PDF format changes | Medium | High (parser breaks silently) | Strict parser with line-count assertion (`expected ≥ 50 tenders/day`); alert via Telegram + halt on deviation |
| EKAP rate-limits or blocks scraping | Low | Medium | Conservative rate limits (1 req / 2s), descriptive User-Agent, contact info embedded; fallback to PDF-only mode |
| Keyword list produces too much noise | Medium | Medium | Calibrate weights in first 2 weeks; add exclusion patterns liberally; LLM stage in F3 acts as backstop |
| Keyword list misses relevant tenders (false negatives) | Medium | Low (we'll learn from Mert's manual EKAP browsing) | Quarterly review of `relevance_level='REJECTED'` random sample; LLM stage may upgrade some |
| LLM cost overrun if HIGH/MEDIUM volume balloons | Low | Low | Daily cost cap (`MAX_TENDER_LLM_COST_PER_DAY=$0.50`) enforced in code; auto-skip remaining LLM calls if exceeded |
| Telegram instant-alert spam | Low | Medium (user fatigue) | 10-min rate-limit window; HIGH-only (not MEDIUM); option to mute via env var |
| Status sweep misses a state transition | Medium | Low (UI shows stale "open" badge for a few hours) | Nightly sweep + opportunistic per-record refresh on next ingestion touch |
| Dashboard performance with large tender history | Low (1 year out) | Low | Indexes + materialized view for KPI strip; archive `tender_status IN ('closed','cancelled','awarded')` older than 6mo to a separate table |
| Failed_jobs flood obscuring real failures | Low | Low | Phase E pattern: only failure logs to `failed_jobs`, not per-success; add `resolved_at` workflow |

---

## 17. Success Metrics

Phase F is successful when, **two weeks after F1 ships:**

| Metric | Target |
|---|---|
| Tenders ingested per day | ≥ 200 (EKAP daily volume; sanity check that ingestion works) |
| Relevant tenders surfaced per day (HIGH + MEDIUM) | 1–10 (proves filter is selective) |
| False-positive rate of HIGH (per Mert's manual review) | ≤ 20% |
| False-negative rate (relevant tenders missed, per Mert's manual cross-check on a sample week) | ≤ 10% |
| LLM cost (after F3) | < $2/month |
| Cron uptime | ≥ 95% (allowing for a few weekly hiccups) |
| Time from EKAP publication to Telegram alert (F4) | < 35 minutes (30-min cron + 5-min processing) |

Long-term (3 months):

-   Mert has approached at least one tender bidder proactively, based on a platform-surfaced tender.
-   Mert no longer manually checks EKAP.

---

## Appendix A: Canonical Keyword List

### A.1 Priority tier keywords (positive weights) — CANONICAL CORE

**Status:** Frozen by Mert (v1.1). This is the *mandatory baseline* — every tender must be matched against this list. A.2 supplements but never replaces it.

| Keyword (original) | Normalized | Class | Weight |
|---|---|---|---|
| tekstil | tekstil | medium_priority | 25 |
| kumaş | kumas | medium_priority | 25 |
| kumas | kumas | medium_priority | 25 |
| konfeksiyon | konfeksiyon | medium_priority | 25 |
| personel kıyafeti | personel kiyafeti | medium_priority | 15 |
| personel kiyafeti | personel kiyafeti | medium_priority | 15 |
| iş elbisesi | is elbisesi | medium_priority | 15 |
| is elbisesi | is elbisesi | medium_priority | 15 |
| iş kıyafeti | is kiyafeti | medium_priority | 15 |
| is kiyafeti | is kiyafeti | medium_priority | 15 |
| askeri tekstil | askeri tekstil | high_priority | 40 |
| üniforma | uniforma | medium_priority | 25 |
| uniforma | uniforma | medium_priority | 25 |
| polis kumaş | polis kumas | high_priority | 40 |
| polis kumas | polis kumas | high_priority | 40 |
| asker kumaş | asker kumas | high_priority | 40 |
| asker kumas | asker kumas | high_priority | 40 |
| güvenlik kumaş | guvenlik kumas | high_priority | 40 |
| guvenlik kumas | guvenlik kumas | high_priority | 40 |

### A.2 Supplementary recall layer — Approved (v1.1)

**Status:** Approved by Mert (v1.1) for extending recall. These keywords are *additive* — they catch tenders that the core list might miss, particularly in defence/protective/technical-fabric language. They never replace A.1; they only widen the funnel.

**Note:** A tender matching ONLY A.2 keywords (without any A.1 hit) is still scored normally. Weights are calibrated such that a single A.2 high_priority hit alone reaches MEDIUM threshold (≥ 20), and two combined hits reach HIGH (≥ 50).

| Keyword (original) | Normalized | Class | Weight |
|---|---|---|---|
| FR kumaş | fr kumas | high_priority | 35 |
| FR kumas | fr kumas | high_priority | 35 |
| flame retardant | flame retardant | high_priority | 35 |
| yanmaz kumaş | yanmaz kumas | high_priority | 35 |
| yanmaz kumas | yanmaz kumas | high_priority | 35 |
| taktik kıyafet | taktik kiyafet | high_priority | 30 |
| taktik kiyafet | taktik kiyafet | high_priority | 30 |
| teknik tekstil | teknik tekstil | high_priority | 30 |
| koruyucu kıyafet | koruyucu kiyafet | medium_priority | 20 |
| koruyucu kiyafet | koruyucu kiyafet | medium_priority | 20 |
| softshell | softshell | medium_priority | 20 |
| kamuflaj | kamuflaj | medium_priority | 25 |
| su geçirmez kumaş | su gecirmez kumas | medium_priority | 20 |
| su gecirmez kumas | su gecirmez kumas | medium_priority | 20 |
| outdoor kıyafet | outdoor kiyafet | medium_priority | 15 |
| outdoor kiyafet | outdoor kiyafet | medium_priority | 15 |

### A.3 Exclusion patterns (negative weights, instant reject)

| Pattern | Reasoning |
|---|---|
| tekstil fabrikası | Construction tenders ("Tekstil Fabrikası İnşaatı") |
| tekstil kortlu | Conveyor belt context ("Tekstil Kortlu Konveyör") |
| tekstil atık | Waste disposal context |
| tekstil temizleme | Cleaning service |
| mefruşat | Furnishings (curtains/upholstery — Rayon does not target this segment) |
| perde | Curtains |
| çarşaf | Bed linen (Rayon does not target this) |
| havlu | Towels (Rayon does not target this) |
| yapım | If `procurement_type='Yapım'`, instant reject (construction projects never relevant) |

This list is **starting point only**. The first two weeks of operation generate empirical feedback that will refine it.

**Note on soft-reject behaviour (v1.1):** An exclusion-pattern match does *not* delete the tender row. The tender is persisted in `tenders` with `relevance_level='REJECTED'` and `rejection_reason='Exclusion match: <pattern>'`. A row is also written to `tender_relevance_history` recording the rejection. This allows:

-   Forensic review when the rule set changes (we can replay over historical rejections).
-   False-negative analysis — Mert can audit the rejected pile to find tenders that should not have been rejected.
-   Future re-scoring with LLM in F3 — the LLM may upgrade a rejection if the rule was too aggressive.

In short: nothing is ever deleted. Everything is flagged and explainable.

---

## Appendix B: CPV Codes Reference

CPV (Common Procurement Vocabulary) codes used by EKAP. The codes most relevant to Rayon's product range:

| CPV | Description (TR) | Description (EN) | Rayon relevance |
|---|---|---|---|
| 18100000 | Mesleki giyim, özel iş kıyafeti ve aksesuarları | Occupational clothing, special workwear and accessories | HIGH |
| 18110000 | Mesleki giyim | Occupational clothing | HIGH |
| 18114000 | Tulumlar | Coveralls | HIGH |
| 18130000 | Özel iş kıyafetleri | Special workwear | HIGH |
| 18140000 | İş kıyafetlerine ait aksesuarlar | Workwear accessories | LOW |
| 18221000 | Su geçirmez giysiler | Waterproof clothing | HIGH |
| 18222000 | Kurumsal giysiler | Corporate clothing | MEDIUM |
| 18223000 | Ceketler ve blazerler | Jackets and blazers | MEDIUM |
| 18230000 | Çeşitli üst giysiler | Miscellaneous outerwear | MEDIUM |
| 18234000 | Pantolonlar | Trousers | MEDIUM |
| 18235000 | Kazak/sweater | Sweaters | MEDIUM |
| 18310000 | İç çamaşırı | Underwear | LOW |
| 18400000 | Özel kullanımlık giysi ve aksesuarlar | Special-purpose clothing | HIGH |
| 18410000 | Özel kullanımlık giysi | Special-purpose clothing | HIGH |
| 18411000 | Bebek kıyafetleri | Infant clothing | REJECT |
| 18412000 | Spor kıyafetleri | Sportswear | MEDIUM |
| 18413000 | Koruyucu kıyafetler | Protective clothing | HIGH |
| 18420000 | Giysi aksesuarları | Clothing accessories | LOW |
| 18424000 | Eldivenler | Gloves | LOW |
| 19200000 | Tekstil kumaşları ve ilgili ürünler | Textile fabrics and related products | HIGH |
| 19210000 | Dokuma kumaşlar | Woven fabrics | HIGH |
| 19220000 | Yünlü kumaşlar | Woollen fabrics | HIGH |
| 19230000 | Keten kumaşlar | Linen fabrics | LOW |
| 19240000 | Özel kumaşlar | Speciality fabrics | HIGH |
| 19243000 | Döşemelik kumaşlar | Upholstery fabric | LOW |
| 19250000 | Örme veya tığ işi kumaşlar | Knitted or crocheted fabrics | HIGH |
| 35100000 | Acil ve güvenlik teçhizatı | Emergency and security equipment | MEDIUM (overlap with protective) |
| 35113000 | Güvenlik teçhizatı | Security equipment | MEDIUM |
| 35113400 | Koruyucu ve emniyet kıyafetleri | Protective and safety clothing | HIGH |
| 35811200 | Polis üniformaları | Police uniforms | HIGH |
| 35811300 | Askeri üniformalar | Military uniforms | HIGH |
| 35812000 | Muharebe üniformaları | Combat uniforms | HIGH |
| 35812100 | Kamuflaj üniformaları | Camouflage uniforms | HIGH |

We use CPV codes as a **secondary signal**, not primary. A tender with HIGH-relevance CPV but no keyword match still goes through normal scoring (the keyword stage dominates).

In F1, CPV is stored but not weighted in the relevance score. In F3, the LLM is told the CPV code and may use it as additional context.

---

## Appendix C: Known False Positive Patterns

Collected from the design discussion + ChatGPT's analysis. These patterns must be downgraded by the rule engine (Section 9) or, when the rule engine misses them, by the LLM (F3).

| Title pattern | Why it's a false positive |
|---|---|
| "Tekstil Fabrikası Yol Yapımı" | Road construction at a textile factory site — civil engineering |
| "Tekstil Kortlu Konveyör Bant Alımı" | Conveyor belt with textile cord reinforcement — industrial equipment |
| "Tekstil Atık Bertarafı" | Waste disposal — services, not textile manufacturing |
| "Tekstil Boya Atık Su Arıtma" | Wastewater treatment for textile dyeing — environmental engineering |
| "Tekstil Makinesi Bakım Hizmeti" | Machine maintenance — services |
| "Tekstil Fabrikası Elektrik Tesisatı" | Electrical work at textile plant — construction |
| "Çarşaf, Yastık Kılıfı Alımı" (hospital linen) | Bedding — outside Rayon's segment |
| "Perde ve Tül Alımı" | Curtains — outside Rayon's segment |
| "Mefruşat Malzemeleri" | Furnishings — outside Rayon's segment |
| "Tekstil Yıkama Hizmeti" | Laundry service for institutional textiles |
| "Tekstil Atölyesi Donanımı" | Workshop equipment, not fabric |

Pattern: if a tender's `procurement_type = 'Yapım'` (construction) or `'Hizmet'` (service), the bar for relevance must be considerably higher. F1's rule engine treats these as instant `REJECT` unless an HIGH-priority keyword overrides.

---

**End of design document.**

*This is a living document. Updates as Phase F evolves will be captured as v1.1, v1.2, etc., with a changelog at the top. All other Phase F artefacts (migrations, scrapers, dashboard code) refer back to this doc as the source of truth.*
