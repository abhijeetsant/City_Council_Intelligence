"""
engine.py — LLM Summarization Engine
San Ramon Council Intelligence Platform

Rate-limit hedging: each backend has a prioritised model cascade.
When the primary model hits a rate/quota/404 error, the engine
silently retries with the next model in that backend's list.
The user's backend selection (Gemini, Groq, etc.) never changes.

Model cascades:
  gemini     → gemini-3-flash-preview → gemini-2.5-flash → gemini-2.0-flash
  groq_llama → llama-3.3-70b-versatile → llama-3.1-70b-versatile → llama-3.1-8b-instant
  trinity    → arcee-ai/trinity-large-preview:free → mistralai/mistral-7b-instruct:free
  deepseek_r1→ deepseek/deepseek-r1-0528:free → deepseek/deepseek-chat:free
"""

import os
import logging

import streamlit as st
from dotenv import load_dotenv
from st_supabase_connection import SupabaseConnection

load_dotenv()
logger = logging.getLogger(__name__)

SUPPORTED_BACKENDS = ("groq_llama", "gemini", "trinity", "deepseek_r1")

# Per-backend model cascades — primary first, fallbacks in order.
# Only models within the same provider/key are listed so no new secrets
# are required. Override the primary via env vars as before.
MODEL_CASCADES = {
    "gemini": [
        "gemini-3-flash-preview",    # primary — highest RPD on free tier
        "gemini-2.5-flash",          # fallback 1
        "gemini-2.0-flash",          # fallback 2
    ],
    "groq_llama": [
        "llama-3.3-70b-versatile",   # primary
        "llama-3.1-70b-versatile",   # fallback 1
        "llama-3.1-8b-instant",      # fallback 2 — smallest, highest rate limit
    ],
    "trinity": [
        "arcee-ai/trinity-large-preview:free",   # primary
        "mistralai/mistral-7b-instruct:free",    # fallback
    ],
    "deepseek_r1": [
        "deepseek/deepseek-r1-0528:free",        # primary
        "deepseek/deepseek-chat:free",           # fallback
    ],
}

# Errors that should trigger a model-level fallback
_FALLBACK_TRIGGERS = (
    "rate_limit", "429", "quota", "insufficient_quota", "billing",
    "decommissioned", "model_decommissioned", "not_found", "404",
    "overloaded", "503", "502",
)


def _get_secret(key: str) -> str | None:
    value = os.getenv(key)
    if not value:
        try:
            value = st.secrets.get(key)
        except Exception:
            pass
    return value


def _is_fallback_error(msg: str) -> bool:
    msg = msg.lower()
    return any(trigger in msg for trigger in _FALLBACK_TRIGGERS)


def _call_llm(client_fn, label: str) -> tuple[str | None, bool]:
    """
    Returns (result, should_fallback).
    should_fallback=True → rate/quota/model error, try next model in cascade.
    should_fallback=False + result=None → hard error, stop.
    """
    try:
        return client_fn(), False
    except Exception as e:
        msg = str(e)
        if _is_fallback_error(msg):
            logger.warning(f"{label}: cascade trigger — {msg[:120]}")
            return None, True
        logger.error(f"{label} error: {e}", exc_info=True)
        return f"**{label} Error:** {e}", False


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

        # Allow env override of the primary model (preserves existing behaviour)
        _env_overrides = {
            "gemini":      os.getenv("GEMINI_MODEL"),
            "groq_llama":  os.getenv("GROQ_MODEL"),
        }
        if _env_overrides.get(self.backend):
            override = _env_overrides[self.backend]
            cascade  = MODEL_CASCADES[self.backend]
            # Put the override first; keep the rest as fallbacks
            self._cascade = [override] + [m for m in cascade if m != override]
            logger.info(f"Engine: Env override '{override}' placed at head of cascade")
        else:
            self._cascade = list(MODEL_CASCADES[self.backend])

        logger.info(f"Engine: Init backend='{self.backend}' cascade={self._cascade}")
        self._init_backend()

    # ── Backend initialisation ────────────────────────────────────────────────

    def _init_backend(self):
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
            raise ValueError("GROQ_API_KEY not found")
        self._groq = Groq(api_key=key)
        logger.info("Engine: Groq ready")

    def _init_gemini(self):
        from google import genai
        key = _get_secret("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not found")
        self._gemini_client = genai.Client(
            api_key=key,
            http_options={"api_version": "v1beta"}
        )
        logger.info("Engine: Gemini ready")

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
        logger.info("Engine: OpenRouter ready")

    # ── Per-model call helpers ────────────────────────────────────────────────

    def _call_groq(self, model: str, prompt: str) -> tuple[str | None, bool]:
        logger.info(f"Engine: Groq → {model}")
        return _call_llm(
            lambda: self._groq.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a senior political analyst. Report facts only. Use clean Markdown with ## headers and bullet points."},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2000,
            ).choices[0].message.content,
            f"Groq/{model}"
        )

    def _call_gemini(self, model: str, prompt: str) -> tuple[str | None, bool]:
        logger.info(f"Engine: Gemini → {model}")
        system = (
            "You are a concise civic reporter. Start immediately with ## Executive Summary. "
            "Use clean Markdown with ## section headers and bullet points. No preamble."
        )
        return _call_llm(
            lambda: self._gemini_client.models.generate_content(
                model=model,
                contents=f"{system}\n\n{prompt}",
            ).text,
            f"Gemini/{model}"
        )

    def _call_openrouter(self, model: str, prompt: str) -> tuple[str | None, bool]:
        logger.info(f"Engine: OpenRouter → {model}")
        return _call_llm(
            lambda: self._or_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are an expert City Clerk. Produce executive-level civic reports in clean Markdown. Start with ## Executive Summary. No preamble."},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.1,
            ).choices[0].message.content,
            f"OpenRouter/{model}"
        )

    def _call_model(self, model: str, prompt: str) -> tuple[str | None, bool]:
        """Dispatch to the right API for a given model string."""
        if self.backend == "groq_llama":
            return self._call_groq(model, prompt)
        elif self.backend == "gemini":
            return self._call_gemini(model, prompt)
        else:
            return self._call_openrouter(model, prompt)

    # ── Main dispatcher with model cascade ───────────────────────────────────

    def generate_summary(self, meeting: dict, transcript: list[dict]) -> str:
        """
        Runs the model cascade for the user's selected backend.
        On a rate-limit / quota / 404 error, silently steps down to the
        next model in the cascade. The backend (provider) never changes.
        """
        limit   = self.CONTEXT_LIMITS[self.backend]
        snippet = prepare_transcript(transcript, limit)
        prompt  = build_prompt(meeting, snippet)

        logger.info(f"Engine: Starting cascade for backend='{self.backend}' | {len(self._cascade)} model(s)")

        for i, model in enumerate(self._cascade):
            is_primary = (i == 0)
            result, should_fallback = self._call_model(model, prompt)

            if not should_fallback:
                # Success or hard error — either way, return
                if result and not is_primary:
                    logger.info(f"Engine: Cascade succeeded on model '{model}' (step {i+1})")
                    result = f"> *Generated with **{model}** (rate-limit fallback from primary)*\n\n{result}"
                return result

            # Fallback triggered
            if i + 1 < len(self._cascade):
                logger.warning(
                    f"Engine: '{model}' rate/quota limited → "
                    f"trying '{self._cascade[i+1]}'"
                )
            else:
                logger.error(f"Engine: All models in cascade exhausted for backend='{self.backend}'")

        return (
            f"**{self.backend.title()} Temporarily Unavailable**\n\n"
            f"All models in the {self.backend} cascade are currently rate-limited:\n"
            + "\n".join(f"- `{m}`" for m in self._cascade) +
            "\n\n**What to do:**\n"
            "- Groq resets hourly · Gemini resets daily at midnight PT\n"
            "- Switch to a different backend in the sidebar while waiting"
        )

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
