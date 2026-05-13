"""
scrapers/tender_ingestion/tender_bulletin_scraper.py

Phase F1 (rule_v2): EKAP Kamu Ihale Bulteni PDF scraper.

Pipeline:
  1. ZIP -> extract main PDF (not _SONUC)
  2. pdfplumber text extraction
  3. Regex section split + structured field parse
  4. Rule-based relevance scoring:
       text_keyword_score    (from lkp_tender_keywords)
       institution_boost     (from lkp_institution_priority)
       exclusion_dominance   (any exclusion match -> REJECTED)
  5. Capped HIGH promotion:
       text_score == 0 + institution_boost > 0  ->  LOW (watchlist only)
       text_score == 0 + institution_boost <= 0 ->  REJECTED (no match)
       text_score >  0                          ->  combined threshold
  6. UPSERT into tenders + audit row in tender_relevance_history
  7. Emit market_signals row for HIGH/MEDIUM (idempotent)

Idempotent: re-running on the same ZIP produces no new rows.
"""
import argparse
import logging
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pdfplumber
import psycopg2

from scrapers.tender_ingestion.util import tr_normalize

SOURCE = "ekap_bulletin"
ENGINE_VERSION = "rule_v2"
BULLETIN_DIR = Path("data/tender_bulletins")
ISTANBUL_TZ = timezone(timedelta(hours=3))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path):
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
        logger.info(f"  Extracting {n} pages from {pdf_path.name}...")
        for i, page in enumerate(pdf.pages):
            pages.append(page.extract_text() or "")
            if (i + 1) % 50 == 0:
                logger.info(f"    {i+1}/{n} pages done")
    return "\n".join(pages)


def parse_tender_section(section):
    ekap_match = re.search("\u0130hale Kay\u0131t Numaras\u0131 \\(\u0130KN\\)\\s*:\\s*(\\d{4}/\\d+)", section)
    if not ekap_match:
        return None
    ekap_id = ekap_match.group(1)

    def squash(s):
        return re.sub(r"\s+", " ", s.strip())

    title_match = re.search("3\\.1\\.\\s*Ad\u0131\\s*:\\s*(.+?)(?=3\\.2\\.)", section, re.DOTALL)
    title = squash(title_match.group(1))[:500] if title_match else None

    inst_match = re.search("1\\.1\\.\\s*Ad\u0131\\s*:\\s*(.+?)(?=1\\.2\\.)", section, re.DOTALL)
    institution = squash(inst_match.group(1))[:500] if inst_match else None

    dl = re.search(
        "2\\.1\\.\\s*Tarih ve Saati\\s*:\\s*(\\d{2})\\.(\\d{2})\\.(\\d{4})\\s*-\\s*(\\d{2}):(\\d{2})",
        section,
    )
    deadline_at = None
    if dl:
        d, m, y, h, mi = dl.groups()
        try:
            local = datetime(int(y), int(m), int(d), int(h), int(mi), tzinfo=ISTANBUL_TZ)
            deadline_at = local.astimezone(timezone.utc)
        except ValueError:
            pass

    desc_match = re.search(
        "3\\.2\\.\\s*Niteli\u011fi, t\u00fcr\u00fc ve miktar\u0131\\s*:\\s*(.+?)(?=3\\.3\\.)",
        section, re.DOTALL,
    )
    description = squash(desc_match.group(1)) if desc_match else None
    if description and len(description) > 2000:
        description = description[:2000] + "..."

    if not title or not institution:
        return None

    return {
        "ekap_id": ekap_id,
        "title": title,
        "institution": institution,
        "deadline_at": deadline_at,
        "description": description,
    }


def parse_pdf_to_tenders(pdf_path, procurement_type):
    full_text = extract_text_from_pdf(pdf_path)
    sections = re.split("(?=\u0130hale Kay\u0131t Numaras\u0131 \\(\u0130KN\\))", full_text)
    logger.info(f"  Found {len(sections)-1} candidate tender sections")
    tenders = []
    for sec in sections[1:]:
        t = parse_tender_section(sec)
        if t:
            t["procurement_type"] = procurement_type
            t["raw_text"] = sec[:5000]
            tenders.append(t)
    logger.info(f"  Parsed {len(tenders)} tenders with required fields")
    return tenders


def load_keywords(cur):
    cur.execute("SELECT keyword, normalized, keyword_class, weight FROM lkp_tender_keywords")
    return [
        {"keyword": r[0], "normalized": r[1], "keyword_class": r[2], "weight": r[3]}
        for r in cur.fetchall()
    ]


def load_institution_priorities(cur):
    cur.execute("SELECT pattern, normalized_pattern, weight, category FROM lkp_institution_priority")
    return [
        {"pattern": r[0], "normalized_pattern": r[1], "weight": r[2], "category": r[3]}
        for r in cur.fetchall()
    ]


_KW_MATCH_CACHE = {}

def _kw_matches(kw_normalized, haystack):
    """Token-aware match: keyword + optional Turkish suffix (up to 5 letters).
    Prevents false positives like 'mont' matching 'montaj'."""
    pat = _KW_MATCH_CACHE.get(kw_normalized)
    if pat is None:
        pat = re.compile(
            r"(^|\W)" + re.escape(kw_normalized) + r"[a-zçğıöşü0-9]{0,5}(\W|$)"
        )
        _KW_MATCH_CACHE[kw_normalized] = pat
    return pat.search(haystack) is not None


def score_tender(tender, keywords, inst_priorities):
    title = tender.get("title") or ""
    description = tender.get("description") or ""
    institution = tender.get("institution") or ""

    haystack = tr_normalize(title + " " + description)
    inst_norm = tr_normalize(institution)

    matched_by_norm = {}
    excluded = []
    for kw in keywords:
        if _kw_matches(kw["normalized"], haystack):
            if kw["keyword_class"] == "exclusion":
                excluded.append(kw["keyword"])
            else:
                existing = matched_by_norm.get(kw["normalized"])
                if not existing or kw["weight"] > existing["weight"]:
                    matched_by_norm[kw["normalized"]] = kw

    matched = list(matched_by_norm.values())
    matched_keywords = [k["keyword"] for k in matched]
    text_score = sum(k["weight"] for k in matched)

    matched_insts = [ip for ip in inst_priorities if ip["normalized_pattern"] in inst_norm]
    if matched_insts:
        best_inst = max(matched_insts, key=lambda x: x["weight"])
        institution_boost = best_inst["weight"]
        institution_pattern = best_inst["pattern"]
    else:
        institution_boost = 0
        institution_pattern = None

    if tender.get("procurement_type") == "Yap\u0131m":
        return {
            "relevance_level": "REJECTED",
            "relevance_score": 0,
            "matched_keywords": matched_keywords,
            "text_score": text_score,
            "institution_boost": institution_boost,
            "matched_institution": institution_pattern,
            "rejection_reason": "Procurement type Yap\u0131m (construction)",
        }

    if excluded:
        return {
            "relevance_level": "REJECTED",
            "relevance_score": max(0, text_score + institution_boost),
            "matched_keywords": matched_keywords,
            "text_score": text_score,
            "institution_boost": institution_boost,
            "matched_institution": institution_pattern,
            "rejection_reason": "Exclusion match: " + ", ".join(excluded),
        }

    if text_score == 0:
        # Mert + ChatGPT review: institution alone is NOT sufficient signal.
        # Without a textile/clothing keyword, REJECT regardless of institution boost.
        return {
            "relevance_level": "REJECTED",
            "relevance_score": 0,
            "matched_keywords": [],
            "text_score": 0,
            "institution_boost": institution_boost,
            "matched_institution": institution_pattern,
            "rejection_reason": (
                f"No textile keyword match (institution boost {institution_boost} ignored)"
                if institution_boost > 0 else "No keyword match"
            ),
        }

    combined = max(0, min(text_score + institution_boost, 100))

    if combined >= 50:
        level = "HIGH"
    elif combined >= 20:
        level = "MEDIUM"
    elif combined >= 1:
        level = "LOW"
    else:
        return {
            "relevance_level": "REJECTED",
            "relevance_score": 0,
            "matched_keywords": matched_keywords,
            "text_score": text_score,
            "institution_boost": institution_boost,
            "matched_institution": institution_pattern,
            "rejection_reason": f"Institution penalty ({institution_boost}) negated text score ({text_score})",
        }

    return {
        "relevance_level": level,
        "relevance_score": combined,
        "matched_keywords": matched_keywords,
        "text_score": text_score,
        "institution_boost": institution_boost,
        "matched_institution": institution_pattern,
        "rejection_reason": None,
    }


def upsert_tender(cur, tender, assessment):
    cur.execute(
        """
        INSERT INTO tenders (
            source, ekap_id,
            title, description, institution,
            procurement_type, tender_status,
            deadline_at, raw_text,
            relevance_level, relevance_score, matched_keywords, rejection_reason
        )
        VALUES (%s,%s, %s,%s,%s, %s,%s, %s,%s, %s,%s,%s,%s)
        ON CONFLICT (source, ekap_id) DO UPDATE SET
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            institution = EXCLUDED.institution,
            deadline_at = EXCLUDED.deadline_at,
            raw_text = EXCLUDED.raw_text,
            relevance_level = EXCLUDED.relevance_level,
            relevance_score = EXCLUDED.relevance_score,
            matched_keywords = EXCLUDED.matched_keywords,
            rejection_reason = EXCLUDED.rejection_reason,
            updated_at = NOW(),
            status_last_checked_at = NOW()
        RETURNING id, (xmax = 0) AS inserted
        """,
        (
            SOURCE, tender["ekap_id"],
            tender["title"], tender.get("description"), tender["institution"],
            tender.get("procurement_type"), "open",
            tender["deadline_at"], tender.get("raw_text"),
            assessment["relevance_level"], assessment["relevance_score"],
            assessment["matched_keywords"], assessment["rejection_reason"],
        ),
    )
    tender_id, inserted = cur.fetchone()

    cur.execute(
        """
        INSERT INTO tender_relevance_history (
            tender_id, engine_version, method,
            relevance_level, relevance_score, matched_keywords, rejection_reason
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            str(tender_id), ENGINE_VERSION, "keyword_rule_plus_institution",
            assessment["relevance_level"], assessment["relevance_score"],
            assessment["matched_keywords"], assessment["rejection_reason"],
        ),
    )
    return str(tender_id), ("inserted" if inserted else "updated")


def emit_market_signal(cur, tender_id, tender, assessment):
    # DISABLED 2026-05-13: tenders displayed in dedicated Tender Intelligence tab,
    # no longer duplicated to market_signals. Re-enable by removing the next line.
    return False
    if assessment["relevance_level"] not in ("HIGH", "MEDIUM"):
        return False

    cur.execute(
        "SELECT id FROM market_signals WHERE source_table=%s AND source_id=%s",
        ("tenders", tender_id),
    )
    if cur.fetchone():
        return False

    severity = "alert" if assessment["relevance_level"] == "HIGH" else "warning"
    title = f"YEN\u0130 \u0130HALE: {tender['title'][:100]}"
    deadline_str = (
        tender["deadline_at"].astimezone(ISTANBUL_TZ).strftime("%d.%m.%Y %H:%M")
        if tender["deadline_at"] else "?"
    )
    inst_note = ""
    if assessment.get("matched_institution"):
        inst_note = f" [Kurum boost: {assessment['matched_institution']} +{assessment['institution_boost']}]"
    body = (
        f"\u0130dare: {tender['institution']}\n"
        f"Son tarih: {deadline_str}\n"
        f"E\u015fle\u015fen kelimeler: {', '.join(assessment['matched_keywords'])}{inst_note}"
    )

    cur.execute(
        """
        INSERT INTO market_signals (
            signal_type, severity, title, body,
            source_table, source_id,
            signal_category, action_tag, impact_score,
            commercial_exposure_type, entity_name, entity_role,
            signal_priority_profile
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            "tender_active", severity, title, body,
            "tenders", tender_id,
            "OTHER", "OPPORTUNITY", assessment["relevance_score"],
            "OUTPUT_DEMAND", tender["institution"][:200], "customer",
            "DEMAND",
        ),
    )
    return True


def process_zip(zip_path, db_url, limit=None):
    logger.info(f"Processing {zip_path.name}")

    # Support both legacy BULTEN_DDMMYYYY_TYPE.zip and new EKAP_YYYY-MM-DD_TYPE.zip
    m_new = re.match(r"EKAP_(\d{4})-(\d{2})-(\d{2})_(\w+)\.zip", zip_path.name)
    m_legacy = re.match(r"BULTEN_(\d{8})_(\w+)\.zip", zip_path.name)
    if m_new:
        type_str = m_new.group(4)
    elif m_legacy:
        type_str = m_legacy.group(2)
    else:
        raise ValueError(f"Unexpected ZIP name: {zip_path.name}")
    type_map = {
        "MAL": "Mal", "HIZMET": "Hizmet",
        "YAPIM": "Yap\u0131m", "DANISMANLIK": "Dan\u0131\u015fmanl\u0131k",
    }
    procurement_type = type_map.get(type_str, "Mal")
    logger.info(f"  Procurement type: {procurement_type}")

    with zipfile.ZipFile(zip_path) as zf:
        main_pdfs = [n for n in zf.namelist() if n.endswith(".pdf") and "_SONUC" not in n]
        if not main_pdfs:
            raise ValueError(f"No main PDF in ZIP: {zf.namelist()}")
        pdf_name = main_pdfs[0]
        temp_pdf = BULLETIN_DIR / pdf_name
        with zf.open(pdf_name) as src, open(temp_pdf, "wb") as dst:
            dst.write(src.read())
        logger.info(f"  Extracted {pdf_name}")

    try:
        t0 = time.time()
        tenders = parse_pdf_to_tenders(temp_pdf, procurement_type)
        logger.info(f"  PDF parsed in {time.time()-t0:.1f}s")

        if limit:
            tenders = tenders[:limit]
            logger.info(f"  Limiting to first {limit}")

        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        keywords = load_keywords(cur)
        inst_priorities = load_institution_priorities(cur)
        logger.info(f"  Loaded {len(keywords)} keywords + {len(inst_priorities)} institution priorities")

        stats = {
            "total": 0, "inserted": 0, "updated": 0,
            "HIGH": 0, "MEDIUM": 0, "LOW": 0, "REJECTED": 0,
            "signals_emitted": 0, "institution_boosted": 0,
        }
        accepted = []
        watchlist = []
        for tender in tenders:
            assessment = score_tender(tender, keywords, inst_priorities)
            tender_id, action = upsert_tender(cur, tender, assessment)

            stats["total"] += 1
            stats[action] += 1
            stats[assessment["relevance_level"]] += 1
            if assessment.get("matched_institution"):
                stats["institution_boosted"] += 1

            if emit_market_signal(cur, tender_id, tender, assessment):
                stats["signals_emitted"] += 1

            if assessment["relevance_level"] in ("HIGH", "MEDIUM"):
                accepted.append((tender, assessment))
            elif assessment["relevance_level"] == "LOW" and assessment.get("matched_institution"):
                watchlist.append((tender, assessment))

        conn.commit()
        cur.close()
        conn.close()

        logger.info(f"  STATS: {stats}")

        if accepted:
            logger.info(f"  --- {len(accepted)} HIGH/MEDIUM tender(s) ---")
            for t, a in accepted:
                logger.info(
                    f"    [{a['relevance_level']:6s} {a['relevance_score']:3d}] "
                    f"{t['ekap_id']}  {t['title'][:70]}"
                )
                inst_part = f"  inst={a.get('matched_institution')} +{a['institution_boost']}" if a.get("matched_institution") else ""
                logger.info(f"          text_score={a['text_score']}{inst_part}")
                logger.info(f"          {t['institution'][:80]}")

        if watchlist:
            logger.info(f"  --- {len(watchlist)} watchlist (institution-only, no text keyword) ---")
            for t, a in watchlist:
                logger.info(
                    f"    [LOW    {a['relevance_score']:3d}] {t['ekap_id']}  {t['title'][:70]}"
                )
                logger.info(f"          inst={a['matched_institution']} +{a['institution_boost']}")

        return stats
    finally:
        if temp_pdf.exists():
            temp_pdf.unlink()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--zip", default=None)
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    db_url = os.environ.get("DATABASE_URL") or os.environ.get("RAYON_DATABASE_URL")
    if not db_url:
        sys.exit("Set DATABASE_URL or RAYON_DATABASE_URL")

    if args.zip:
        zips = [Path(args.zip)]
    else:
        zips = sorted(BULLETIN_DIR.glob("BULTEN_*.zip"))

    if not zips:
        logger.warning(f"No ZIPs in {BULLETIN_DIR}/")
        return

    logger.info(f"Found {len(zips)} ZIP(s)")
    for z in zips:
        try:
            process_zip(z, db_url, limit=args.limit)
        except Exception as e:
            logger.error(f"FAILED {z.name}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
