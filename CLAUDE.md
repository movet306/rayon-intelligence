# Project Conventions — Read First

> Read this at the start of every session before writing code or running commands.
> Updated whenever a recurring confusion is discovered.

## Repository: Rayon Intelligence Platform

Family textile manufacturing company analytics + market intelligence platform: scrapers, FastAPI dashboard, PostgreSQL on Railway, GitHub Actions cron, OpenAI LLM analysis.

## Three databases — see `docs/DATABASE_CONVENTIONS.md` for full reference

| Env var | DB | Use |
|---|---|---|
| `RAYON_DATABASE_URL` | **Ana DB** | Default for any new scraper/builder |
| `RAYON_INTEL_DATABASE_URL` | **Tender DB** | Tender (ihale) data only |
| `DATABASE_URL` | ⛔ **DEPRECATED** | Never use, never re-introduce |

### Hard rules

- Never confuse the three.
- Never map the same GitHub Secret to two env names.
- Never fallback between them.
- New scrapers default to `RAYON_DATABASE_URL`. Workflow env block must expose `RAYON_DATABASE_URL: ${{ secrets.RAYON_DATABASE_URL }}`.

## File layout

- `scrapers/` — Data ingestion scripts (one per source)
- `dashboard/` — FastAPI server + static frontend
- `schema/` — Postgres DDL migrations
- `scripts/migrations/` — Python data migrations
- `docs/` — Architecture, roadmaps, conventions (read these BEFORE designing a new feature)
- `.github/workflows/daily_scraper.yml` — Daily cron orchestration

## Environment

- Python 3.12.7 (Anaconda), conda env `rayon-dashboard`
- Dashboard: `uvicorn dashboard.server:app --port 8000`
- Local DB connection: load via `python-dotenv` from `.env`
- Static cache buster: `v5` for js/css, `v6` general invalidation

## When in doubt

- Check `docs/` for an existing convention before guessing.
- Read the pattern from a similar scraper before writing a new one.
- If a convention question recurs, write it down in `docs/` or here.