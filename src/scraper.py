"""
scraper.py — IQM2 RSS Feed Parser
San Ramon Council Intelligence Platform

Parses the IQM2 RSS calendar feed to extract City Council meetings
with their associated agenda, minutes, and webcast resource URLs.

NOTE: RSS feed only publishes meetings with filed agendas. This is
intentional — every record is guaranteed to have a document trail.
"""

import re
import time
import logging
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

IQM2_RSS  = "https://sanramonca.iqm2.com/Services/RSS.aspx?Feed=Calendar"
IQM2_BASE = "https://sanramonca.iqm2.com/Citizens"
HEADERS   = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT   = 15
MAX_RETRIES = 2


def _abs(href: str | None) -> str | None:
    """
    Makes relative IQM2 hrefs absolute.
    BUG-06 FIX: returns None (not '') for empty/None input.
    """
    if not href or not href.strip():
        return None
    href = href.strip()
    if href.startswith("http"):
        return href
    return f"{IQM2_BASE}/{href.lstrip('/')}"


def _parse_date(heading: str) -> datetime | None:
    """Extracts and parses a date from an IQM2 RSS heading string."""
    m = re.search(
        r"(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
        r"\s+\d{1,2},\s+\d{4}(?:\s+\d{1,2}:\d{2}\s*(?:AM|PM))?)",
        heading, re.IGNORECASE,
    )
    if not m:
        return None
    s = m.group(1).strip()
    for fmt in ("%b %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _fetch_rss_html() -> str | None:
    """
    Fetches raw RSS HTML with retry logic.
    BUG-15 FIX: retries once on failure with 2s backoff; surfaces error clearly.
    """
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(IQM2_RSS, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            logger.info(f"Scraper: RSS fetch OK ({len(resp.text):,} chars) on attempt {attempt}")
            return resp.text
        except Exception as e:
            last_exc = e
            logger.warning(f"Scraper: Attempt {attempt}/{MAX_RETRIES} failed — {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2)
    logger.error(f"Scraper: All {MAX_RETRIES} attempts failed. Last error: {last_exc}")
    return None


def _fetch_rss() -> list[dict]:
    """
    Parses IQM2 RSS feed into structured meeting dicts.
    Groups Agenda / Minutes / Webcast entries by date into one record each.
    """
    html = _fetch_rss_html()
    if not html:
        return []

    soup    = BeautifulSoup(html, "html.parser")
    by_date: dict[str, dict] = {}

    for div in soup.find_all("div"):
        h2 = div.find("h2")
        if not h2:
            continue
        heading = h2.get_text(strip=True)

        if "City Council" not in heading or "Cancelled" in heading:
            continue

        m_dt = _parse_date(heading)
        if not m_dt:
            logger.warning(f"Scraper: Could not parse date from: '{heading}'")
            continue

        iso = m_dt.strftime("%Y-%m-%d")

        # Collect all valid links in this div block
        # BUG-06 FIX: filter out None hrefs from _abs()
        div_links = [
            (a.get_text(strip=True), _abs(a["href"]))
            for a in div.find_all("a", href=True)
            if _abs(a["href"])  # exclude None/empty
        ]

        if iso not in by_date:
            by_date[iso] = {
                "name":        "City Council",
                "date":        m_dt.strftime("%m/%d/%Y"),
                "iso":         iso,
                "detail_url":  None,
                "agenda_url":  None,
                "minutes_url": None,
                "has_webcast": False,
                "webcast_url": None,
            }

        entry = by_date[iso]

        if "- Agenda -" in heading:
            for _, href in div_links:
                if "Detail_Meeting" in href and not entry["detail_url"]:
                    entry["detail_url"] = href
                if "FileOpen" in href and "Type=14" in href and not entry["agenda_url"]:
                    entry["agenda_url"] = href
            # Fallback: any FileOpen link
            if not entry["agenda_url"]:
                for _, href in div_links:
                    if "FileOpen" in href:
                        entry["agenda_url"] = href
                        break

        elif "- Minutes -" in heading:
            for _, href in div_links:
                if "FileOpen" in href:
                    entry["minutes_url"] = href
                    break
            # Fallback: link text containing "minute" or Type=16
            if not entry["minutes_url"]:
                for text, href in div_links:
                    if "minute" in text.lower() or "Type=16" in href:
                        entry["minutes_url"] = href
                        break

        elif "- Webcast -" in heading:
            entry["has_webcast"] = True
            # Use THIS entry's own Detail_Meeting link (different ID from Agenda)
            for _, href in div_links:
                if "Detail_Meeting" in href:
                    entry["webcast_url"] = href
                    break

        logger.debug(f"Scraper: Processed '{heading[:65]}' → {iso}")

    meetings = sorted(by_date.values(), key=lambda x: x["iso"], reverse=True)
    logger.info(f"Scraper: {len(meetings)} unique City Council meetings parsed from RSS")
    return meetings


def get_meetings_in_range(
    start_date: str = "2025-01-01",
    end_date:   str = "2026-12-31",
) -> list[dict]:
    """
    Returns City Council meetings within the given ISO date range,
    sorted newest-first.
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt   = datetime.strptime(end_date,   "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"Scraper: Invalid date format — {e}")
        return []

    filtered = [
        m for m in _fetch_rss()
        if start_dt <= datetime.strptime(m["iso"], "%Y-%m-%d") <= end_dt
    ]
    filtered.sort(key=lambda x: x["iso"], reverse=True)
    logger.info(f"Scraper: {len(filtered)} meetings between {start_date} and {end_date}")
    return filtered


def get_latest_meeting() -> dict | None:
    """
    Returns the most recent City Council meeting in the last 90 days.
    Returns None if none found (network error or genuinely no meetings).
    """
    now       = datetime.now()
    end_iso   = now.strftime("%Y-%m-%d")
    start_iso = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    meetings  = get_meetings_in_range(start_iso, end_iso)
    if meetings:
        logger.info(f"Scraper: Latest meeting → {meetings[0]['iso']}")
        return meetings[0]
    logger.warning("Scraper: No City Council meetings found in last 90 days")
    return None
