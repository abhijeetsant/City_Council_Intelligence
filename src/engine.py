"""
engine.py — LLM Summarization Engine
San Ramon Council Intelligence Platform
"""

import os
import logging

import streamlit as st
from dotenv import load_dotenv
from st_supabase_connection import SupabaseConnection

load_dotenv()
logger = logging.getLogger(__name__)

SUPPORTED_BACKENDS = ("groq_llama", "gemini", "trinity", "deepseek_r1")


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
            return f"**Rate Limit:** {label} is busy. Wait 60 seconds and retry."
        if "insufficient_quota" in msg or "billing" in msg:
            return f"**Quota Error:** {label} account has insufficient credits."
        if "decommissioned" in msg or "model_decommissioned" in msg:
            return f"**Model Error:** {label} model is decommissioned."
        if "invalid_api_key" in msg or "authentication" in msg:
            return f"**Auth Error:** Invalid {label} API key."
        logger.error(f"{label} error: {e}", exc_info=True)
        return f"**{label} Error:** {e}"


def build_prompt(meeting: dict, text_snippet: str) -> str:
    agenda_note   = f"Official agenda: {meeting['agenda_url']}\n"  if meeting.get("agenda_url")  else ""
    minutes_note  = f"Official minutes: {meeting['minutes_url']}\n" if meeting.get("minutes_url") else ""
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
    logger.info(f"Engine: Transcript = {len(full):,} chars")
    if len(full) > max_chars:
        logger.warning(f"Engine: Trimming to {max_chars:,} chars")
        return full[:max_chars]
    return full


class CouncilEngine:
    CONTEXT_LIMITS = {
        "gemini":      120_000,
        "groq_llama":  18_000,
        "trinity":     40_000,
        "deepseek_r1": 64_000,
    }

    def __init__(self, backend: str | None = None):
        self.backend = (backend or os.getenv("SUMMARIZER_BACKEND", "gemini")).lower()
        if self.backend not in SUPPORTED_BACKENDS:
            raise ValueError(f"Invalid backend '{self.backend}'. Choose from: {SUPPORTED_BACKENDS}")
        logger.info(f"Engine: Init '{self.backend}'")
        {
            "groq_llama":  self._init_groq,
            "gemini":      self._init_gemini,
            "trinity":     self._init_openrouter,
            "deepseek_r1": self._init_openrouter,
        }[self.backend]()

    # ── Groq ──────────────────────────────────────────────────────────────────
    def _init_groq(self):
        from groq import Groq
        key = _get_secret("GROQ_API_KEY")
        if not key:
            raise ValueError("GROQ_API_KEY not found")
        self._groq       = Groq(api_key=key)
        self._groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        logger.info(f"Engine: Groq ready ({self._groq_model})")

    def _summarize_groq(self, prompt: str) -> str:
        logger.info(f"Engine: Calling Groq ({self._groq_model})")
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

    # ── Gemini ─────────────────────────────────────────────────────────────────
    def _init_gemini(self):
        from google import genai
        from google.genai import types as genai_types
        key = _get_secret("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not found")
        # v1beta required for gemini-3-flash-preview
        self._gemini_client     = genai.Client(
            api_key=key,
            http_options={"api_version": "v1beta"}
        )
        self._gemini_model  = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        self._genai_types   = genai_types
        logger.info(f"Engine: Gemini ready ({self._gemini_model})")

    def _summarize_gemini(self, prompt: str) -> str:
        logger.info(f"Engine: Calling Gemini ({self._gemini_model})")
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

    # ── OpenRouter ─────────────────────────────────────────────────────────────
    def _init_openrouter(self):
        from openai import OpenAI
        key = _get_secret("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("OPENROUTER_API_KEY not found")
        self._or_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
            default_headers={"HTTP-Referer": "http://localhost:8501"},
        )
        self._or_model = {
            "trinity":     "arcee-ai/trinity-large-preview:free",
            "deepseek_r1": "deepseek/deepseek-r1-0528:free",
        }[self.backend]
        logger.info(f"Engine: OpenRouter ready ({self._or_model})")

    def _summarize_openrouter(self, prompt: str) -> str:
        logger.info(f"Engine: Calling OpenRouter ({self._or_model})")
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

    # ── Dispatcher ─────────────────────────────────────────────────────────────
    def generate_summary(self, meeting: dict, transcript: list[dict]) -> str:
        limit   = self.CONTEXT_LIMITS[self.backend]
        snippet = prepare_transcript(transcript, limit)
        prompt  = build_prompt(meeting, snippet)
        logger.info(f"Engine: Prompt={len(prompt):,} chars | backend={self.backend}")
        return {
            "groq_llama":  self._summarize_groq,
            "gemini":      self._summarize_gemini,
            "trinity":     self._summarize_openrouter,
            "deepseek_r1": self._summarize_openrouter,
        }[self.backend](prompt)

    @staticmethod
    def save_to_supabase(meeting: dict, summary: str, backend: str) -> bool:
        try:
            conn = st.connection("supabase", type=SupabaseConnection)
            conn.table("council_reports").insert({
                "meeting_date": meeting["date"],
                "title":        meeting.get("name", "City Council Meeting"),
                "summary":      summary,
                "backend_used": backend,
                "agenda_url":   meeting.get("agenda_url"),
                "minutes_url":  meeting.get("minutes_url"),
                "webcast_url":  meeting.get("webcast_url"),
            }).execute()
            logger.info(f"Engine: Saved {meeting['date']} to Supabase")
            return True
        except Exception as e:
            logger.error(f"Engine: Supabase save failed — {e}", exc_info=True)
            return False
