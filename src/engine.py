"""
engine.py — LLM Summarization Engine
San Ramon Council Intelligence Platform

Model cascade strategy:
  - Every backend tries a priority-ordered list of models
  - On 404 / model-not-found / rate-limit → automatically tries next model
  - Final fallback returns a clear user-facing error (never a silent blank)

OpenRouter free models are volatile by design — cascades are mandatory.
"""

import os
import logging
import time

import streamlit as st
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SUPPORTED_BACKENDS = ("groq_llama", "gemini", "trinity", "deepseek_r1")

# ── Model cascade lists (tried in order, first success wins) ──────────────────
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
]

GEMINI_MODELS = [
    "gemini-3-flash-preview",
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.0-flash",
]

# DeepSeek: R1 reasoning variants first, fall back to V3 chat (stable workhorse)
DEEPSEEK_MODELS = [
    "deepseek/deepseek-r1:free",
    "deepseek/deepseek-r1-0528:free",
    "deepseek/deepseek-chat:free",
    "deepseek/deepseek-v3-base:free",
]

# Trinity: Arcee first, then strong free OpenRouter alternatives
TRINITY_MODELS = [
    "arcee-ai/trinity-large-preview:free",
    "mistralai/mistral-small-3.2-24b-instruct:free",
    "meta-llama/llama-4-scout:free",
    "google/gemma-3-27b-it:free",
]

_MODEL_GONE_SIGNALS = (
    "no endpoints found",
    "404",
    "model not found",
    "decommissioned",
    "model_decommissioned",
    "not available",
    "no provider",
)
_RATE_LIMIT_SIGNALS = ("rate_limit", "429", "too many requests")


def _get_secret(key: str) -> str | None:
    value = os.getenv(key)
    if not value:
        try:
            value = st.secrets.get(key)
        except Exception:
            pass
    return value


def _is_model_gone(msg: str) -> bool:
    return any(s in msg for s in _MODEL_GONE_SIGNALS)


def _is_rate_limit(msg: str) -> bool:
    return any(s in msg for s in _RATE_LIMIT_SIGNALS)


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
    logger.info(f"Engine: Transcript = {len(full):,} chars")
    if len(full) > max_chars:
        logger.warning(f"Engine: Trimming to {max_chars:,} chars")
        return full[:max_chars]
    return full


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
        self._groq = Groq(api_key=key)
        logger.info(f"Engine: Groq ready (cascade: {GROQ_MODELS})")

    def _summarize_groq(self, prompt: str) -> str:
        system = "You are a senior political analyst. Report facts only. Use clean Markdown with ## headers and bullet points."
        for model in GROQ_MODELS:
            logger.info(f"Engine: Trying Groq model '{model}'")
            try:
                result = self._groq.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=2000,
                ).choices[0].message.content
                logger.info(f"Engine: Groq '{model}' succeeded")
                return result
            except Exception as e:
                msg = str(e).lower()
                if _is_rate_limit(msg):
                    logger.warning(f"Engine: Groq '{model}' rate limited — waiting 5s")
                    time.sleep(5)
                elif _is_model_gone(msg):
                    logger.warning(f"Engine: Groq '{model}' unavailable — trying next")
                else:
                    logger.error(f"Engine: Groq '{model}' error: {e}")
                continue
        return "**Groq Error:** All Groq models currently unavailable. Please switch to Gemini."

    # ── Gemini ─────────────────────────────────────────────────────────────────
    def _init_gemini(self):
        from google import genai
        key = _get_secret("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not found")
        self._gemini_client = genai.Client(
            api_key=key,
            http_options={"api_version": "v1beta"},
        )
        logger.info(f"Engine: Gemini ready (cascade: {GEMINI_MODELS})")

    def _summarize_gemini(self, prompt: str) -> str:
        system = (
            "You are a concise civic reporter. Start immediately with ## Executive Summary. "
            "Use clean Markdown with ## section headers and bullet points. No preamble."
        )
        full_prompt = f"{system}\n\n{prompt}"
        for model in GEMINI_MODELS:
            logger.info(f"Engine: Trying Gemini model '{model}'")
            try:
                result = self._gemini_client.models.generate_content(
                    model=model,
                    contents=full_prompt,
                ).text
                logger.info(f"Engine: Gemini '{model}' succeeded")
                return result
            except Exception as e:
                msg = str(e).lower()
                if _is_rate_limit(msg):
                    logger.warning(f"Engine: Gemini '{model}' rate limited — waiting 5s")
                    time.sleep(5)
                elif "503" in msg or "unavailable" in msg or _is_model_gone(msg):
                    logger.warning(f"Engine: Gemini '{model}' unavailable — trying next")
                else:
                    logger.error(f"Engine: Gemini '{model}' error: {e}")
                continue
        return "**Gemini Error:** All Gemini models currently unavailable. Please switch to Llama."

    # ── OpenRouter (Trinity + DeepSeek) ────────────────────────────────────────
    def _init_openrouter(self):
        from openai import OpenAI
        key = _get_secret("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("OPENROUTER_API_KEY not found")
        self._or_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
            default_headers={
                "HTTP-Referer": "https://abhijeetsant-city-council-intelligence.streamlit.app",
                "X-Title":      "San Ramon Council Intelligence",
            },
        )
        self._or_cascade = {
            "trinity":     TRINITY_MODELS,
            "deepseek_r1": DEEPSEEK_MODELS,
        }[self.backend]
        logger.info(f"Engine: OpenRouter ready | backend={self.backend} | cascade={self._or_cascade}")

    def _summarize_openrouter(self, prompt: str) -> str:
        system = (
            "You are an expert City Clerk. Produce executive-level civic reports in clean Markdown. "
            "Start with ## Executive Summary. No preamble."
        )
        for model in self._or_cascade:
            logger.info(f"Engine: Trying OpenRouter model '{model}'")
            try:
                result = self._or_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": prompt},
                    ],
                    temperature=0.1,
                ).choices[0].message.content

                if not result or not result.strip():
                    logger.warning(f"Engine: OpenRouter '{model}' returned empty content — trying next")
                    continue

                logger.info(f"Engine: OpenRouter '{model}' succeeded ({len(result):,} chars)")
                return result

            except Exception as e:
                msg = str(e).lower()
                if _is_model_gone(msg):
                    logger.warning(f"Engine: OpenRouter '{model}' gone (404) — trying next in cascade")
                elif _is_rate_limit(msg):
                    logger.warning(f"Engine: OpenRouter '{model}' rate limited — waiting 5s")
                    time.sleep(5)
                elif "insufficient_quota" in msg or "billing" in msg:
                    return "**Quota Error:** OpenRouter account has insufficient credits. Add credits at openrouter.ai."
                elif "invalid_api_key" in msg or "authentication" in msg:
                    return "**Auth Error:** Invalid OPENROUTER_API_KEY. Check your Streamlit secrets."
                else:
                    logger.error(f"Engine: OpenRouter '{model}' unexpected error: {e}")
                continue

        backend_label = "DeepSeek R1" if self.backend == "deepseek_r1" else "Trinity"
        tried = " → ".join(self._or_cascade)
        return (
            f"**{backend_label} — All models unavailable.**\n\n"
            f"Cascade tried: {tried}\n\n"
            f"OpenRouter free endpoints are volatile. Please switch to **Gemini** or **Llama** instead."
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
            from st_supabase_connection import SupabaseConnection
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
        except ImportError:
            logger.debug("Engine: st-supabase-connection not installed — skipping save")
            return False
        except Exception as e:
            err = str(e).lower()
            if any(x in err for x in ("nodename", "servname", "connect", "network", "dns", "timeout")):
                logger.debug("Engine: Supabase unreachable (no VPN?) — in-memory only")
            else:
                logger.error(f"Engine: Supabase save failed — {e}", exc_info=True)
            return False
