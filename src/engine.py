"""
engine.py — LLM Summarization Engine
San Ramon Council Intelligence Platform

Supabase persistence uses supabase-py create_client() directly.
No st-supabase-connection wrapper. No st.connection(). No secrets.toml required.
Credentials read from env vars (SUPABASE_URL, SUPABASE_KEY) with Streamlit
secrets as fallback. Works in any Python context.
"""

import os
import logging

import streamlit as st
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SUPPORTED_BACKENDS = ("groq_llama", "gemini", "trinity", "deepseek_r1")


# ── Supabase ──────────────────────────────────────────────────────────────────

def _get_supabase_client():
    """
    Returns a configured supabase-py Client, or None if unconfigured.
    Lazy-imports supabase so missing package doesn't crash the module.
    Reads SUPABASE_URL + SUPABASE_KEY from env vars, then st.secrets fallback.
    """
    try:
        from supabase import create_client
    except ImportError:
        logger.warning("Supabase: package not installed — pip install supabase")
        return None

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        try:
            url = url or st.secrets.get("SUPABASE_URL")
            key = key or st.secrets.get("SUPABASE_KEY")
        except Exception:
            pass

    if not url or not key:
        logger.warning("Supabase: SUPABASE_URL / SUPABASE_KEY not set — persistence disabled")
        return None

    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Supabase: create_client failed — {e}")
        return None


def save_to_supabase(meeting: dict, summary: str, backend: str) -> tuple[bool, str]:
    """
    Inserts one council report row. Returns (ok, message) so callers can
    surface the exact result in the UI — no more silent data loss.
    """
    client = _get_supabase_client()
    if client is None:
        return False, "Supabase not configured (set SUPABASE_URL + SUPABASE_KEY)"

    try:
        client.table("council_reports").insert({
            "meeting_date": meeting["date"],
            "title":        meeting.get("name", "City Council Meeting"),
            "summary":      summary,
            "backend_used": backend,
            "agenda_url":   meeting.get("agenda_url"),
            "minutes_url":  meeting.get("minutes_url"),
            "webcast_url":  meeting.get("webcast_url"),
        }).execute()
        logger.info(f"Supabase: saved {meeting['date']}")
        return True, "ok"
    except Exception as e:
        logger.error(f"Supabase: save failed — {e}", exc_info=True)
        return False, str(e)


def load_from_supabase() -> list[dict]:
    """
    Fetches all council_reports rows, newest first.
    Returns [] if Supabase is not configured or the query fails.
    """
    client = _get_supabase_client()
    if client is None:
        return []

    try:
        result = client.table("council_reports").select("*").order("created_at", desc=True).execute()
        rows = result.data or []
        logger.info(f"Supabase: loaded {len(rows)} reports")
        return rows
    except Exception as e:
        logger.error(f"Supabase: load failed — {e}", exc_info=True)
        return []


# ── LLM helpers ───────────────────────────────────────────────────────────────

def _get_secret(key: str) -> str | None:
    value = os.getenv(key)
    if not value:
        try:
            value = st.secrets.get(key)
        except Exception:
            pass
    return value


def _call_llm(client_fn, label: str) -> str:
    try:
        return client_fn()
    except Exception as e:
        msg = str(e).lower()
        if "rate_limit" in msg or "429" in msg:
            logger.warning(f"{label}: rate limit hit")
            return f"**Rate Limit:** {label} is busy. Wait 60 s and retry."
        if "insufficient_quota" in msg or "billing" in msg:
            return f"**Quota Error:** {label} has insufficient credits."
        if "decommissioned" in msg or "model_decommissioned" in msg:
            return f"**Model Error:** {label} model is decommissioned."
        if "invalid_api_key" in msg or "authentication" in msg:
            return f"**Auth Error:** Invalid {label} API key."
        logger.error(f"{label} error: {e}", exc_info=True)
        return f"**{label} Error:** {e}"


def build_prompt(meeting: dict, text_snippet: str) -> str:
    agenda_note  = f"Official agenda: {meeting['agenda_url']}\n"  if meeting.get("agenda_url")  else ""
    minutes_note = f"Official minutes: {meeting['minutes_url']}\n" if meeting.get("minutes_url") else ""
    return (
        f"You are a senior municipal reporter covering a San Ramon City Council meeting on {meeting['date']}.\n"
        f"{agenda_note}{minutes_note}\n"
        f"Produce a structured civic intelligence report with EXACTLY these sections:\n\n"
        f"## Executive Summary\n2-3 sentences on the meeting's most significant outcomes.\n\n"
        f"## Key Votes & Decisions\nBullet list of every formal vote. Include vote counts if mentioned.\n\n"
        f"## Fiscal Impact\nSpending, contracts, or budget commitments. Write 'None discussed' if absent.\n\n"
        f"## Public Commentary\nNotable themes from public comment. Who spoke and on what topics.\n\n"
        f"## Next Steps & Deadlines\nFollow-up actions or future agenda items mentioned.\n\n"
        f"RULES: Start immediately with ## Executive Summary. Facts only. No preamble.\n\n"
        f"TRANSCRIPT:\n{text_snippet}"
    )


def prepare_transcript(transcript: list[dict], max_chars: int) -> str:
    full = " ".join(t["text"] for t in transcript)
    logger.info(f"Engine: transcript = {len(full):,} chars")
    if len(full) > max_chars:
        logger.warning(f"Engine: trimming to {max_chars:,} chars")
        return full[:max_chars]
    return full


# ── Engine class ──────────────────────────────────────────────────────────────

class CouncilEngine:
    CONTEXT_LIMITS = {
        "gemini":      120_000,
        "groq_llama":   18_000,
        "trinity":      40_000,
        "deepseek_r1":  64_000,
    }

    def __init__(self, backend: str | None = None):
        self.backend = (backend or os.getenv("SUMMARIZER_BACKEND", "gemini")).lower()
        if self.backend not in SUPPORTED_BACKENDS:
            raise ValueError(f"Invalid backend '{self.backend}'. Choose from: {SUPPORTED_BACKENDS}")
        logger.info(f"Engine: init '{self.backend}'")
        {
            "groq_llama":  self._init_groq,
            "gemini":      self._init_gemini,
            "trinity":     self._init_openrouter,
            "deepseek_r1": self._init_openrouter,
        }[self.backend]()

    def _init_groq(self):
        from groq import Groq
        key = _get_secret("GROQ_API_KEY")
        if not key:
            raise ValueError("GROQ_API_KEY not set")
        self._groq       = Groq(api_key=key)
        self._groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    def _summarize_groq(self, prompt: str) -> str:
        return _call_llm(
            lambda: self._groq.chat.completions.create(
                model=self._groq_model,
                messages=[
                    {"role": "system", "content": "You are a senior political analyst. Report facts only. Use clean Markdown with ## headers and bullet points."},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2000,
            ).choices[0].message.content,
            "Groq"
        )

    def _init_gemini(self):
        from google import genai
        from google.genai import types as genai_types
        key = _get_secret("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not set")
        self._gemini_client = genai.Client(
            api_key=key,
            http_options={"api_version": "v1beta"},
        )
        self._gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-04-17")
        self._genai_types  = genai_types

    def _summarize_gemini(self, prompt: str) -> str:
        system = (
            "You are a concise civic reporter. Start immediately with ## Executive Summary. "
            "Use clean Markdown with ## section headers and bullet points. No preamble."
        )
        return _call_llm(
            lambda: self._gemini_client.models.generate_content(
                model=self._gemini_model,
                contents=f"{system}\n\n{prompt}",
            ).text,
            "Gemini"
        )

    def _init_openrouter(self):
        from openai import OpenAI
        key = _get_secret("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("OPENROUTER_API_KEY not set")
        self._or_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
            default_headers={"HTTP-Referer": "http://localhost:8501"},
        )
        self._or_model = {
            "trinity":     "arcee-ai/trinity-large-preview:free",
            "deepseek_r1": "deepseek/deepseek-r1-0528:free",
        }[self.backend]

    def _summarize_openrouter(self, prompt: str) -> str:
        return _call_llm(
            lambda: self._or_client.chat.completions.create(
                model=self._or_model,
                messages=[
                    {"role": "system", "content": "You are an expert City Clerk. Produce executive-level civic reports in clean Markdown. Start with ## Executive Summary. No preamble."},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.1,
            ).choices[0].message.content,
            "OpenRouter"
        )

    def generate_summary(self, meeting: dict, transcript: list[dict]) -> str:
        limit   = self.CONTEXT_LIMITS[self.backend]
        snippet = prepare_transcript(transcript, limit)
        prompt  = build_prompt(meeting, snippet)
        logger.info(f"Engine: prompt={len(prompt):,} chars | backend={self.backend}")
        return {
            "groq_llama":  self._summarize_groq,
            "gemini":      self._summarize_gemini,
            "trinity":     self._summarize_openrouter,
            "deepseek_r1": self._summarize_openrouter,
        }[self.backend](prompt)
