"""
scrapers/llm_analyzer.py
Reads unanalyzed news_items (relevance_score IS NULL) and runs each through
GPT-4o-mini to produce relevance scores, signal classification, and a Turkish
summary.  High-relevance articles (score > 0.4) are promoted to market_signals.

Specific intelligence extracted:
  - competitor_mention  : any article naming a tracked competitor company
  - price_signal        : articles with specific price data (USD/kg or direction)
  - standard types      : price_move, capacity_change, new_market, trend, regulation, other

The system prompt is built dynamically at startup from the companies table so the
LLM always works with the current competitor list.

Usage:
    python scrapers/llm_analyzer.py
    python scrapers/llm_analyzer.py --limit 10 --dry-run
    python scrapers/llm_analyzer.py --limit 20 --print-signals

Returns exit code 0 always; summary is printed to stdout.
"""

import argparse
import json
import logging
import os
import sys
import textwrap
import traceback
from datetime import datetime, timezone

import requests as req

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# OpenAI called via direct HTTP requests (no SDK needed)

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PIPELINE = "llm_analyzer"
LLM_MODEL = "gpt-4o-mini"
RELEVANCE_THRESHOLD = 0.20
# Competitor mentions are emitted as signals even at lower relevance
COMPETITOR_MENTION_MIN_RELEVANCE = 0.15
DEFAULT_BATCH_LIMIT = 20

# GPT-4o-mini pricing (USD per token, as of 2024-11)
COST_PER_INPUT_TOKEN  = 0.150 / 1_000_000   # $0.150 per 1M tokens
COST_PER_OUTPUT_TOKEN = 0.600 / 1_000_000   # $0.600 per 1M tokens

VALID_SIGNAL_TYPES = {
    "price_move", "capacity_change", "new_market", "trend",
    "regulation", "competitor_mention", "price_signal", "other",
}
VALID_SEVERITIES      = {"info", "warning", "alert"}
VALID_TIME_HORIZONS   = {"short", "mid", "long"}
VALID_ACTION_TAGS     = {"MONITOR", "RISK", "OPPORTUNITY"}
VALID_SIGNAL_CATS     = {"COST_IMPACT", "DEMAND_SHIFT", "SUPPLY_RISK", "COMPETITOR_MOVE", "REGULATORY"}
VALID_RAYON_REL       = {"direct", "indirect", "none"}
VALID_AFFECTED        = {"woven", "knit", "technical", "laminated"}

# Generic Turkish phrases that indicate a vague/low-quality summary
GENERIC_TR_PHRASES = [
    "piyasası artıyor", "piyasası düşüyor", "sektör büyüyor",
    "fiyatlar artıyor", "fiyatlar düşüyor", "piyasa hareketleniyor",
    "sektörde gelişmeler", "önemli gelişmeler",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dynamic system prompt
# ---------------------------------------------------------------------------

def build_system_prompt(competitor_names: list[str]) -> str:
    """
    Build the v2 LLM system prompt injecting the current competitor list.
    Enforces material-form-level reasoning, structured taxonomy, and
    Rayon-specific relevance scoring.
    Called once at startup after fetching companies from DB.
    """
    names_block = "\n".join(f"  • {n}" for n in sorted(competitor_names))

    return textwrap.dedent(f"""\
        You are a market intelligence analyst for Rayon Tekstil Sanayi, a Turkish B2B technical fabric manufacturer.

        ══ A. RAYON BUSINESS CONTEXT ══
        Products:
          • Woven technical fabrics (military, workwear, outdoor, FR flame-retardant)
          • Knitted performance fabrics (sportswear, activewear)
          • Laminated/coated technical fabrics
        Yarn inputs: polyester filament (FDY/POY/DTY), nylon FDY, PSF staple, PP, FR-modified fibres.
        Export markets: Eastern Europe, Caucasus, Russia, Ukraine, Middle East.
        Customers: garment manufacturers, tender companies, wholesalers.

        ══ B. MATERIAL HIERARCHY (reason at Level 2 minimum — material FORM, never just fiber family) ══

        Polyester family:
          PSF  (polyester staple fiber)   → knit and woven fabrics          [relevance: HIGH]
          FDY  (fully drawn yarn)         → woven fabrics, core cost driver  [relevance: CRITICAL]
          POY  (partially oriented yarn)  → texturizing input for DTY        [relevance: CRITICAL]
          DTY  (draw textured yarn)       → knit fabrics                     [relevance: CRITICAL]
          PTA  (purified terephthalic acid) → upstream leading indicator     [relevance: MEDIUM]

        Polyamide/Nylon family:
          Nylon FDY  → military and technical fabrics                        [relevance: HIGH]
          PA6 chip   → upstream nylon input                                  [relevance: MEDIUM]
          PA66 chip  → upstream high-performance nylon                       [relevance: LOW]

        Cotton family:
          Cotton lint → raw input for yarn                                   [relevance: LOW]
          Cotton yarn (OE/ring/compact) → secondary woven/knit products      [relevance: LOW-MEDIUM]

        Rayon/Viscose:
          Rayon yarn → blended fabrics                                       [relevance: MEDIUM]

        RULE: If an article mentions material data, you MUST identify the specific form
        (e.g. "FDY", "PSF", "Nylon FDY", "DTY") — never just "polyester" or "nylon" alone.

        ══ C. TRACKED COMPETITOR COMPANIES ══
        Flag ANY article that explicitly names one or more of these companies:
        {names_block}

        ══ D. MANDATORY JSON OUTPUT (return ONLY this object, no markdown) ══
        {{
          "relevance_score":    <float 0.0–1.0>,
          "signal_category":    <"COST_IMPACT"|"DEMAND_SHIFT"|"SUPPLY_RISK"|"COMPETITOR_MOVE"|"REGULATORY"|null>,
          "signal_type":        <"price_move"|"price_signal"|"capacity_change"|"new_market"|"trend"|"regulation"|"competitor_mention"|"other">,
          "severity":           <"info"|"warning"|"alert">,
          "impact_score":       <integer 0–100, see rubric below>,
          "time_horizon":       <"short"|"mid"|"long"|null>,
          "action_tag":         <"MONITOR"|"RISK"|"OPPORTUNITY"|null>,
          "material_form":      <specific form from hierarchy above, e.g. "FDY", "PSF", "Nylon FDY"|null if no material data>,
          "affected_products":  <array from ["woven","knit","technical","laminated"], empty array if unclear>,
          "theme":              <short label, e.g. "Polyester Cost Pressure", "US Trade Risk", "Nylon Supply Squeeze"|null>,
          "rayon_relevance":    <"direct"|"indirect"|"none">,
          "summary_tr":         <ONE specific Turkish sentence — MUST name the material form, direction, and magnitude or geography>,
          "competitors_mentioned": <list of exact company names from article that appear in the tracked list; [] if none>,
          "price_signal": {{
            "material":      <specific material form, e.g. "Polyester FDY">,
            "direction":     <"up"|"down"|"stable">,
            "price_usd_kg":  <float or null>,
            "note":          <brief quote or context, max 80 chars>
          }} or null
        }}

        ══ E. IMPACT SCORE RUBRIC (strict) ══
        90–100: Direct material cost change >5% affecting FDY/POY/DTY/Nylon FDY (Rayon's core inputs)
        70–89:  Competitor strategic move OR supply disruption in key materials OR
                major trade policy directly affecting Rayon's export markets (tariffs, sanctions)
        50–69:  Industry demand shift in Rayon's markets OR regulatory change affecting
                Turkish textile sector OR significant competitor capacity change OR
                Turkish government textile policy with direct industry impact
        30–49:  Indirect market development OR general industry trend worth monitoring
        0–29:   Background context, no operational relevance

        ══ F. FIELD RULES ══
        signal_type:
          "competitor_mention" → article names a tracked competitor (primary signal)
          "price_signal"       → specific price figure given (USD/kg, index, % change)
          "price_move"         → only directional/qualitative price trend, no specific figure
          "capacity_change"    → factory expansion, closure, new production line, CapEx
          "new_market"         → new geography, customer segment, or certification
          "trend"              → broader industry direction
          "regulation"         → tariff, sanction, standard, compliance change

        rayon_relevance:
          "direct"   → directly affects Rayon's input costs, production, or key markets
          "indirect" → affects the broader industry in which Rayon competes
          "none"     → no plausible connection to Rayon's business

        time_horizon:
          "short" → effect within 1 month
          "mid"   → effect within 1–6 months
          "long"  → structural/strategic, 6+ months

        action_tag:
          "RISK"        → negative impact on costs or supply
          "OPPORTUNITY" → potential advantage (competitor weakness, new market)
          "MONITOR"     → watch but no action yet

        severity:
          alert   → immediate operational risk (major price shock, supply disruption, sanctions)
          warning → developing situation requiring tracking
          info    → background context or slow-moving trend

        summary_tr MUST be specific.
        BAD:  "Polyester piyasası artıyor."
        BAD:  "Sektörde önemli gelişmeler yaşanıyor."
        GOOD: "Çin'de POY fiyatları %4 artarak 7.200 RMB/ton seviyesine ulaştı, DTY maliyetlerini doğrudan etkiliyor."
        GOOD: "ABD gümrük tarifeleri Bangladeş menşeli polyester dokuma kumaşlara %25 ek vergi getiriyor."

        ══ G. DISCARD RULE ══
        If the article does NOT meaningfully impact any of these:
          - raw material costs (polyester/nylon/cotton input prices)
          - production supply (factory capacity, disruption, availability)
          - demand in Rayon's markets (EU, US, Middle East, Eastern Europe)
          - direct competitor moves (capacity, pricing, new markets)
          - Turkish government/industry textile policy
          - major buyer or trade-flow decisions affecting Turkish textile exporters

        Then set rayon_relevance="none" and relevance_score < 0.2.

        Do NOT discard — these are rayon_relevance="indirect" minimum:
          - Turkish government textile/industry policy statements
          - Trade association statements about sector challenges (ITKIB, TIM, TTGB)
          - Major buyer decisions affecting Turkish suppliers (e.g. brand cutting orders)
          - Turkish textile export performance data (volumes, destinations, trends)
          - US/EU/regional tariff or trade policy affecting Turkish textile exports

        Articles about the following topics are almost always irrelevant — set rayon_relevance="none":
          - design competitions, sustainability awards, CSR initiatives
          - general industry conferences or trade shows (unless specific price/capacity data)
          - fashion trends, retail consumer news, influencer/brand marketing
          - company financial results without supply/pricing implications
          - generic innovation or R&D announcements without commercial impact
    """)


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
    """Return all competitor company names + ids for matching and prompt injection."""
    cur.execute("SELECT id, name, category FROM companies ORDER BY name")
    return [{"id": str(row[0]), "name": row[1], "category": row[2]} for row in cur.fetchall()]


def match_companies(names_from_llm: list[str], companies: list[dict]) -> list[dict]:
    """
    For each LLM-returned name, find a matching tracked company.
    Uses case-insensitive substring match in both directions.
    Returns list of {"id": ..., "name": ...} dicts (deduplicated).
    """
    matched = {}
    for llm_name in names_from_llm:
        if not llm_name:
            continue
        needle = llm_name.strip().lower()
        for c in companies:
            haystack = c["name"].lower()
            if needle in haystack or haystack in needle:
                if c["id"] not in matched:
                    matched[c["id"]] = c
                break
    return list(matched.values())


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
    """Insert the primary (non-competitor-mention) market signal."""
    body = analysis["summary_tr"] or ""
    # Append price context to body if available
    ps = analysis.get("price_signal")
    if ps:
        direction_str = {"up": "↑", "down": "↓", "stable": "→"}.get(ps.get("direction", ""), "")
        price_str = f"  |  {ps['material']} {direction_str}"
        if ps.get("price_usd_kg"):
            price_str += f" ${ps['price_usd_kg']:.2f}/kg"
        if ps.get("note"):
            price_str += f" — {ps['note']}"
        body = body + price_str

    cur.execute(
        """
        INSERT INTO market_signals
            (signal_type, severity, title, body,
             source_table, source_id, source_url, company_id,
             llm_model, llm_tokens_in, llm_tokens_out, llm_cost_usd,
             impact_score, time_horizon, action_tag, signal_category,
             material_form, theme, affected_products, rayon_relevance)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            analysis["signal_type"],
            analysis["severity"],
            item["title"] or analysis["summary_tr"],
            body,
            "news_items",
            item["id"],
            item.get("url"),
            company_id,
            LLM_MODEL,
            tokens_in,
            tokens_out,
            cost,
            analysis.get("impact_score"),
            analysis.get("time_horizon"),
            analysis.get("action_tag"),
            analysis.get("signal_category"),
            analysis.get("material_form"),
            analysis.get("theme"),
            analysis.get("affected_products"),
            analysis.get("rayon_relevance"),
        ),
    )


def insert_competitor_signal(cur, item: dict, company: dict, analysis: dict,
                             tokens_in: int, tokens_out: int, cost: float):
    """
    Insert one competitor_mention market_signal linked to a specific company.
    Called once per matched competitor per article.
    """
    title = f"{company['name']} mentioned: {item['title'][:100]}" if item["title"] \
            else f"{company['name']} mentioned in news"
    body = analysis["summary_tr"] or ""

    cur.execute(
        """
        INSERT INTO market_signals
            (signal_type, severity, title, body,
             source_table, source_id, source_url, company_id,
             llm_model, llm_tokens_in, llm_tokens_out, llm_cost_usd,
             impact_score, time_horizon, action_tag, signal_category,
             material_form, theme, affected_products, rayon_relevance)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            "competitor_mention",
            analysis["severity"],
            title,
            body,
            "news_items",
            item["id"],
            item.get("url"),
            company["id"],
            LLM_MODEL,
            tokens_in,
            tokens_out,
            cost,
            analysis.get("impact_score"),
            analysis.get("time_horizon"),
            analysis.get("action_tag"),
            "COMPETITOR_MOVE",   # always for competitor signals
            analysis.get("material_form"),
            analysis.get("theme"),
            analysis.get("affected_products"),
            analysis.get("rayon_relevance"),
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


def call_openai(client, system_prompt: str, user_message: str) -> tuple[dict, int, int, float]:
    """
    Send one article to GPT-4o-mini and return (analysis_dict, tokens_in, tokens_out, cost_usd).
    Raises on API error or JSON parse failure.
    Uses direct HTTP requests — no OpenAI SDK required.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    response = req.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": LLM_MODEL,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            "temperature": 0.1,
            "max_tokens": 400,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    tokens_in  = data["usage"]["prompt_tokens"]
    tokens_out = data["usage"]["completion_tokens"]
    cost       = tokens_in * COST_PER_INPUT_TOKEN + tokens_out * COST_PER_OUTPUT_TOKEN

    raw = data["choices"][0]["message"]["content"]
    analysis = json.loads(raw)

    # ── Validate and sanitize ──────────────────────────────────────────────

    # relevance_score
    score = float(analysis.get("relevance_score", 0.0))
    analysis["relevance_score"] = round(max(0.0, min(1.0, score)), 3)

    # signal_type
    signal_type = analysis.get("signal_type", "other")
    if signal_type not in VALID_SIGNAL_TYPES:
        signal_type = "other"
    analysis["signal_type"] = signal_type

    # severity
    severity = analysis.get("severity", "info")
    if severity not in VALID_SEVERITIES:
        severity = "info"
    analysis["severity"] = severity

    # summary_tr
    analysis["summary_tr"] = (analysis.get("summary_tr") or "").strip() or None

    # competitors_mentioned: always a list of strings
    raw_competitors = analysis.get("competitors_mentioned") or []
    if isinstance(raw_competitors, str):
        raw_competitors = [raw_competitors] if raw_competitors else []
    analysis["competitors_mentioned"] = [str(c).strip() for c in raw_competitors if c]

    # price_signal: validate structure or set to None
    ps = analysis.get("price_signal")
    if ps and isinstance(ps, dict) and ps.get("material"):
        ps["direction"] = ps.get("direction", "stable")
        if ps["direction"] not in ("up", "down", "stable"):
            ps["direction"] = "stable"
        if ps.get("price_usd_kg") is not None:
            try:
                ps["price_usd_kg"] = float(ps["price_usd_kg"])
            except (TypeError, ValueError):
                ps["price_usd_kg"] = None
        analysis["price_signal"] = ps
    else:
        analysis["price_signal"] = None

    # ── New v2 fields ──────────────────────────────────────────────────────

    # impact_score: int 0-100
    try:
        impact = int(analysis.get("impact_score") or 0)
        analysis["impact_score"] = max(0, min(100, impact))
    except (TypeError, ValueError):
        analysis["impact_score"] = 0

    # time_horizon
    th = analysis.get("time_horizon")
    analysis["time_horizon"] = th if th in VALID_TIME_HORIZONS else None

    # action_tag
    at = analysis.get("action_tag")
    analysis["action_tag"] = at if at in VALID_ACTION_TAGS else None

    # signal_category
    sc = analysis.get("signal_category")
    analysis["signal_category"] = sc if sc in VALID_SIGNAL_CATS else None

    # material_form: free text, just strip
    mf = (analysis.get("material_form") or "").strip()
    analysis["material_form"] = mf or None

    # theme: free text, just strip
    theme = (analysis.get("theme") or "").strip()
    analysis["theme"] = theme or None

    # affected_products: filter to valid values
    raw_ap = analysis.get("affected_products") or []
    if isinstance(raw_ap, str):
        raw_ap = [raw_ap]
    analysis["affected_products"] = [p for p in raw_ap if p in VALID_AFFECTED] or None

    # rayon_relevance
    rr = analysis.get("rayon_relevance")
    analysis["rayon_relevance"] = rr if rr in VALID_RAYON_REL else "indirect"

    # ── Post-processing rules (F1–F4) ─────────────────────────────────────

    # F1: no material_form but high relevance → cap score
    if analysis["material_form"] is None and analysis["relevance_score"] > 0.4:
        log.debug("F1: material_form null, capping relevance_score %.3f → 0.35",
                  analysis["relevance_score"])
        analysis["relevance_score"] = min(analysis["relevance_score"], 0.35)

    # F2: generic summary_tr → cap impact_score
    summary_lower = (analysis["summary_tr"] or "").lower()
    if any(phrase in summary_lower for phrase in GENERIC_TR_PHRASES):
        log.warning("F2: generic summary_tr detected — capping impact_score %d → 30",
                    analysis["impact_score"])
        analysis["impact_score"] = min(analysis["impact_score"], 30)

    # F3: high impact but no time_horizon → default to 'mid'
    if analysis["impact_score"] > 60 and analysis["time_horizon"] is None:
        analysis["time_horizon"] = "mid"

    # F4: no signal_category but relevance above threshold → infer
    if analysis["signal_category"] is None and analysis["relevance_score"] > 0.4:
        analysis["signal_category"] = (
            "COST_IMPACT" if analysis["price_signal"] is not None else "DEMAND_SHIFT"
        )

    return analysis, tokens_in, tokens_out, cost


# ---------------------------------------------------------------------------
# Main analysis loop
# ---------------------------------------------------------------------------

def analyze(limit: int = DEFAULT_BATCH_LIMIT, dry_run: bool = False,
            print_signals: bool = False) -> dict:
    """
    Fetch up to `limit` unanalyzed news_items, run LLM analysis, persist results.
    Returns summary counts.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    try:
        conn = get_connection()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return {"processed": 0, "signaled": 0, "failed": 0, "total_cost_usd": 0.0, "error": str(e)}

    processed = signaled = failed = competitor_signals = 0
    total_cost = 0.0
    sample_signals: list[dict] = []

    with conn.cursor() as cur:
        items     = fetch_unanalyzed(cur, limit)
        companies = fetch_companies(cur)

    competitor_names = [c["name"] for c in companies]
    system_prompt = build_system_prompt(competitor_names)

    log.info(
        "Fetched %d unanalyzed articles; %d companies in prompt (%d competitors)",
        len(items),
        len(companies),
        sum(1 for c in companies if c.get("category") == "competitor"),
    )

    for item in items:
        log.info("Analyzing [%s] %.80s", item["id"], item["title"])

        user_msg = build_user_message(item)

        try:
            analysis, tokens_in, tokens_out, cost = call_openai(None, system_prompt, user_msg)
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
        matched = match_companies(analysis["competitors_mentioned"], companies)
        first_company_id = matched[0]["id"] if matched else None

        # Build a readable log line
        competitor_tag = ""
        if matched:
            competitor_tag = f"  competitors={[c['name'] for c in matched]}"
        price_tag = ""
        if analysis["price_signal"]:
            ps = analysis["price_signal"]
            price_tag = f"  price={ps['material']}({ps['direction']})"
            if ps.get("price_usd_kg"):
                price_tag += f"@${ps['price_usd_kg']:.2f}/kg"

        log.info(
            "  score=%.3f  impact=%3s  cat=%-16s  type=%-18s  sev=%-7s  "
            "mat=%-12s  rel=%-8s  horizon=%-5s  tokens=%d+%d  cost=$%.6f%s%s",
            analysis["relevance_score"],
            analysis.get("impact_score") if analysis.get("impact_score") is not None else "—",
            analysis.get("signal_category") or "—",
            analysis["signal_type"],
            analysis["severity"],
            analysis.get("material_form") or "—",
            analysis.get("rayon_relevance") or "—",
            analysis.get("time_horizon") or "—",
            tokens_in, tokens_out,
            cost,
            competitor_tag,
            price_tag,
        )

        if dry_run:
            log.info("  [DRY-RUN] skipping DB writes")
            processed += 1
            if analysis["relevance_score"] >= RELEVANCE_THRESHOLD:
                signaled += 1
            if matched:
                competitor_signals += len(matched)
            if print_signals and (matched or analysis["relevance_score"] >= RELEVANCE_THRESHOLD):
                sample_signals.append({
                    "title":          item["title"],
                    "score":          analysis["relevance_score"],
                    "type":           analysis["signal_type"],
                    "severity":       analysis["severity"],
                    "summary_tr":     analysis["summary_tr"],
                    "competitors":    [c["name"] for c in matched],
                    "price":          analysis["price_signal"],
                    "impact_score":   analysis.get("impact_score"),
                    "signal_category": analysis.get("signal_category"),
                    "material_form":  analysis.get("material_form"),
                    "theme":          analysis.get("theme"),
                    "action_tag":     analysis.get("action_tag"),
                    "time_horizon":   analysis.get("time_horizon"),
                    "rayon_relevance": analysis.get("rayon_relevance"),
                    "affected_products": analysis.get("affected_products"),
                })
            continue

        try:
            with conn:
                with conn.cursor() as cur:
                    update_news_item(cur, item["id"], analysis, first_company_id,
                                     tokens_in, tokens_out, cost)

                    signals_written = 0

                    # 1. Competitor mention signals — one per matched company
                    for company in matched:
                        if analysis["relevance_score"] >= COMPETITOR_MENTION_MIN_RELEVANCE:
                            insert_competitor_signal(cur, item, company, analysis,
                                                     tokens_in, tokens_out, cost)
                            signals_written += 1
                            competitor_signals += 1
                            log.info("  → competitor_mention: %s", company["name"])

                    # 2. Primary signal — emit when above threshold
                    #    F5: skip entirely if rayon_relevance='none' and no competitor match
                    rayon_rel = analysis.get("rayon_relevance", "indirect")
                    f5_gate = rayon_rel != "none" or bool(matched)
                    emit_primary = (
                        f5_gate and analysis["relevance_score"] >= RELEVANCE_THRESHOLD
                    )
                    if emit_primary:
                        # If all intelligence is captured by competitor signals, skip redundant signal
                        if analysis["signal_type"] == "competitor_mention" and signals_written > 0:
                            pass  # competitor signals already capture this
                        else:
                            insert_market_signal(cur, item, analysis, first_company_id,
                                                 tokens_in, tokens_out, cost)
                            signals_written += 1
                            log.info("  → market_signal: %s", analysis["signal_type"])

                    signaled += signals_written

            processed += 1

            if print_signals and signals_written > 0:
                sample_signals.append({
                    "title":          item["title"],
                    "score":          analysis["relevance_score"],
                    "type":           analysis["signal_type"],
                    "severity":       analysis["severity"],
                    "summary_tr":     analysis["summary_tr"],
                    "competitors":    [c["name"] for c in matched],
                    "price":          analysis["price_signal"],
                    "impact_score":   analysis.get("impact_score"),
                    "signal_category": analysis.get("signal_category"),
                    "material_form":  analysis.get("material_form"),
                    "theme":          analysis.get("theme"),
                    "action_tag":     analysis.get("action_tag"),
                    "time_horizon":   analysis.get("time_horizon"),
                    "rayon_relevance": analysis.get("rayon_relevance"),
                    "affected_products": analysis.get("affected_products"),
                })

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

    if print_signals and sample_signals:
        _print_sample_signals(sample_signals)

    return {
        "processed":          processed,
        "signaled":           signaled,
        "competitor_signals": competitor_signals,
        "failed":             failed,
        "total_cost_usd":     round(total_cost, 6),
    }


def _safe(text: str, maxlen: int = 0) -> str:
    """Encode to terminal code page with '?' substitution for unmappable chars."""
    enc = sys.stdout.encoding or "ascii"
    s = (text or "")[:maxlen] if maxlen else (text or "")
    return s.encode(enc, "replace").decode(enc)


def _print_sample_signals(signals: list[dict]):
    sep = "-" * 72
    lines = [
        "",
        sep,
        f"  SAMPLE SIGNALS ({len(signals)} articles with signals)",
        sep,
    ]
    for i, s in enumerate(signals, 1):
        lines.append(
            f"\n[{i}] score={s['score']:.2f}  impact={s.get('impact_score','—')}  "
            f"cat={s.get('signal_category') or '—'}  type={s['type']}  sev={s['severity']}"
        )
        lines.append(f"    Title   : {_safe(s['title'], 90)}")
        lines.append(f"    Signal  : {_safe(s['summary_tr'])}")
        lines.append(
            f"    Material: {s.get('material_form') or '—'}  "
            f"Products: {s.get('affected_products') or '—'}  "
            f"Horizon: {s.get('time_horizon') or '—'}  "
            f"Action: {s.get('action_tag') or '—'}  "
            f"Relevance: {s.get('rayon_relevance') or '—'}"
        )
        if s.get("theme"):
            lines.append(f"    Theme   : {_safe(s['theme'])}")
        if s["competitors"]:
            lines.append(f"    Companies: {_safe(', '.join(s['competitors']))}")
        if s["price"]:
            ps = s["price"]
            p = f"${ps['price_usd_kg']:.2f}/kg" if ps.get("price_usd_kg") else ps.get("direction", "")
            lines.append(f"    Price   : {_safe(ps['material'])} {p} — {_safe(ps.get('note', ''))}")
    lines += ["", sep, ""]
    print("\n".join(lines))


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
    parser.add_argument(
        "--print-signals",
        action="store_true",
        help="Print a formatted table of signals generated in this run",
    )
    args = parser.parse_args()

    log.info(
        "Starting %s (model=%s, limit=%d%s%s)",
        PIPELINE, LLM_MODEL, args.limit,
        ", DRY-RUN" if args.dry_run else "",
        ", PRINT-SIGNALS" if args.print_signals else "",
    )

    result = analyze(limit=args.limit, dry_run=args.dry_run, print_signals=args.print_signals)

    print(
        f"\nSummary — processed: {result['processed']}  "
        f"signals: {result['signaled']}  "
        f"competitor_mentions: {result['competitor_signals']}  "
        f"failed: {result['failed']}  "
        f"total_cost: ${result['total_cost_usd']:.6f}"
    )

    if result.get("error"):
        print(f"Fatal error: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
