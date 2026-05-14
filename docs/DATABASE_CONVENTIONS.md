# Database Connection Conventions

> **CANONICAL REFERENCE** — every new script, scraper, or contributor must follow this.
> Last updated: 2026-05-14 (Plan A migration)

## Three databases, three env vars

| Env name | DB purpose | Notes |
|---|---|---|
| `RAYON_DATABASE_URL` | **Rayon Intelligence ana DB** — news_items, market_signals, price_signals, competitors, yarn intelligence, internal data (orders, lescon, yarn_costs), trade_flows, fair_exhibitors | Default for ALL scrapers/builders unless explicitly tender |
| `RAYON_INTEL_DATABASE_URL` | **Tender DB** — ihale (procurement tender) data | Separate database. Integrated to Market Signals via dedicated ETL (`tender_to_signals.py` — planned) that reads from `RAYON_INTEL_DATABASE_URL` and writes to `RAYON_DATABASE_URL.market_signals` |
| ~~`DATABASE_URL`~~ | **DEPRECATED — DO NOT USE** | Legacy convention removed in Plan A migration. Never re-introduce. |

## Hard rules

1. **Never confuse the three.** `RAYON_DATABASE_URL` ≠ `RAYON_INTEL_DATABASE_URL`. Different purposes, different data.
2. **Never map the same secret to two env names.** If two env vars are needed, they must come from different secrets.
3. **Never fallback between them.** A script that needs ana DB and falls back to tender DB on failure is a data corruption bug.
4. **Never re-introduce `DATABASE_URL`.** Reserved as a "do not use" name to prevent legacy convention drift.

## Local `.env` template

```dotenv
OPENAI_API_KEY=sk-...
RAYON_DATABASE_URL=postgresql://...        # Rayon Intelligence main DB
RAYON_INTEL_DATABASE_URL=postgresql://...  # Tender DB (separate)
```

## GitHub Actions workflow env

```yaml
env:
  RAYON_DATABASE_URL: ${{ secrets.RAYON_DATABASE_URL }}
  # For tender-touching steps, add:
  # RAYON_INTEL_DATABASE_URL: ${{ secrets.RAYON_INTEL_DATABASE_URL }}
```

## Script template (new scraper / builder)

```python
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_conn():
    url = os.environ.get("RAYON_DATABASE_URL")
    if not url:
        raise RuntimeError("RAYON_DATABASE_URL environment variable is not set")
    return psycopg2.connect(url)
```

For tender-related scripts: substitute `RAYON_INTEL_DATABASE_URL` and update the error message.

## New script — checklist

- [ ] Touches ana DB or tender DB? Pick ONE env var.
- [ ] Needs both DBs (ETL/cross-DB)? Load BOTH env vars explicitly — never fallback.
- [ ] Added to `.github/workflows/daily_scraper.yml` (or appropriate workflow)?
- [ ] Workflow env block exposes the needed env var? Add it if missing (one line per env name, from matching secret).
- [ ] Locally tested with `python scrapers/your_script.py --pages 1` (or equivalent)?