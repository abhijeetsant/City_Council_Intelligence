"""
youtube_logic.py — YouTube Transcript Fetcher
San Ramon Council Intelligence Platform

Strategy (v2 — YouTube Data API):
  1. Resolve the channel handle (from env/config) to a channel ID via
     channels.list?forHandle=  — no hardcoded IDs anywhere.
  2. Search that channel for the meeting date via search.list.
  3. Try each candidate video ID until a valid transcript is found.

Why the old approach broke:
  The previous version scraped youtube.com/results with requests.get().
  YouTube tightened bot-detection and now returns a challenge page instead
  of real results, so the video-ID regex found nothing and every analysis
  silently failed before any transcript fetch was attempted.

Requirements:
  YOUTUBE_API_KEY   — a Google Cloud API key with YouTube Data API v3 enabled
  YOUTUBE_CHANNEL_HANDLE — the @handle of the city's YouTube channel
                           (default: SanRamonGovTV, readable from .env)

YouTube Data API v3 quota cost per analysis:
  channels.list  → 1 unit   (cached after first call per session)
  search.list    → 100 units
  Total: ~101 units per meeting (free tier = 10,000 units/day)
"""

import logging
import os
from datetime import datetime
from functools import lru_cache

import requests

logger = logging.getLogger(__name__)

YT_API_BASE   = "https://www.googleapis.com/youtube/v3"
MAX_CANDIDATES = 8
MIN_SEGMENTS   = 20  # fewer than this → likely wrong/short video, skip


# ── Date formatting ───────────────────────────────────────────────────────────

def _format_date_for_search(meeting_date: str) -> str:
    """
    Converts any date format to natural language for the search query.
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


# ── YouTube Data API v3 helpers ───────────────────────────────────────────────

def _get_api_key() -> str | None:
    """Reads YOUTUBE_API_KEY from environment or Streamlit secrets."""
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("YOUTUBE_API_KEY")
        except Exception:
            pass
    return key or None


def _get_channel_handle() -> str:
    """
    Reads the channel handle from env. Falls back to the San Ramon channel.
    Strip leading @ if present — the API wants the bare handle.
    """
    handle = os.getenv("YOUTUBE_CHANNEL_HANDLE", "SanRamonGovTV")
    return handle.lstrip("@")


@lru_cache(maxsize=8)
def _resolve_channel_id(handle: str, api_key: str) -> str | None:
    """
    Resolves a YouTube @handle to a channel ID via channels.list.
    Result is cached in-process so we only pay 1 API unit per session.

    e.g. "SanRamonGovTV" → "UCxxxxxxxxxxxxxxxxxxxxxxxx"
    """
    url = f"{YT_API_BASE}/channels"
    params = {
        "part":      "id",
        "forHandle": handle,
        "key":       api_key,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data  = resp.json()
        items = data.get("items", [])
        if not items:
            logger.error(f"YouTube: Handle '@{handle}' resolved to no channel. "
                         f"Check YOUTUBE_CHANNEL_HANDLE in .env.")
            return None
        channel_id = items[0]["id"]
        logger.info(f"YouTube: @{handle} → channel ID {channel_id}")
        return channel_id
    except Exception as e:
        logger.error(f"YouTube: channels.list failed for @{handle} — {e}")
        return None


def _search_channel(channel_id: str, date_str: str, api_key: str) -> list[str]:
    """
    Searches a specific channel for council meeting videos matching the date.
    Returns up to MAX_CANDIDATES deduplicated video IDs.

    Uses search.list (100 quota units) scoped to channelId so we only
    get videos from the official city channel — no irrelevant results.
    """
    natural = _format_date_for_search(date_str)

    # Two query variants: exact date phrase first, then broader fallback
    queries = [
        f"City Council Meeting {natural}",
        f"City Council {natural}",
        "City Council Meeting",   # fallback: latest meetings if date not in title
    ]

    seen, results = set(), []

    for query in queries:
        params = {
            "part":       "id",
            "channelId":  channel_id,
            "q":          query,
            "type":       "video",
            "order":      "date",
            "maxResults": MAX_CANDIDATES,
            "key":        api_key,
        }
        logger.info(f"YouTube: API search → channelId={channel_id} q='{query}'")
        try:
            resp = requests.get(f"{YT_API_BASE}/search", params=params, timeout=12)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                vid = item.get("id", {}).get("videoId")
                if vid and vid not in seen:
                    seen.add(vid)
                    results.append(vid)
                    if len(results) >= MAX_CANDIDATES:
                        logger.info(f"YouTube: Reached MAX_CANDIDATES={MAX_CANDIDATES}")
                        return results

        except Exception as e:
            logger.warning(f"YouTube: search.list failed for query '{query}' — {e}")
            continue

        # If we already have strong candidates from the first query, stop early
        if results:
            logger.info(f"YouTube: {len(results)} candidate(s) found, stopping search")
            break

    logger.info(f"YouTube: Total candidates: {results}")
    return results


# ── Public API ────────────────────────────────────────────────────────────────

def get_transcript(meeting_date: str) -> list[dict] | None:
    """
    Fetches the YouTube transcript for a given meeting date.

    Pipeline:
      1. Read YOUTUBE_API_KEY and YOUTUBE_CHANNEL_HANDLE from env
      2. Resolve @handle → channel ID (cached)
      3. Search that channel for the date
      4. Try each video ID until a valid transcript is found
      5. Return list of {text, start, duration} or None

    Falls back gracefully at each step with clear error messages.
    """
    logger.info(f"YouTube: Transcript fetch requested for '{meeting_date}'")

    api_key = _get_api_key()
    if not api_key:
        logger.error(
            "YouTube: YOUTUBE_API_KEY not set. "
            "Add it to .env or .streamlit/secrets.toml. "
            "Get a free key at https://console.cloud.google.com/ "
            "(enable YouTube Data API v3, free tier = 10,000 units/day)."
        )
        return None

    handle     = _get_channel_handle()
    channel_id = _resolve_channel_id(handle, api_key)
    if not channel_id:
        return None

    candidates = _search_channel(channel_id, meeting_date, api_key)
    if not candidates:
        logger.error(
            f"YouTube: No videos found in channel @{handle} for '{meeting_date}'. "
            "The video may not be uploaded yet (usually 1–2 days after the meeting)."
        )
        return None

    # Lazy import so app doesn't crash if package not installed
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        logger.error("YouTube: youtube-transcript-api not installed. Run: pip install youtube-transcript-api")
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
            exc_type = type(e).__name__
            logger.warning(f"YouTube: {video_id} failed ({exc_type}) — {e}")
            continue

    logger.error(
        f"YouTube: All {len(candidates)} candidate(s) exhausted. "
        f"Transcript not available for '{meeting_date}'. "
        "Auto-captions may not be generated yet — check back in 24 hours."
    )
    return None
