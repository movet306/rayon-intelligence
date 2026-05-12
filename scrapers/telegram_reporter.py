"""
scrapers/telegram_reporter.py
Reads unnotified market_signals from the last 24 hours, formats a Turkish
Telegram message grouped by severity, sends it, and marks signals as notified.

Usage:
    python scrapers/telegram_reporter.py
    python scrapers/telegram_reporter.py --hours 48
    python scrapers/telegram_reporter.py --dry-run

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
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PIPELINE       = "telegram_reporter"
TELEGRAM_API   = "https://api.telegram.org/bot{token}/sendMessage"
MSG_MAX_CHARS  = 4000   # stay 96 chars under Telegram's 4096 hard limit
DEFAULT_HOURS  = 24

# Severity ordering: highest priority first
SEVERITY_ORDER = ["alert", "warning", "info"]

SEVERITY_LABELS = {
    "alert":   "🚨 KRİTİK",
    "warning": "⚠️ UYARI",
    "info":    "ℹ️ BİLGİ",
}

SIGNAL_TYPE_LABELS = {
    "price_move":      "Fiyat Hareketi",
    "capacity_change": "Kapasite Değişikliği",
    "new_market":      "Yeni Pazar",
    "trend":           "Trend",
    "regulation":      "Düzenleme",
    "other":           "Diğer",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(url, connect_timeout=10)


def fetch_unnotified_signals(cur, hours: int) -> list[dict]:
    """Return unnotified signals from the last `hours` hours, newest first."""
    cur.execute(
        """
        SELECT
            ms.id,
            ms.signal_type,
            ms.severity,
            ms.title,
            ms.body,
            ms.detected_at,
            c.name AS company_name
        FROM  market_signals ms
        LEFT  JOIN entities c ON c.id = ms.entity_id
        WHERE ms.notified_at IS NULL
          AND ms.detected_at >= NOW() - (%s || ' hours')::INTERVAL
        ORDER BY
            CASE ms.severity
                WHEN 'alert'   THEN 1
                WHEN 'warning' THEN 2
                WHEN 'info'    THEN 3
            END,
            ms.detected_at DESC
        """,
        (str(hours),),
    )
    cols = ["id", "signal_type", "severity", "title", "body", "detected_at", "company_name"]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def mark_notified(cur, signal_ids: list[str]):
    """Set notified_at = NOW() for the given signal IDs."""
    cur.execute(
        """
        UPDATE market_signals
        SET    notified_at = NOW()
        WHERE  id = ANY(%s::uuid[])
        """,
        (signal_ids,),
    )


def record_failure(conn, error_message: str, error_detail: str, payload: dict):
    """Write one row to failed_jobs. Never raises."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO failed_jobs
                    (pipeline, job_type, error_message, error_detail, payload)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    PIPELINE,
                    "send_telegram",
                    error_message[:500],
                    error_detail[:2000],
                    json.dumps(payload),
                ),
            )
        conn.commit()
    except Exception as e:
        log.warning("Could not write to failed_jobs: %s", e)


# ---------------------------------------------------------------------------
# Message formatting
# ---------------------------------------------------------------------------

def _signal_block(signal: dict) -> str:
    """Format a single signal as an HTML block (no severity header)."""
    type_label    = SIGNAL_TYPE_LABELS.get(signal["signal_type"], signal["signal_type"])
    title         = signal["title"] or "(başlık yok)"
    body          = signal["body"]  or ""
    company_line  = f"\n  🏢 <i>{signal['company_name']}</i>" if signal["company_name"] else ""

    return (
        f"▪ <b>{title}</b>"
        f"\n  Tür: {type_label}{company_line}"
        + (f"\n  {body}" if body else "")
    )


def build_messages(signals: list[dict], hours: int) -> list[str]:
    """
    Build one or more Telegram HTML messages from the signal list.
    Splits on signal boundaries so no message exceeds MSG_MAX_CHARS.
    Each continuation message gets its own header.
    """
    total   = len(signals)
    now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    main_header = (
        f"<b>📊 Rayon Intelligence — Pazar Sinyalleri</b>\n"
        f"<i>Son {hours} saat  •  {total} sinyal  •  {now_str}</i>"
    )
    cont_header = "<b>📊 Rayon Intelligence — Pazar Sinyalleri (devam)</b>"

    if not signals:
        return [f"{main_header}\n\nℹ️ Bu periyotta bildirilecek sinyal yok."]

    # Group by severity (already ordered alert → warning → info from DB)
    groups: dict[str, list[dict]] = {s: [] for s in SEVERITY_ORDER}
    for sig in signals:
        groups[sig["severity"]].append(sig)

    # Flatten into (severity_heading_or_None, signal_block) pairs.
    # The heading is emitted before the first signal of each group,
    # and re-emitted at the top of a new message if the group spans messages.
    items: list[tuple[str | None, str]] = []
    for sev in SEVERITY_ORDER:
        grp = groups[sev]
        if not grp:
            continue
        label   = SEVERITY_LABELS[sev]
        heading = f"\n\n<b>{label} ({len(grp)})</b>"
        for i, sig in enumerate(grp):
            items.append((heading if i == 0 else None, _signal_block(sig)))

    # Pack signal by signal, tracking which severity heading is "pending"
    # so it can be re-emitted if a group spans a message boundary.
    messages: list[str] = []
    current  = main_header
    pending_heading: str | None = None   # heading to prepend if new msg starts mid-group

    for heading, block in items:
        if heading is not None:
            # Start of a new severity group
            candidate = current + heading + "\n" + block
            if len(candidate) <= MSG_MAX_CHARS:
                current = candidate
                pending_heading = heading
            else:
                # Flush current message and start fresh
                messages.append(current)
                current = cont_header + heading + "\n" + block
                pending_heading = heading
        else:
            # Continuation signal within the same severity group
            candidate = current + "\n\n" + block
            if len(candidate) <= MSG_MAX_CHARS:
                current = candidate
            else:
                messages.append(current)
                # Re-emit the group heading so the new message is self-contained
                current = cont_header + (pending_heading or "") + "\n" + block

    messages.append(current)
    return messages


# ---------------------------------------------------------------------------
# Telegram sending
# ---------------------------------------------------------------------------

def send_telegram(token: str, chat_id: str, text: str, timeout: int = 15) -> dict:
    """
    POST one message to Telegram. Returns the response JSON.
    Raises requests.HTTPError on non-2xx responses.
    """
    url  = TELEGRAM_API.format(token=token)
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Main reporter
# ---------------------------------------------------------------------------

def report(hours: int = DEFAULT_HOURS, dry_run: bool = False) -> dict:
    """
    Fetch unnotified signals, send Telegram message(s), mark as notified.
    Returns {"signals_found": int, "messages_sent": int, "failed": bool}.
    """
    token   = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID environment variable is not set")

    try:
        conn = get_connection()
    except Exception as e:
        log.error("DB connection failed: %s", e)
        return {"signals_found": 0, "messages_sent": 0, "failed": True, "error": str(e)}

    with conn.cursor() as cur:
        signals = fetch_unnotified_signals(cur, hours)

    log.info("Found %d unnotified signal(s) in last %d hours", len(signals), hours)

    if not signals:
        conn.close()
        return {"signals_found": 0, "messages_sent": 0, "failed": False}

    for sig in signals:
        log.info(
            "  [%s] %s — %.60s",
            sig["severity"].upper(),
            sig["signal_type"],
            sig["title"],
        )

    messages      = build_messages(signals, hours)
    signal_ids    = [str(s["id"]) for s in signals]
    messages_sent = 0

    if dry_run:
        log.info("[DRY-RUN] Would send %d message(s):", len(messages))
        for i, msg in enumerate(messages, 1):
            log.info("--- Message %d/%d (%d chars) ---\n%s", i, len(messages), len(msg), msg)
        conn.close()
        return {"signals_found": len(signals), "messages_sent": 0, "failed": False}

    # Send all messages; only mark notified if every send succeeds
    try:
        for i, msg in enumerate(messages, 1):
            log.info("Sending message %d/%d (%d chars) to chat %s", i, len(messages), len(msg), chat_id)
            result = send_telegram(token, chat_id, msg)
            if not result.get("ok"):
                raise RuntimeError(f"Telegram API returned ok=false: {result}")
            messages_sent += 1
            log.info("  Sent OK (message_id=%s)", result.get("result", {}).get("message_id"))

    except Exception as e:
        log.error("Telegram send failed: %s", e)
        record_failure(
            conn,
            error_message=str(e),
            error_detail=traceback.format_exc(),
            payload={"signal_ids": signal_ids, "messages_sent": messages_sent},
        )
        conn.close()
        return {
            "signals_found": len(signals),
            "messages_sent": messages_sent,
            "failed": True,
            "error": str(e),
        }

    # All messages sent — mark every signal as notified in one transaction
    try:
        with conn:
            with conn.cursor() as cur:
                mark_notified(cur, signal_ids)
        log.info("Marked %d signal(s) as notified", len(signal_ids))
    except Exception as e:
        log.error("Failed to mark signals as notified: %s", e)
        record_failure(
            conn,
            error_message=str(e),
            error_detail=traceback.format_exc(),
            payload={"signal_ids": signal_ids},
        )

    conn.close()
    return {"signals_found": len(signals), "messages_sent": messages_sent, "failed": False}


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Send unnotified market_signals to Telegram"
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_HOURS,
        metavar="N",
        help=f"Look-back window in hours (default: {DEFAULT_HOURS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Format and log the message(s) but do not send or update notified_at",
    )
    args = parser.parse_args()

    log.info(
        "Starting %s (hours=%d%s)",
        PIPELINE, args.hours, ", DRY-RUN" if args.dry_run else "",
    )

    result = report(hours=args.hours, dry_run=args.dry_run)

    print(
        f"\nSummary — signals_found: {result['signals_found']}  "
        f"messages_sent: {result['messages_sent']}  "
        f"failed: {result['failed']}"
    )

    if result.get("error"):
        print(f"Error: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
