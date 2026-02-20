"""
scraper.py — IQM2 RSS Feed Parser
San Ramon Council Intelligence Platform
"""

import re
import logging
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

IQM2_RSS     = "https://sanramonca.iqm2.com/Services/RSS.aspx?Feed=Calendar"
IQM2_BASE    = "https://sanramonca.iqm2.com/Citizens"
HEADERS      = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TIMEOUT      = 15


def _parse_date(heading: str) -> datetime | None:
    match = re.search(
        r"(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
        r"\s+\d{1,2},\s+\d{4}(?:\s+\d{1,2}:\d{2}\s*(?:AM|PM))?)",
        heading, re.IGNORECASE
    )
    if not match:
        return None
    date_str = match.group(1).strip()
    for fmt in ("%b %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _abs(href: str) -> str:
    """Makes relative IQM2 hrefs absolute."""
    if href.startswith("http"):
        return href
    return f"{IQM2_BASE}/{href.lstrip('/')}"


def _fetch_rss() -> list[dict]:
    logger.info(f"Scraper: GET {IQM2_RSS}")
    try:
        resp = requests.get(IQM2_RSS, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Scraper: RSS fetch failed — {e}", exc_info=True)
        return []

    soup   = BeautifulSoup(resp.text, "html.parser")
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
            continue

        iso = m_dt.strftime("%Y-%m-%d")

        # Collect ALL links in this div block
        all_links = {a.get_text(strip=True): _abs(a["href"]) for a in div.find_all("a", href=True)}

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

        # Grab detail URL from "View Web Agenda" or "View Web" links
        for text, href in all_links.items():
            if "Detail_Meeting" in href and not entry["detail_url"]:
                entry["detail_url"] = href

        if "- Agenda -" in heading:
            for text, href in all_links.items():
                if "FileOpen" in href and "Type=14" in href:
                    entry["agenda_url"] = href
                    break
            # Fallback: any FileOpen link
            if not entry["agenda_url"]:
                for text, href in all_links.items():
                    if "FileOpen" in href and not entry["agenda_url"]:
                        entry["agenda_url"] = href

        elif "- Minutes -" in heading:
            for text, href in all_links.items():
                # Minutes can be Type=16 or just a PDF download
                if "FileOpen" in href:
                    entry["minutes_url"] = href
                    break
            # Fallback: look for "Minutes" in link text
            if not entry["minutes_url"]:
                for text, href in all_links.items():
                    if "minute" in text.lower() and "FileOpen" in href:
                        entry["minutes_url"] = href
                        break

        elif "- Webcast -" in heading:
            entry["has_webcast"] = True
            # Webcast entry links to a Detail_Meeting page with video player
            for text, href in all_links.items():
                if "Detail_Meeting" in href:
                    entry["webcast_url"] = href
                    break

        logger.debug(f"Scraper: {heading[:60]} → {iso}")

    meetings = sorted(by_date.values(), key=lambda x: x["iso"], reverse=True)
    logger.info(f"Scraper: {len(meetings)} City Council meetings in RSS")
    return meetings


def get_meetings_in_range(start_date: str = "2025-01-01",
                           end_date:   str = "2026-12-31") -> list[dict]:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d")
    filtered = [
        m for m in _fetch_rss()
        if start_dt <= datetime.strptime(m["iso"], "%Y-%m-%d") <= end_dt
    ]
    filtered.sort(key=lambda x: x["iso"], reverse=True)
    logger.info(f"Scraper: {len(filtered)} meetings in {start_date}→{end_date}")
    return filtered


def get_latest_meeting() -> dict | None:
    now      = datetime.now()
    meetings = get_meetings_in_range(
        (now - timedelta(days=90)).strftime("%Y-%m-%d"),
        now.strftime("%Y-%m-%d")
    )
    if meetings:
        logger.info(f"Scraper: Latest → {meetings[0]['iso']}")
        return meetings[0]
    logger.warning("Scraper: No meetings in last 90 days")
    return None
