# P1 Step 1: Rename Inventory

_Generated end of 11 May 2026 session. Per-line cheat sheet for tomorrow's scrapers update._

## Rename Rules

1. **SQL table refs:** `companies` -> `entities`
2. **Column refs / Python variables:** `company_id` -> `entity_id`
3. **Function rename (llm_analyzer.py only):** `match_companies(...)` -> `match_entities(...)`

## Safety Note

Migration 010 creates a backwards-compat `companies` VIEW so `SELECT FROM companies` still works after rename. But for INSERT/UPDATE you MUST use `entities` (views are not auto-updatable for complex DML). Recommendation: rename everywhere for code cleanliness.

## Suggested Order (smallest to largest)

After each file, run syntax check:
```powershell
python -c "import ast; ast.parse(open(r'<file>', encoding='utf-8').read())"
```

## `dashboard/server.py` (2 hits)

| Line | Type | Code |
|---|---|---|
| L221 | SQL-table | `"SELECT COUNT(*)::int AS n FROM companies WHERE category = 'competitor'",` |
| L338 | SQL-table | `LEFT JOIN companies c ON ms.company_id = c.id` |

## `scrapers/telegram_reporter.py` (1 hits)

| Line | Type | Code |
|---|---|---|
| L86 | SQL-table | `LEFT  JOIN companies c ON c.id = ms.company_id` |

## `scrapers/texhibition_scraper.py` (11 hits)

| Line | Type | Code |
|---|---|---|
| L4 | py-variable | `in the fair_exhibitors table.  Then cross-references against the companies` |
| L168 | py-variable | `Return (company_id, company_name) if any row in companies matches` |
| L176 | SQL-table | `FROM   companies` |
| L189 | py-variable | `conn, company_id: str, company_name: str,` |
| L203 | py-variable | `AND  company_id  = %s` |
| L207 | py-variable | `(company_id, tags),` |
| L217 | py-variable | `(signal_type, severity, title, body, company_id, tags)` |
| L220 | py-variable | `(title, body, company_id, tags),` |
| L457 | comment | `# Cross-reference with companies table` |
| L460 | py-variable | `company_id, company_name = match` |
| L462 | py-variable | `conn, company_id, company_name,` |

## `scrapers/llm_analyzer.py` (20 hits)

| Line | Type | Code |
|---|---|---|
| L12 | py-variable | `The system prompt is built dynamically at startup from the companies table so the` |
| L103 | py-variable | `Called once at startup after fetching companies from DB.` |
| L117 | py-variable | `Customers: garment manufacturers, tender companies, wholesalers.` |
| L144 | py-variable | `Flag ANY article that explicitly names one or more of these companies:` |
| L318 | SQL-table | `cur.execute("SELECT id, name, category FROM companies ORDER BY name")` |
| L322 | def-signature | `def match_companies(names_from_llm: list[str], companies: list[dict]) -> list[dict]:` |
| L333 | py-variable | `for c in companies:` |
| L342 | def-signature | `def update_news_item(cur, item_id: str, analysis: dict, company_id: str \| None,` |
| L349 | py-variable | `company_id      = %s,` |
| L359 | py-variable | `company_id,` |
| L369 | def-signature | `def insert_market_signal(cur, item: dict, analysis: dict, company_id: str \| None,` |
| L388 | py-variable | `source_table, source_id, source_url, company_id,` |
| L404 | py-variable | `company_id,` |
| L436 | py-variable | `source_table, source_id, source_url, company_id,` |
| L683 | py-variable | `companies = fetch_companies(cur)` |
| L685 | py-variable | `competitor_names = [c["name"] for c in companies]` |
| L689 | py-variable | `"Fetched %d unanalyzed articles; %d companies in prompt (%d competitors)",` |
| L691 | py-variable | `len(companies),` |
| L692 | py-variable | `sum(1 for c in companies if c.get("category") == "competitor"),` |
| L716 | py-variable | `matched = match_companies(analysis["competitors_mentioned"], companies)` |

## `scrapers/competitor_monitor.py` (26 hits)

| Line | Type | Code |
|---|---|---|
| L146 | SQL-table | `FROM companies` |
| L154 | def-signature | `def get_latest_snapshot(cur, company_id: str) -> dict \| None:` |
| L159 | SQL-column | `WHERE company_id = %s` |
| L163 | py-variable | `(company_id,),` |
| L168 | def-signature | `def insert_snapshot(cur, company_id: str, url: str, content_hash: str, summary: str):` |
| L172 | py-variable | `(company_id, url, content_hash, content_summary, checked_at)` |
| L175 | py-variable | `(company_id, url, content_hash, summary, datetime.now(timezone.utc)),` |
| L179 | def-signature | `def insert_market_signal(cur, company_id: str, company_name: str, url: str, summary: str):` |
| L183 | py-variable | `(signal_type, severity, title, body, source_table, company_id, detected_at, tags)` |
| L196 | py-variable | `company_id,` |
| L232 | py-variable | `Check all companies with a website. Returns a summary dict.` |
| L243 | py-variable | `companies = get_companies(cur)` |
| L245 | py-variable | `log.info("Checking %d companies", len(companies))` |
| L247 | py-variable | `for idx, company in enumerate(companies, start=1):` |
| L248 | py-variable | `company_id = str(company["id"])` |
| L252 | py-variable | `log.info("[%d/%d] %s — %s", idx, len(companies), name, url)` |
| L262 | py-variable | `error_detail=f"company_id={company_id}",` |
| L263 | py-variable | `payload={"company_id": company_id, "name": name, "url": url},` |
| L280 | py-variable | `payload={"company_id": company_id, "name": name, "url": url},` |
| L288 | py-variable | `previous = get_latest_snapshot(cur, company_id)` |
| L292 | py-variable | `insert_snapshot(cur, company_id, url, content_hash, summary)` |
| L311 | py-variable | `insert_snapshot(cur, company_id, url, content_hash, summary)` |
| L312 | py-variable | `insert_market_signal(cur, company_id, name, url, summary)` |
| L326 | py-variable | `payload={"company_id": company_id, "name": name, "url": url},` |
| L336 | py-variable | `payload={"company_id": company_id, "name": name, "url": url},` |
| L339 | py-variable | `if idx < len(companies):` |

---

**Total: 60 hits across 5 files**