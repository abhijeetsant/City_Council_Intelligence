"""
youtube_logic.py — YouTube Transcript Fetcher
San Ramon Council Intelligence Platform

Searches YouTube for a City Council meeting by date and fetches
the auto-generated transcript via the YouTube Transcript API.

Limitation: YouTube search results are not guaranteed to match the
exact meeting date. Results are ordered by relevance, and the first
result is used. This works well for San Ramon because the city's
YouTube channel consistently uploads meetings within 24-48 hours.

Author: San Ramon Council Intelligence
"""

import re
import logging

import requests
from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)

YOUTUBE_SEARCH = "https://www.youtube.com/results?search_query="
HEADERS        = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _search_youtube(meeting_date: str) -> str | None:
    """
    Searches YouTube for a San Ramon City Council meeting by date.
    Returns the first matching video ID, or None.
    """
    query      = f"San Ramon City Council Meeting {meeting_date}"
    search_url = YOUTUBE_SEARCH + query.replace(" ", "+")
    logger.info(f"YouTube: Searching — {search_url}")

    try:
        resp     = requests.get(search_url, headers=HEADERS, timeout=10)
        video_ids = re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", resp.text)

        seen, unique = set(), []
        for vid in video_ids:
            if vid not in seen:
                seen.add(vid)
                unique.append(vid)

        if unique:
            logger.info(f"YouTube: {len(unique)} candidates → using {unique[0]}")
            return unique[0]

        logger.warning("YouTube: No video IDs found in search results")
        return None

    except Exception as e:
        logger.error(f"YouTube: Search failed — {e}", exc_info=True)
        return None


def get_transcript(meeting_date: str) -> list[dict] | None:
    """
    Fetches the YouTube transcript for a given meeting date.

    Strategy:
      1. Search YouTube for the meeting by date string
      2. Take the top result video ID
      3. Fetch transcript via YouTubeTranscriptApi

    Args:
        meeting_date: Date string in any format (e.g. "02/10/2026")

    Returns:
        List of segment dicts [{text, start, duration}], or None on failure.
    """
    logger.info(f"YouTube: Fetching transcript for {meeting_date}")

    video_id = _search_youtube(meeting_date)
    if not video_id:
        logger.error("YouTube: No video ID found — transcript fetch aborted")
        return None

    try:
        api      = YouTubeTranscriptApi()
        fetched  = api.fetch(video_id)
        segments = [
            {"text": e.text, "start": e.start, "duration": e.duration}
            for e in fetched
        ]
        logger.info(f"YouTube: Fetched {len(segments):,} segments for {video_id}")
        return segments

    except Exception as e:
        logger.error(f"YouTube: Transcript fetch failed ({video_id}) — {e}", exc_info=True)
        return None
