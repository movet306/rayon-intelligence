"""
Phase E P1 Step 7: Backfill Mig 011 fields for existing market_signals
======================================================================

For market_signals where source_table='news_items' and entity_name IS NULL
(currently 68 signals), re-analyze source news_item via the current LLM 
prompt (b489019) and populate 6 Mig 011 fields:

- entity_name, entity_role
- commercial_exposure_type
- rayon_why_it_matters
- affected_business_line (JSONB)
- affected_material_family (JSONB)
- entity_id (FK to companies, via match_entities)

Reuses llm_analyzer functions:
- build_system_prompt, build_user_message, call_openai
- match_entities, fetch_companies

Cost: ~68 articles * ~$0.0005 = ~$0.035 (gpt-4o-mini)
Duration: ~3-5 minutes (with 0.4s rate-limit sleep)

Idempotency: WHERE entity_name IS NULL filter; safe to re-run.

Usage:
    $env:RAYON_DATABASE_URL = "postgresql://..."
    $env:OPENAI_API_KEY = "sk-..."
    python scripts/migrations/p1s7_backfill_mig011_fields.py
"""
import os
import sys
import time
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import psycopg2
import psycopg2.extras

from scrapers.llm_analyzer import (
    build_system_prompt,
    build_user_message,
    call_openai,
    match_entities,
    fetch_companies,
)


def main():
    db_url = os.environ.get("RAYON_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("Set RAYON_DATABASE_URL or DATABASE_URL")
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    print("Phase E P1 Step 7 - Mig 011 Backfill")
    print("=" * 60)

    entities = fetch_companies(cur)
    competitor_names = [e["name"] for e in entities]
    print(f"  Loaded {len(entities)} entities")

    cur.execute("""
        SELECT s.id AS signal_id, s.source_id,
               n.id AS news_id, n.url, n.title AS news_title, n.body_raw
        FROM market_signals s
        JOIN news_items n ON n.id = s.source_id
        WHERE s.source_table = 'news_items'
          AND s.entity_name IS NULL
        ORDER BY s.detected_at DESC
    """)
    signals = cur.fetchall()
    print(f"  Found {len(signals)} signals to backfill")
    print()

    if not signals:
        print("Nothing to do.")
        cur.close()
        conn.close()
        return

    system_prompt = build_system_prompt(competitor_names)
    # call_openai signature has 'client' param but body does not use it
    client = None

    updated = 0
    failed = 0
    total_cost = 0.0
    start = time.time()

    for i, sig in enumerate(signals, 1):
        item = {
            "id": str(sig["news_id"]),
            "url": sig["url"],
            "title": sig["news_title"] or "",
            "body_raw": sig["body_raw"] or "",
        }
        try:
            user_msg = build_user_message(item)
            analysis, tokens_in, tokens_out, cost = call_openai(client, system_prompt, user_msg)
            total_cost += cost
        except Exception as e:
            print(f"  [{i:>2}/{len(signals)}] LLM FAIL: {type(e).__name__}: {e}")
            failed += 1
            continue

        entity_id = None
        ent_name = analysis.get("entity_name")
        if ent_name:
            matched = match_entities([ent_name], entities)
            if matched:
                entity_id = matched[0]["id"]

        try:
            cur.execute("""
                UPDATE market_signals SET
                    entity_name              = %s,
                    entity_role              = %s,
                    commercial_exposure_type = %s,
                    rayon_why_it_matters     = %s,
                    affected_business_line   = %s,
                    affected_material_family = %s,
                    entity_id                = COALESCE(entity_id, %s)
                WHERE id = %s
            """, (
                analysis.get("entity_name"),
                analysis.get("entity_role"),
                analysis.get("commercial_exposure_type"),
                analysis.get("rayon_why_it_matters"),
                psycopg2.extras.Json(analysis.get("affected_business_line") or {}),
                psycopg2.extras.Json(analysis.get("affected_material_family") or {}),
                entity_id,
                sig["signal_id"],
            ))
            conn.commit()
            updated += 1
            ename = (analysis.get("entity_name") or "?")[:25]
            erole = (analysis.get("entity_role") or "?")[:15]
            exp = (analysis.get("commercial_exposure_type") or "?")[:15]
            print(f"  [{i:>2}/{len(signals)}] OK   {ename} / {erole} / {exp}")
        except Exception as e:
            print(f"  [{i:>2}/{len(signals)}] DB FAIL: {e}")
            traceback.print_exc()
            conn.rollback()
            failed += 1
            continue

        time.sleep(0.4)

    elapsed = time.time() - start
    print()
    print("=" * 60)
    print(f"Updated: {updated}/{len(signals)}")
    print(f"Failed:  {failed}")
    print(f"Cost:    ${total_cost:.4f}")
    print(f"Time:    {elapsed:.1f}s")
    print()

    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE entity_name IS NULL)          AS null_entity,
            COUNT(*) FILTER (WHERE rayon_why_it_matters IS NULL) AS null_why,
            COUNT(*) FILTER (WHERE commercial_exposure_type IS NULL) AS null_exp
        FROM market_signals
    """)
    r = cur.fetchone()
    print(f"Final NULL rates:")
    print(f"  entity_name              : {r['null_entity']}/{r['total']}")
    print(f"  rayon_why_it_matters     : {r['null_why']}/{r['total']}")
    print(f"  commercial_exposure_type : {r['null_exp']}/{r['total']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()