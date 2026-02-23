"""
youtube_logic.py — YouTube Transcript Fetcher
San Ramon Council Intelligence Platform

Strategy: search YouTube for the meeting by natural-language date,
try up to MAX_CANDIDATES video IDs, return first valid transcript.
"""

import re
import logging
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

YOUTUBE_SEARCH = "https://www.youtube.com/results?search_query="
HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
MAX_CANDIDATES = 8
MIN_SEGMENTS   = 20   # fewer than this → likely wrong video


def _format_date_for_search(meeting_date: str) -> str:
    """
    Converts any date format to natural language for YouTube search.
    "02/10/2026" → "February 10 2026"
    "2026-02-10" → "February 10 2026"
    """
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(meeting_date.strip(), fmt).strftime("%B %d %Y")
        except ValueError:
            continue
    logger.warning(f"YouTube: Could not reformat date '{meeting_date}' — using as-is")
    return meeting_date


def _search_youtube(date_str: str) -> list[str]:
    """
    Searches YouTube and returns up to MAX_CANDIDATES deduplicated video IDs.
    Tries two query variants for maximum recall.
    """
    natural = _format_date_for_search(date_str)
    safe    = natural.replace(" ", "+")

    queries = [
        f"San+Ramon+City+Council+Meeting+{safe}",
        f"\"San+Ramon\"+Council+Meeting+{safe}",
        f"City+of+San+Ramon+Council+{safe}",
    ]

    seen, results = set(), []

    for query in queries:
        url = YOUTUBE_SEARCH + query
        logger.info(f"YouTube: Searching → {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            resp.raise_for_status()
            for vid in re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", resp.text):
                if vid not in seen:
                    seen.add(vid)
                    results.append(vid)
                    if len(results) >= MAX_CANDIDATES:
                        logger.info(f"YouTube: Hit MAX_CANDIDATES={MAX_CANDIDATES}, stopping")
                        return results
        except Exception as e:
            logger.warning(f"YouTube: Search query failed — {e}")
            continue

    logger.info(f"YouTube: Found {len(results)} candidate(s): {results}")
    return results


def get_transcript(meeting_date: str) -> list[dict] | None:
    """
    Fetches the YouTube transcript for a given meeting date.

    1. Reformats date to natural language
    2. Searches YouTube with 3 query variants
    3. Tries each video ID until a valid transcript is found
    4. Returns list of {text, start, duration} or None

    BUG-07 FIX: catches public exception classes, not internal _errors module.
    """
    logger.info(f"YouTube: Transcript fetch requested for '{meeting_date}'")

    candidates = _search_youtube(meeting_date)
    if not candidates:
        logger.error("YouTube: No video candidates found in search")
        return None

    # Lazy import so app doesn't crash if package not installed
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        logger.error("YouTube: youtube-transcript-api not installed")
        return None

    api = YouTubeTranscriptApi()

    for video_id in candidates:
        logger.info(f"YouTube: Attempting transcript for {video_id}")
        try:
            fetched  = api.fetch(video_id)
            segments = [
                {"text": e.text, "start": e.start, "duration": e.duration}
                for e in fetched
                if e.text and e.text.strip()
            ]

            if len(segments) < MIN_SEGMENTS:
                logger.warning(
                    f"YouTube: {video_id} only has {len(segments)} segments "
                    f"(min={MIN_SEGMENTS}) — likely wrong video, skipping"
                )
                continue

            logger.info(f"YouTube: ✓ {len(segments):,} segments from {video_id}")
            return segments

        except Exception as e:
            # BUG-07 FIX: catch all exceptions, log exact type for debugging
            exc_type = type(e).__name__
            logger.warning(f"YouTube: {video_id} failed ({exc_type}) — {e}")
            continue

    logger.error(
        f"YouTube: All {len(candidates)} candidate(s) exhausted. "
        f"Transcript not available for '{meeting_date}'."
    )
    return None
