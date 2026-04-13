"""
scrapers/llm_analyzer.py
Reads unanalyzed news_items (relevance_score IS NULL) and runs each through
GPT-4o-mini to produce relevance scores, signal classification, and a Turkish
summary.  High-relevance articles (score > 0.4) are promoted to market_signals.

Usage:
    python scrapers/llm_analyzer.py
    python scrapers/llm_analyzer.py --limit 10 --dry-run

Returns exit code 0 always; summary is printed to stdout.
"""

import argparse
import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PIPELINE = "llm_analyzer"
LLM_MODEL = "gpt-4o-mini"
RELEVANCE_THRESHOLD = 0.4
DEFAULT_BATCH_LIMIT = 20

# GPT-4o-mini pricing (USD per token, as of 2024-11)
COST_PER_INPUT_TOKEN  = 0.150 / 1_000_000   # $0.150 per 1M tokens
COST_PER_OUTPUT_TOKEN = 0.600 / 1_000_000   # $0.600 per 1M tokens

VALID_SIGNAL_TYPES = {"price_move", "capacity_change", "new_market", "trend", "regulation", "other"}
VALID_SEVERITIES   = {"info", "warning", "alert"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a market intelligence analyst specialized in the global textile and fabric industry.
You serve a Turkish B2B fabric manufacturer (Rayon Tekstil) that produces knit and woven fabrics
and exports to Eastern Europe, Middle East, Caucasus, Russia, and Ukraine.
Their customers are garment manufacturers, tender companies, and wholesalers.

You will be given the title and body of a news article. Respond ONLY with a JSON object
containing these exact keys:

{
  "relevance_score": <float 0.0–1.0, how relevant this article is to the company>,
  "signal_type": <one of: "price_move", "capacity_change", "new_market", "trend", "regulation", "other">,
  "severity": <one of: "info", "warning", "alert">,
  "summary_tr": <one sentence in Turkish summarising the article's key market intelligence>,
  "company_mentioned": <the exact name of a specific competitor or supplier company mentioned in the article, or null if none>
}

Relevance scoring guide:
  1.0 = directly affects fabric/textile pricing, supply, or export markets Rayon serves
  0.7 = affects the broader textile/garment industry in relevant geographies
  0.4 = general textile industry news with indirect relevance
  0.0 = completely unrelated (fashion, retail consumer news, unrelated industries)

Severity guide:
  alert   = immediate action or close monitoring required (major price shock, supply disruption, sanctions)
  warning = developing situation worth tracking (capacity shifts, new entrants, regulatory proposals)
  info    = background context or trend to be aware of

Return only the JSON object — no markdown, no explanation.\
"""


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(url, connect_timeout=10)


def fetch_unanalyzed(cur, limit: int) -> list[dict]:
    cur.execute(
        """
        SELECT id, url, title, body_raw
        FROM   news_items
        WHERE  relevance_score IS NULL
        ORDER  BY scraped_at ASC
        LIMIT  %s
        """,
        (limit,),
    )
    return [
        {"id": str(row[0]), "url": row[1], "title": row[2] or "", "body_raw": row[3] or ""}
        for row in cur.fetchall()
    ]


def fetch_companies(cur) -> list[dict]:
    """Return all company names + ids for fuzzy matching."""
    cur.execute("SELECT id, name FROM companies")
    return [{"id": str(row[0]), "name": row[1]} for row in cur.fetchall()]


def match_company(company_name: str | None, companies: list[dict]) -> str | None:
    """
    Case-insensitive substring match: return company_id if the LLM-returned
    name appears in any tracked company name or vice-versa.
    Returns None if no match or company_name is None.
    """
    if not company_name:
        return None
    needle = company_name.strip().lower()
    for c in companies:
        haystack = c["name"].lower()
        if needle in haystack or haystack in needle:
            return c["id"]
    return None


def update_news_item(cur, item_id: str, analysis: dict, company_id: str | None,
                     tokens_in: int, tokens_out: int, cost: float):
    cur.execute(
        """
        UPDATE news_items
        SET    relevance_score = %s,
               body_summary    = %s,
               company_id      = %s,
               llm_model       = %s,
               llm_tokens_in   = %s,
               llm_tokens_out  = %s,
               llm_cost_usd    = %s
        WHERE  id = %s
        """,
        (
            analysis["relevance_score"],
            analysis["summary_tr"],
            company_id,
            LLM_MODEL,
            tokens_in,
            tokens_out,
            cost,
            item_id,
        ),
    )


def insert_market_signal(cur, item: dict, analysis: dict, company_id: str | None,
                         tokens_in: int, tokens_out: int, cost: float):
    cur.execute(
        """
        INSERT INTO market_signals
            (signal_type, severity, title, body,
             source_table, source_id, company_id,
             llm_model, llm_tokens_in, llm_tokens_out, llm_cost_usd)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            analysis["signal_type"],
            analysis["severity"],
            item["title"] or analysis["summary_tr"],
            analysis["summary_tr"],
            "news_items",
            item["id"],
            company_id,
            LLM_MODEL,
            tokens_in,
            tokens_out,
            cost,
        ),
    )


def record_failure(conn, item_id: str | None, url: str | None,
                   error_message: str, error_detail: str, payload: dict):
    """Write one row to failed_jobs. Never raises."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO failed_jobs
                    (pipeline, job_type, url, error_message, error_detail, payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    PIPELINE,
                    "llm_analyze",
                    url,
                    error_message[:500],
                    error_detail[:2000],
                    json.dumps(payload),
                ),
            )
        conn.commit()
    except Exception as e:
        log.warning("Could not write to failed_jobs: %s", e)


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def build_user_message(item: dict) -> str:
    title = item["title"].strip() if item["title"] else "(no title)"
    body  = item["body_raw"].strip() if item["body_raw"] else "(no body)"
    # Truncate body to ~4 000 chars to stay well within context limits
    if len(body) > 4000:
        body = body[:4000] + "…"
    return f"TITLE: {title}\n\nBODY:\n{body}"


def call_openai(client: OpenAI, user_message: str) -> tuple[dict, int, int, float]:
    """
    Send one article to GPT-4o-mini and return (analysis_dict, tokens_in, tokens_out, cost_usd).
    Raises on API error or JSON parse failure.
    """
    response = client.chat.completions.create(
        model=LLM_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.1,
        max_tokens=256,
    )

    tokens_in  = response.usage.prompt_tokens
    tokens_out = response.usage.completion_tokens
    cost       = tokens_in * COST_PER_INPUT_TOKEN + tokens_out * COST_PER_OUTPUT_TOKEN

    raw = response.choices[0].message.content
    analysis = json.loads(raw)

    # Validate and sanitize fields
    score = float(analysis.get("relevance_score", 0.0))
    score = max(0.0, min(1.0, score))
    analysis["relevance_score"] = round(score, 3)

    signal_type = analysis.get("signal_type", "other")
    if signal_type not in VALID_SIGNAL_TYPES:
        signal_type = "other"
    analysis["signal_type"] = signal_type

    severity = analysis.get("severity", "info")
    if severity not in VALID_SEVERITIES:
        severity = "info"
    analysis["severity"] = severity

    analysis["summary_tr"] = (analysis.get("summary_tr") or "").strip() or None
    analysis["company_mentioned"] = analysis.get("company_mentioned") or None

    return analysis, tokens_in, tokens_out, cost


# ---------------------------------------------------------------------------
# Main analysis loop
# ---------------------------------------------------------------------------

def analyze(limit: int = DEFAULT_BATCH_LIMIT, dry_run: bool = False) -> dict:
    """
    Fetch up to `limit` unanalyzed news_items, run LLM analysis, persist results.
    Returns summary counts.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    client = OpenAI(api_key=api_key)

    try:
        conn = get_connection()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return {"processed": 0, "signaled": 0, "failed": 0, "total_cost_usd": 0.0, "error": str(e)}

    processed = signaled = failed = 0
    total_cost = 0.0

    with conn.cursor() as cur:
        items     = fetch_unanalyzed(cur, limit)
        companies = fetch_companies(cur)

    log.info("Fetched %d unanalyzed articles; %d companies in index", len(items), len(companies))

    for item in items:
        log.info("Analyzing [%s] %.80s", item["id"], item["title"])

        user_msg = build_user_message(item)

        try:
            analysis, tokens_in, tokens_out, cost = call_openai(client, user_msg)
        except Exception as e:
            failed += 1
            log.warning("  LLM error: %s", e)
            record_failure(
                conn,
                item_id=item["id"],
                url=item["url"],
                error_message=str(e),
                error_detail=traceback.format_exc(),
                payload={"news_item_id": item["id"], "url": item["url"]},
            )
            continue

        total_cost += cost
        company_id = match_company(analysis["company_mentioned"], companies)

        log.info(
            "  score=%.3f  type=%-17s severity=%-7s  tokens=%d+%d  cost=$%.6f%s",
            analysis["relevance_score"],
            analysis["signal_type"],
            analysis["severity"],
            tokens_in, tokens_out,
            cost,
            f"  company_id={company_id}" if company_id else "",
        )

        if dry_run:
            log.info("  [DRY-RUN] skipping DB writes")
            processed += 1
            if analysis["relevance_score"] > RELEVANCE_THRESHOLD:
                signaled += 1
            continue

        try:
            with conn:
                with conn.cursor() as cur:
                    update_news_item(cur, item["id"], analysis, company_id,
                                     tokens_in, tokens_out, cost)

                    if analysis["relevance_score"] > RELEVANCE_THRESHOLD:
                        insert_market_signal(cur, item, analysis, company_id,
                                             tokens_in, tokens_out, cost)
                        signaled += 1
                        log.info("  → market_signal written")

            processed += 1

        except psycopg2.Error as e:
            failed += 1
            log.warning("  DB write error: %s", e)
            record_failure(
                conn,
                item_id=item["id"],
                url=item["url"],
                error_message=str(e),
                error_detail=traceback.format_exc(),
                payload={"news_item_id": item["id"], "url": item["url"], "analysis": analysis},
            )
        except Exception as e:
            failed += 1
            log.warning("  Unexpected error: %s", e)
            record_failure(
                conn,
                item_id=item["id"],
                url=item["url"],
                error_message=str(e),
                error_detail=traceback.format_exc(),
                payload={"news_item_id": item["id"], "url": item["url"]},
            )

    conn.close()
    return {
        "processed":      processed,
        "signaled":       signaled,
        "failed":         failed,
        "total_cost_usd": round(total_cost, 6),
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run LLM analysis on unanalyzed news_items")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_BATCH_LIMIT,
        metavar="N",
        help=f"Max articles to process per run (default: {DEFAULT_BATCH_LIMIT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Call OpenAI but skip all DB writes",
    )
    args = parser.parse_args()

    log.info("Starting %s (model=%s, limit=%d%s)", PIPELINE, LLM_MODEL, args.limit,
             ", DRY-RUN" if args.dry_run else "")

    result = analyze(limit=args.limit, dry_run=args.dry_run)

    print(
        f"\nSummary — processed: {result['processed']}  "
        f"signaled: {result['signaled']}  "
        f"failed: {result['failed']}  "
        f"total_cost: ${result['total_cost_usd']:.6f}"
    )

    if result.get("error"):
        print(f"Fatal error: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
