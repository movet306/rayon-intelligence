"""Date parsing utilities for scrapers.

Extracts published_at from various sources:
- HTML <meta property="article:published_time"> or similar
- JSON-LD datePublished
- <time datetime="..."> element
- URL regex fallback (e.g. /2025/03/15/)
- WordPress REST API date field
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Union

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


# Common meta tag property/name values that indicate publish time
META_PUBLISH_KEYS = (
    "article:published_time",
    "og:article:published_time",
    "publish_date",
    "datePublished",
    "pubdate",
    "date",
    "DC.date.issued",
    "sailthru.date",
    "parsely-pub-date",
)


def parse_published_at(
    soup_or_html: Union[BeautifulSoup, str, bytes, None] = None,
    url: Optional[str] = None,
) -> Optional[datetime]:
    """Try multiple strategies to extract published_at.

    Returns a timezone-aware datetime (UTC), or None if no date found.
    """
    soup: Optional[BeautifulSoup] = None
    if isinstance(soup_or_html, BeautifulSoup):
        soup = soup_or_html
    elif isinstance(soup_or_html, (str, bytes)):
        try:
            soup = BeautifulSoup(soup_or_html, "html.parser")
        except Exception as e:
            log.debug("BeautifulSoup parse failed: %s", e)

    if soup is not None:
        # Strategy 1: <meta property="article:published_time"> etc.
        for key in META_PUBLISH_KEYS:
            for attr in ("property", "name", "itemprop"):
                tag = soup.find("meta", attrs={attr: key})
                if tag and tag.get("content"):
                    dt = _try_parse_iso(tag["content"])
                    if dt:
                        return dt

        # Strategy 2: JSON-LD datePublished
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                txt = script.string or script.get_text()
                if not txt:
                    continue
                data = json.loads(txt)
                dt = _extract_jsonld_date(data)
                if dt:
                    return dt
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                log.debug("JSON-LD parse failed: %s", e)
                continue

        # Strategy 3: <time datetime="...">
        for time_tag in soup.find_all("time"):
            if time_tag.get("datetime"):
                dt = _try_parse_iso(time_tag["datetime"])
                if dt:
                    return dt

    # Strategy 4: URL regex fallback (/YYYY/MM/DD/)
    if url:
        m = re.search(r"/(\d{4})/(\d{1,2})/(\d{1,2})(?:/|$)", url)
        if m:
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if 2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                    return datetime(y, mo, d, tzinfo=timezone.utc)
            except ValueError:
                pass

    return None


def parse_wp_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse a WordPress REST API date string (ISO 8601)."""
    return _try_parse_iso(date_str) if date_str else None


def _extract_jsonld_date(data) -> Optional[datetime]:
    """Recursively search JSON-LD for datePublished or dateCreated."""
    if isinstance(data, dict):
        for key in ("datePublished", "dateCreated", "uploadDate"):
            if key in data:
                dt = _try_parse_iso(data[key])
                if dt:
                    return dt
        if "@graph" in data and isinstance(data["@graph"], list):
            for item in data["@graph"]:
                dt = _extract_jsonld_date(item)
                if dt:
                    return dt
        for v in data.values():
            if isinstance(v, (dict, list)):
                dt = _extract_jsonld_date(v)
                if dt:
                    return dt
    elif isinstance(data, list):
        for item in data:
            dt = _extract_jsonld_date(item)
            if dt:
                return dt
    return None


def _try_parse_iso(s) -> Optional[datetime]:
    """Try to parse an ISO 8601 date string, returning UTC datetime or None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d %B %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None