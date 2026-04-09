# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Rayon Intelligence Platform — market intelligence and competitor analysis for Rayon Tekstil Sanayi ve Dış Tic. Ltd. Şti., a Turkish B2B fabric manufacturer with two business units:
- **Knit fabrics**: fully integrated (yarn → finished fabric)
- **Woven fabrics**: import greige from Far East + dyeing/coating/lamination finishing

Export markets: Eastern Europe, Middle East, Caucasus, Russia, Ukraine.
Customers: garment manufacturers, tender companies, wholesalers.

## System Architecture

**Phase 1 — Market Intelligence** (active)
**Phase 2 — Price Intelligence** (planned)

**Stack:**
- Orchestration: n8n (hosted on Railway)
- Database: PostgreSQL (hosted on Railway)
- Scraping: Python + BeautifulSoup
- AI: OpenAI API (token cost tracked per call)
- Storage: Cloudflare R2
- Dashboard: Streamlit
- Output: Telegram bot + email reports

## Database Design Principles

- Deduplication enforced at PostgreSQL level only via `url_hash UNIQUE` constraint — not in n8n
- Each source has its own independent pipeline
- Every pipeline has error handling; failed records go to `failed_jobs` table, never silently dropped
- LLM token costs tracked per call in the database
- Phase 1 feeds entirely from external sources — no internal company data

## Core Schema Tables

- `companies` — tracked competitor/market entities
- `news_items` — scraped news articles and press items
- `trade_flows` — import/export trade data
- `market_signals` — processed intelligence signals
- `failed_jobs` — dead letter queue for all pipeline errors

## Repository Structure

```
schema/          # PostgreSQL DDL scripts
scrapers/        # Python scraper modules (one per source)
n8n/             # n8n workflow JSON exports
dashboard/       # Streamlit app
```
