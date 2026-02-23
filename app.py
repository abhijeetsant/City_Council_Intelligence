"""
app.py — San Ramon Council Intelligence Platform
Entry point for the Streamlit web application.

All 18 original bugs from engineering audit addressed, plus 6 additional:
  BUG-01/02: Gemini HttpOptions fix (in engine.py)
  BUG-03: Refresh button now wired up
  BUG-04: load_archive cached with ttl=60, cleared after saves
  BUG-05: widget keys sanitized (no hyphens)
  BUG-06: scraper _abs() returns None not '' (in scraper.py)
  BUG-07: YouTube exception handling (in youtube_logic.py)
  BUG-08: Transcript word-boundary truncation (in engine.py) — actually applied now
  BUG-09: backend_radio index with safe fallback
  BUG-10: st.rerun() called OUTSIDE st.status context
  BUG-11: rouge-score removed from requirements (in requirements.txt)
  BUG-12: All packages version-pinned (in requirements.txt)
  BUG-13: README model name corrected
  BUG-14: masthead rendered after sidebar (correct state)
  BUG-15: Scraper retry logic (in scraper.py)
  BUG-16: html.escape() on all user-facing injections
  BUG-17: .gitignore added
  BUG-18: Lazy Supabase import (in engine.py)
  BUG-A:  Report summary invisible on dark bg — fixed by rendering markdown
          as inline HTML inside the report shell div (report-content class)
  BUG-B:  Stats bar (Reports/Engines/Latest) removed from Archived Reports
  BUG-C:  `import re` moved to top-level imports (was after first use)
  BUG-D:  rouge-score removed from requirements.txt (was still present)
  BUG-E:  requirements.txt version pins actually applied
  BUG-F:  evaluator.py model fixed to match engine.py; Date always set
  BUG-G:  rfl CSS class defined (was used in res_links but never styled)
  BUG-H:  "Archived Reports" renamed to "Recently Viewed"
  BUG-I:  Sidebar AI engine radio buttons now visible — fixed overly broad
          [data-baseweb="radio"] { display:none } that hid entire option rows
          in Streamlit ≥1.35; now only hides the radio circle input dot.
          Also removed nuclear wildcard sidebar * color override that fought
          all specific color declarations via !important specificity ties."""

import html
import logging
import os
import re
from datetime import datetime as _dt

import streamlit as st
import streamlit.components.v1 as st_components
from dotenv import load_dotenv

from src.scraper import get_latest_meeting, get_meetings_in_range
from src.youtube_logic import get_transcript
from src.engine import CouncilEngine, save_to_supabase, load_from_supabase

load_dotenv()
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/council_app.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)
logger.info("=" * 60)
logger.info("Platform starting")
logger.info("=" * 60)

st.set_page_config(
    page_title="San Ramon Council Intelligence",
    layout="wide",
    page_icon="🏛️",
    initial_sidebar_state="expanded",
)

# ── Force sidebar open ────────────────────────────────────────────────────────
# Streamlit persists sidebar collapsed state in JS component state.
# initial_sidebar_state="expanded" only applies on the very first ever load.
# After a user collapses it, the state is locked collapsed across reloads.
# Fix: inject JS that clicks the expand button (data-testid="stExpandSidebarButton")
# if it exists, which only renders when the sidebar IS collapsed.
# Uses a short polling loop since Streamlit renders asynchronously.
st_components.html(
    """
    <script>
    (function() {
        function tryExpand(attempts) {
            var btn = window.parent.document.querySelector(
                '[data-testid="stExpandSidebarButton"]'
            );
            if (btn) {
                btn.click();
                return;
            }
            if (attempts > 0) {
                setTimeout(function() { tryExpand(attempts - 1); }, 150);
            }
        }
        // Give Streamlit 200ms to finish its first render, then try up to 10 times
        setTimeout(function() { tryExpand(10); }, 200);
    })();
    </script>
    """,
    height=0,
)

# ── Backend registry ──────────────────────────────────────────────────────────
BACKENDS = {
    "gemini": {
        "label": "Gemini 3 Flash",   "model": "gemini-3-flash-preview",
        "env_key": "GEMINI_API_KEY", "icon": "◆", "ctx": "120k", "speed": "Recommended",
    },
    "groq_llama": {
        "label": "Llama 3.3 70B",    "model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",   "icon": "▣", "ctx": "18k",  "speed": "Fastest",
    },
    "trinity": {
        "label": "Trinity Large",    "model": "arcee-ai/trinity-large-preview:free",
        "env_key": "OPENROUTER_API_KEY", "icon": "◈", "ctx": "40k", "speed": "Moderate",
    },
    "deepseek_r1": {
        "label": "DeepSeek R1",      "model": "deepseek/deepseek-r1-0528:free",
        "env_key": "OPENROUTER_API_KEY", "icon": "◎", "ctx": "64k", "speed": "Thorough",
    },
}

BACKEND_KEYS = list(BACKENDS.keys())


def _safe_key(raw: str) -> str:
    """BUG-05 FIX: sanitize widget keys to alphanumeric + underscores only."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", str(raw))


# ══════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=Source+Serif+4:wght@300;400;600&family=IBM+Plex+Mono:wght@300;400;500&display=swap');

:root {
    --ink:       #1a1f2e;
    --ink-mid:   #4a5568;
    --ink-light: #718096;
    --ink-faint: #a0aec0;
    --paper:     #faf9f6;
    --paper-1:   #f5f2ec;
    --paper-2:   #eeeadf;
    --white:     #ffffff;
    --gold:      #b07d10;
    --gold-dk:   #92610a;
    --gold-lt:   #f5ecd4;
    --gold-pale: #fdf8ed;
    --teal:      #0f6b6b;
    --teal-lt:   #e8f5f5;
    --green:     #1a5c2e;
    --green-lt:  #e8f5ec;
    --rad:       7px;
    --font-d:    'Cormorant Garamond', Georgia, serif;
    --font-b:    'Source Serif 4', Georgia, serif;
    --font-m:    'IBM Plex Mono', monospace;
    --s1: 0 1px 3px rgba(26,31,46,.07);
    --s2: 0 4px 12px rgba(26,31,46,.09), 0 2px 4px rgba(26,31,46,.06);
}
*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] {
    font-family: var(--font-b); background: var(--paper); color: var(--ink);
    -webkit-font-smoothing: antialiased;
}
.stApp { background: var(--paper); }
#MainMenu, footer { visibility: hidden; }
header { visibility: visible !important; background: transparent !important; }
hr { border-color: var(--paper-2) !important; margin: 14px 0 !important; }
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: var(--paper-1); }
::-webkit-scrollbar-thumb { background: var(--paper-2); border-radius: 2px; }

/* ── SIDEBAR ── */
[data-testid="stSidebar"] {
    background: #12161f !important;
    min-width: 270px !important;
    max-width: 270px !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding: 0 !important;
}

.sb-brand { padding: 22px 18px 16px; border-bottom: 1px solid #1e2535; margin-bottom: 4px; }
.sb-brand-title { font-family: var(--font-d) !important; font-size: 1.1rem; color: #f0ece4 !important; font-weight: 600; }
.sb-brand-sub { font-family: var(--font-m) !important; font-size: 0.57rem; color: var(--gold) !important; letter-spacing: 2px; text-transform: uppercase; margin-top: 3px; }
.sb-label { font-family: var(--font-m) !important; font-size: 0.55rem !important; color: #3d4f6a !important; letter-spacing: 2.5px; text-transform: uppercase; padding: 14px 18px 6px; display: block; }

/* ── Sidebar engine selector — st.radio styled as nav rows ── */
/* Hide the radio circle dot; keep the full label row clickable */
[data-testid="stSidebar"] [data-testid="stRadio"] [data-baseweb="radio"] > div:first-child {
    display: none !important;
}
/* Each radio option row */
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    display: flex !important;
    align-items: flex-start !important;
    padding: 10px 18px !important;
    margin: 0 !important;
    border-left: 2px solid transparent !important;
    background: transparent !important;
    border-radius: 0 !important;
    cursor: pointer !important;
    width: 100% !important;
    transition: background 0.12s, border-left-color 0.12s !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: rgba(255,255,255,0.04) !important;
    border-left-color: rgba(176,125,16,0.35) !important;
}
/* Selected (checked) option */
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: rgba(176,125,16,0.09) !important;
    border-left-color: var(--gold) !important;
}
/* Label text — the format_func string */
[data-testid="stSidebar"] [data-testid="stRadio"] label p,
[data-testid="stSidebar"] [data-testid="stRadio"] label div,
[data-testid="stSidebar"] [data-testid="stRadio"] label span {
    font-family: var(--font-m) !important;
    font-size: 0.69rem !important;
    color: #5a6a86 !important;
    line-height: 1.5 !important;
    white-space: pre-line !important;  /* renders the \n in format_func string */
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) div,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) span {
    color: #e8c060 !important;
}
/* Remove outer radio container padding/gap */
[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    gap: 0 !important;
}

/* ── Sidebar Clear Cache button ── */
/* Zero out the stButton wrapper's own margin so height matches nav rows */
[data-testid="stSidebar"] .stButton {
    padding: 0 18px !important;
    margin: 2px 0 !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: #5a6a86 !important;
    border: 1px solid #2a3448 !important;
    border-radius: 5px !important;
    font-family: var(--font-m) !important;
    font-size: 0.69rem !important;
    letter-spacing: 0 !important;
    text-transform: none !important;
    padding: 9px 14px !important;
    margin: 0 !important;
    width: 100% !important;
    transition: all 0.15s !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    border-color: var(--gold) !important;
    color: var(--gold) !important;
    background: rgba(176,125,16,0.05) !important;
}

.key-pill {
    font-family: var(--font-m); font-size: 0.58rem;
    padding: 3px 18px 10px; display: flex; align-items: center; gap: 6px;
}
.dot-ok   { display:inline-block; width:6px; height:6px; border-radius:50%; background:#22c55e; }
.dot-miss { display:inline-block; width:6px; height:6px; border-radius:50%; background:#ef4444; }
.text-ok   { color: #22c55e !important; }
.text-miss { color: #ef4444 !important; }

.sb-footer { padding: 12px 18px 20px; font-family: var(--font-m) !important; font-size: 0.56rem; color: #1e2a3a !important; line-height: 2.1; }

/* ── MASTHEAD ── */
.masthead { background: #12161f; padding: 32px 40px 28px; margin: -1rem -1rem 0 -1rem; }
.mh-flag { display:flex; align-items:center; justify-content:space-between; padding-bottom:13px; margin-bottom:20px; border-bottom:1px solid rgba(176,125,16,0.3); }
.mh-flag-l { font-family:var(--font-m); font-size:0.6rem; color:var(--gold); letter-spacing:2.5px; text-transform:uppercase; }
.mh-flag-r { font-family:var(--font-m); font-size:0.58rem; color:#2d3a50; letter-spacing:1.5px; }
.mh-headline { font-family:var(--font-d); font-size:clamp(2.6rem,4vw,4rem); font-weight:400; color:#f0ece4; line-height:1.0; letter-spacing:-1.5px; margin-bottom:10px; }
.mh-headline strong { font-weight:600; }
.mh-headline em { font-style:italic; color:var(--gold); }
.mh-deck { font-family:var(--font-b); font-size:0.92rem; color:#4a5a72; font-weight:300; line-height:1.6; max-width:520px; margin-bottom:22px; }
.mh-stats { display:flex; gap:0; border-top:1px solid #1e2535; padding-top:16px; }
.mh-stat { padding:0 28px 0 0; margin-right:28px; border-right:1px solid #1e2535; }
.mh-stat:last-child { border-right:none; }
.mh-stat-n { font-family:var(--font-d); font-size:1.85rem; font-weight:300; color:#f0ece4; line-height:1; }
.mh-stat-l { font-family:var(--font-m); font-size:0.53rem; color:#2d3a50; letter-spacing:2px; text-transform:uppercase; margin-top:4px; }

/* ── SECTIONS ── */
.sec-eyebrow { font-family:var(--font-m); font-size:0.57rem; letter-spacing:2.5px; text-transform:uppercase; color:var(--gold-dk); margin-bottom:12px; padding-bottom:8px; border-bottom:1px solid var(--gold-lt); }

/* ── BUTTONS ── */
.stButton > button {
    font-family: var(--font-m) !important; font-size: 0.65rem !important;
    letter-spacing: 1.2px !important; text-transform: uppercase !important;
    font-weight: 500 !important; padding: 10px 20px !important;
    border-radius: var(--rad) !important; border: 1px solid #d4c9a8 !important;
    background: var(--white) !important; color: var(--gold-dk) !important;
    transition: all 0.15s !important; box-shadow: var(--s1) !important; width: 100% !important;
}
.stButton > button:hover {
    background: var(--gold-pale) !important; border-color: var(--gold) !important; box-shadow: var(--s2) !important;
}
.stButton > button:active { transform: translateY(1px) !important; box-shadow: none !important; }
/* Secondary - second column button */
div[data-testid="column"] + div[data-testid="column"] .stButton > button {
    color: var(--ink-mid) !important; border-color: var(--paper-2) !important; background: var(--paper-1) !important;
}
div[data-testid="column"] + div[data-testid="column"] .stButton > button:hover {
    background: var(--paper-2) !important; border-color: var(--ink-faint) !important; color: var(--ink) !important;
}

/* ── REPORT ── */
.report-shell {
    background: #12161f;
    border: 1px solid #1e2535;
    border-top: 4px solid var(--gold);
    border-radius: var(--rad);
    box-shadow: var(--s2);
    overflow: hidden;
    margin-bottom: 16px;
}

.report-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 11px 20px;
    background: #1a1f2e;
    border-bottom: 1px solid #2d3a50;
}

.rt-date   { font-family: var(--font-m); font-size: 0.62rem; color: var(--gold); font-weight: 500; letter-spacing: 1.5px; text-transform: uppercase; }
.rt-engine { font-family: var(--font-m); font-size: 0.57rem; color: #8a96b0; letter-spacing: 1px; }

/* The report body wrapper sets the dark background + left/right padding */
.report-body { padding: 22px 26px 18px; background: #12161f; }

/*
 * BUG-A FIX: Streamlit renders st.markdown() inside its own stMarkdown divs
 * that sit OUTSIDE our .report-body container. We target the Streamlit
 * markdown container that immediately follows .report-body using a
 * data attribute selector, and also style the stMarkdown block itself.
 * We wrap the summary in a dedicated .report-content div and target all
 * Streamlit element containers rendered adjacent to it.
 */
.report-content,
.report-content *,
.report-content p,
.report-content li,
.report-content h1,
.report-content h2,
.report-content h3,
.report-content h4,
.report-content ul,
.report-content ol {
    color: #e2e8f0 !important;
    font-family: var(--font-b) !important;
    font-size: 1.0rem !important;
    line-height: 1.8 !important;
    background: transparent !important;
}
.report-content h2 {
    font-family: var(--font-d) !important;
    font-size: 1.15rem !important;
    font-weight: 600 !important;
    color: var(--gold) !important;
    border-bottom: 1px solid #2d3a50 !important;
    padding-bottom: 4px !important;
    margin-top: 18px !important;
    margin-bottom: 8px !important;
}
.report-content h3 {
    font-family: var(--font-d) !important;
    font-size: 1.0rem !important;
    color: #c8a84b !important;
}
.report-content strong { color: var(--gold) !important; font-weight: 600 !important; }
.report-content em     { color: #a8b8d0 !important; }
.report-content ul     { padding-left: 1.2rem !important; }
.report-content li     { margin-bottom: 4px !important; }

/* Force Streamlit's internal markdown wrappers dark when inside our report zone */
[data-testid="stVerticalBlockBorderWrapper"] .report-content ~ div p,
[data-testid="stVerticalBlockBorderWrapper"] .report-content ~ div li { color: #e2e8f0 !important; }

.report-foot {
    display: flex;
    gap: 7px;
    padding: 11px 20px;
    background: #1a1f2e;
    border-top: 1px solid #2d3a50;
    flex-wrap: wrap;
}

/* BUG-H FIX: rfl class (used in report footer links) was never defined */
.rfl {
    font-family: var(--font-m); font-size: 0.57rem; padding: 3px 8px;
    border-radius: 3px; text-decoration: none !important;
    border: 1px solid #2d3a50; color: var(--gold); background: rgba(176,125,16,0.12);
    transition: all 0.12s; display: inline-flex; align-items: center; gap: 3px;
}
.rfl:hover { background: rgba(176,125,16,0.22); border-color: var(--gold); }
.rfl.vid   { color: #6ec6c6; background: rgba(15,107,107,0.15); border-color: #1e4a4a; }
.rfl.vid:hover { background: rgba(15,107,107,0.25); }
.rfl.min   { color: #6ec48a; background: rgba(26,92,46,0.15); border-color: #1e3a28; }
.rfl.min:hover { background: rgba(26,92,46,0.25); }

/* ── MEETING CARDS ── */
.meeting-card { background:var(--white); border:1px solid #e0d8c8; border-left:3px solid var(--gold); border-radius:var(--rad); padding:13px 15px 11px; margin-bottom:9px; box-shadow:var(--s1); transition:box-shadow 0.15s; }
.meeting-card:hover { box-shadow:var(--s2); }
.mc-date { font-family:var(--font-m); font-size:0.58rem; color:var(--gold-dk); font-weight:500; letter-spacing:2px; text-transform:uppercase; margin-bottom:4px; }
.mc-title { font-family:var(--font-d); font-size:0.98rem; color:var(--ink); font-weight:600; margin-bottom:9px; }
.mc-links { display:flex; gap:5px; flex-wrap:wrap; align-items:center; }
.mcl { font-family:var(--font-m); font-size:0.57rem; padding:3px 8px; border-radius:3px; text-decoration:none !important; border:1px solid #d4c9a8; color:var(--gold-dk); background:var(--gold-pale); transition:all 0.12s; display:inline-flex; align-items:center; gap:3px; }
.mcl:hover { background:var(--gold-lt); }
.mcl.vid { color:var(--teal); background:var(--teal-lt); border-color:#b8d8d8; }
.mcl.vid:hover { background:#d0ecec; }
.mcl.min { color:var(--green); background:var(--green-lt); border-color:#b8d8c4; }
.mcl.min:hover { background:#cce8d8; }
.mc-badge { font-family:var(--font-m); font-size:0.54rem; padding:2px 6px; border-radius:3px; background:var(--gold-lt); color:var(--gold-dk); border:1px solid #d4c9a8; }

/* ── ARCHIVE ── */
.arc-card { display:flex; align-items:center; gap:10px; padding:11px 14px; background:var(--white); border:1px solid #e0d8c8; border-radius:var(--rad); margin-bottom:7px; box-shadow:var(--s1); transition:all 0.12s; }
.arc-card:hover { box-shadow:var(--s2); border-color:#cfc4aa; }
.arc-dot { width:7px; height:7px; border-radius:50%; background:var(--gold); flex-shrink:0; }
.arc-body { flex:1; min-width:0; }
.arc-date { font-family:var(--font-m); font-size:0.59rem; color:var(--gold-dk); letter-spacing:1.5px; text-transform:uppercase; font-weight:500; }
.arc-title { font-family:var(--font-b); font-size:0.83rem; color:var(--ink-mid); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.arc-engine { font-family:var(--font-m); font-size:0.54rem; color:var(--ink-faint); margin-top:2px; }

/* ── STATS ── */
.stats-bar { display:flex; background:var(--white); border:1px solid #e0d8c8; border-radius:var(--rad); overflow:hidden; box-shadow:var(--s1); margin-bottom:18px; }
.sc { flex:1; padding:14px 16px; border-right:1px solid #e0d8c8; text-align:center; }
.sc:last-child { border-right:none; }
.sc-n { font-family:var(--font-d); font-size:1.7rem; font-weight:300; color:var(--ink); line-height:1; }
.sc-l { font-family:var(--font-m); font-size:0.53rem; color:var(--ink-faint); letter-spacing:2px; text-transform:uppercase; margin-top:4px; }

/* ── INPUTS ── */
.stDateInput input { font-family:var(--font-m) !important; font-size:0.78rem !important; border-color:#cec5b0 !important; border-radius:var(--rad) !important; background:var(--white) !important; color:var(--ink) !important; padding:9px 12px !important; }
.stDateInput input:focus { border-color:var(--gold) !important; box-shadow:0 0 0 3px var(--gold-lt) !important; }
label[data-testid="stWidgetLabel"] p { font-family:var(--font-m) !important; font-size:0.58rem !important; color:var(--ink-light) !important; letter-spacing:1.5px !important; text-transform:uppercase !important; }

/* ── MISC ── */
/*
 * st.status() renders as a BlockProto.Expandable — same component as st.expander.
 * data-testid="stStatusWidget" targets the APP-LEVEL header spinner, NOT the in-page
 * st.status() call. The in-page status uses data-testid="stExpander" + "stExpanderDetails".
 *
 * Problem: st.write() inside st.status() renders stMarkdownContainer divs whose text
 * color defaults to var(--text-color) = dark ink on the light theme. The expander body
 * background also defaults to the page's light paper color.
 *
 * Fix: target stExpander elements that contain an icon (spinner/check/error) — these
 * are the st.status() instances. We force dark bg + light text on their content.
 * We scope to .stExpander to avoid breaking regular st.expander calls.
 */
[data-testid="stExpander"] {
    background: #1a1f2e !important;
    border: 1px solid #2d3a50 !important;
    border-radius: var(--rad) !important;
    overflow: hidden !important;
}
/* Expander header row (the label + icon bar) */
[data-testid="stExpander"] details summary {
    background: #12161f !important;
    padding: 10px 16px !important;
    border-bottom: 1px solid #2d3a50 !important;
    list-style: none !important;
}
[data-testid="stExpander"] details summary * {
    color: var(--gold) !important;
    font-family: var(--font-m) !important;
    font-size: 0.72rem !important;
    background: transparent !important;
}
/* Expander body panel — force dark bg, light text on EVERY descendant */
[data-testid="stExpanderDetails"] {
    background: #1a1f2e !important;
    padding: 12px 16px !important;
}
[data-testid="stExpanderDetails"] * {
    color: #c8d6e8 !important;
    background-color: #1a1f2e !important;
}
/* Inline elements that should be transparent (icons, spans inside text) */
[data-testid="stExpanderDetails"] svg {
    background-color: transparent !important;
    color: #22c55e !important;
    fill: #22c55e !important;
}
[data-testid="stExpanderDetails"] strong {
    color: #e8c060 !important;
    background-color: transparent !important;
}
/* stMarkdownContainer specifically */
[data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"],
[data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"] p {
    color: #c8d6e8 !important;
    background-color: #1a1f2e !important;
}
/* Checkbox / success tick that appears below each completed step */
[data-testid="stExpanderDetails"] [data-testid="stCheckbox"],
[data-testid="stExpanderDetails"] input[type="checkbox"] {
    accent-color: #22c55e !important;
}
.stAlert { font-family:var(--font-b) !important; font-size:0.87rem !important; border-radius:var(--rad) !important; }
.stSpinner > div { border-top-color:var(--gold) !important; }
.info-box { background:var(--white); border:1px solid #e0d8c8; border-radius:var(--rad); padding:16px 18px; margin-top:16px; box-shadow:var(--s1); }
.info-box-title { font-family:var(--font-m); font-size:0.57rem; color:var(--gold-dk); letter-spacing:2.5px; text-transform:uppercase; margin-bottom:7px; font-weight:500; }
.info-box-body { font-family:var(--font-b); font-size:0.84rem; color:var(--ink-mid); line-height:1.7; }
.empty-state { text-align:center; padding:28px 20px; background:var(--white); border:1px dashed #d4c9a8; border-radius:var(--rad); }
.empty-state-icon { font-size:1.5rem; margin-bottom:8px; opacity:0.4; }
.empty-state-text { font-family:var(--font-m); font-size:0.63rem; color:var(--ink-faint); line-height:1.9; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def get_engine(backend: str) -> CouncilEngine | None:
    try:
        return CouncilEngine(backend=backend)
    except Exception as e:
        st.error(f"⚠ Engine init failed: {e}")
        return None


@st.cache_data(ttl=60)
def _cached_load_from_supabase() -> list[dict]:
    """
    Loads reports from Supabase via the direct supabase-py client.
    Cached for 60 s. Call _cached_load_from_supabase.clear() to bust.
    Returns [] if Supabase is not configured or unavailable.
    """
    return load_from_supabase()


def load_archive() -> list[dict]:
    """
    Merges Supabase rows with any in-memory reports added this session.
    In-memory reports are shown immediately after analysis even if the
    Supabase write succeeded (avoids waiting for the 60 s cache to expire).
    """
    db_rows  = _cached_load_from_supabase()
    mem      = st.session_state.get("_mem_archive", [])
    if mem:
        db_dates = {r.get("meeting_date") for r in db_rows}
        extras   = [r for r in mem if r.get("meeting_date") not in db_dates]
        return extras + db_rows
    return db_rows


def res_links(meeting: dict, cls: str = "rfl") -> str:
    """Build HTML resource link chips — agenda, minutes, video. BUG-16 FIX: html.escape()."""
    h = ""
    if meeting.get("agenda_url"):
        h += f'<a class="{cls}" href="{html.escape(meeting["agenda_url"])}" target="_blank">📄 Agenda</a>'
    if meeting.get("minutes_url"):
        h += f'<a class="{cls} min" href="{html.escape(meeting["minutes_url"])}" target="_blank">📋 Minutes</a>'
    if meeting.get("webcast_url"):
        h += f'<a class="{cls} vid" href="{html.escape(meeting["webcast_url"])}" target="_blank">▶ Video</a>'
    return h


def run_analysis(meeting: dict, backend: str):
    """
    Full pipeline: transcript → AI summary → save → display.
    BUG-10 FIX: st.rerun() called OUTSIDE the st.status context manager.
    """
    should_rerun = False

    with st.status("Starting analysis...", expanded=True) as status:
        status.update(label=f"Searching YouTube for {meeting['date']}...")
        transcript = get_transcript(meeting["date"])

        if not transcript:
            status.update(label="❌ Transcript not found", state="error")
            st.error(
                f"**No transcript found for {html.escape(meeting['date'])}.**\n\n"
                "**Common causes:**\n"
                "- Video not yet uploaded (usually 1–2 days after the meeting)\n"
                "- Auto-captions not yet generated (check back in 24 hours)\n"
                "- Try the City YouTube channel manually: search *San Ramon City Council* on YouTube"
            )
            return  # do NOT rerun — let user see the error

        st.write(f"✅ Transcript: **{len(transcript):,} segments**")
        status.update(label=f"Generating summary with {BACKENDS[backend]['label']}...")

        engine = get_engine(backend)
        if not engine:
            status.update(label="❌ Engine failed", state="error")
            return

        summary        = engine.generate_summary(meeting, transcript)
        saved, save_msg = save_to_supabase(meeting, summary, backend)

        if saved:
            st.write("✅ Saved to Supabase")
            _cached_load_from_supabase.clear()
        else:
            st.warning(f"⚠ Supabase save skipped: {save_msg}")

        # Always add to in-memory archive for immediate display (BUG-04 FIX)
        mem_report = {
            "id":           _safe_key(f"mem_{meeting.get('iso', meeting['date'])}"),
            "meeting_date": meeting["date"],
            "title":        meeting.get("name", "City Council Meeting"),
            "summary":      summary,
            "backend_used": backend,
            "agenda_url":   meeting.get("agenda_url"),
            "minutes_url":  meeting.get("minutes_url"),
            "webcast_url":  meeting.get("webcast_url"),
            "created_at":   _dt.now().isoformat(),
        }
        mem = [r for r in st.session_state.get("_mem_archive", [])
               if r.get("meeting_date") != meeting["date"]]
        st.session_state["_mem_archive"] = [mem_report] + mem

        st.session_state.current_summary = summary
        st.session_state.current_meeting = meeting
        st.session_state.current_backend = backend
        status.update(label="✅ Analysis complete", state="complete")
        should_rerun = True

    # BUG-10 FIX: rerun OUTSIDE the `with st.status` block
    if should_rerun:
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# SIDEBAR  (rendered first so backend_choice is set before masthead)
# BUG-14 FIX: sidebar must render before masthead reads backend_choice
# ══════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div class="sb-brand">
        <div class="sb-brand-title">🏛️ Council Intelligence</div>
        <div class="sb-brand-sub">San Ramon, CA</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<span class="sb-label">AI Engine</span>', unsafe_allow_html=True)

    # ── Engine selector via @st.fragment ──────────────────────────────
    # st.fragment reruns ONLY this block when the radio changes — the main
    # page content is never re-rendered, so there is zero visible flash.
    # st.radio on_change updates session_state before the fragment reruns.

    if "backend_choice" not in st.session_state:
        st.session_state["backend_choice"] = "gemini"

    @st.fragment
    def _engine_selector() -> None:
        def _on_change() -> None:
            prev = st.session_state.get("backend_choice", "gemini")
            chosen = st.session_state["_engine_radio"]
            st.session_state["backend_choice"] = chosen
            if prev != chosen and "current_meeting" in st.session_state:
                st.session_state.pop("current_summary", None)
                st.session_state["_pending_reanalysis"] = True

        try:
            _idx = BACKEND_KEYS.index(st.session_state.get("backend_choice", "gemini"))
        except ValueError:
            _idx = 0

        st.radio(
            "Select engine",
            options=BACKEND_KEYS,
            format_func=lambda k: (
                f'{BACKENDS[k]["icon"]}  {BACKENDS[k]["label"]}\n'
                f'{BACKENDS[k]["ctx"]} · {BACKENDS[k]["speed"]}'
            ),
            index=_idx,
            key="_engine_radio",
            on_change=_on_change,
            label_visibility="collapsed",
        )

    _engine_selector()

    backend_choice = st.session_state.get("backend_choice", "gemini")

    cfg     = BACKENDS[backend_choice]
    key_set = bool(os.getenv(cfg["env_key"]))
    d_cls   = "dot-ok"  if key_set else "dot-miss"
    t_cls   = "text-ok" if key_set else "text-miss"
    k_msg   = f"{cfg['env_key']} set" if key_set else f"{cfg['env_key']} missing"

    st.markdown(f"""
    <div class="key-pill">
        <span class="{d_cls}"></span>
        <span class="{t_cls}">{k_msg}</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<hr style="border-color:#1e2535;margin:6px 0">', unsafe_allow_html=True)
    st.markdown('<span class="sb-label">Controls</span>', unsafe_allow_html=True)

    if st.button("⟳  Clear Cache", use_container_width=True):
        _cached_load_from_supabase.clear()
        st.session_state.pop("_mem_archive", None)
        st.session_state.pop("range_meetings", None)
        st.success("Cache and memory cleared")

    st.markdown('<hr style="border-color:#1e2535;margin:6px 0">', unsafe_allow_html=True)
    st.markdown("""
    <div class="sb-footer">
        Source · IQM2 RSS Feed<br>
        Video · YouTube API<br>
        Storage · Supabase<br>
        Version · 1.0.0<br>
        Logs · logs/council_app.log
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# DATA (loaded AFTER sidebar so backend_choice is resolved)
# BUG-14 FIX: data + masthead rendered after sidebar
# ══════════════════════════════════════════════════════════════════
archived_all = load_archive()
cfg          = BACKENDS[backend_choice]
key_set      = bool(os.getenv(cfg["env_key"]))
today_str    = _dt.now().strftime("%B %d, %Y").upper()

# If user changed model while a meeting is loaded, re-run analysis with new model
if st.session_state.pop("_pending_reanalysis", False):
    meeting = st.session_state.get("current_meeting")
    if meeting:
        run_analysis(meeting, backend_choice)


# ══════════════════════════════════════════════════════════════════
# MASTHEAD
# ══════════════════════════════════════════════════════════════════
st.markdown(f"""
<div class="masthead">
  <div class="mh-flag">
    <span class="mh-flag-l">San Ramon, CA &nbsp;·&nbsp; Civic Intelligence</span>
    <span class="mh-flag-r">{today_str} &nbsp;·&nbsp; {html.escape(cfg['label'].upper())}</span>
  </div>
  <div class="mh-headline"><strong>Council</strong> <em>Intelligence</em></div>
  <div class="mh-deck">AI-powered analysis of every San Ramon City Council meeting — votes, fiscal decisions, and public commentary distilled into a 30-second brief.</div>
  <div class="mh-stats">
    <div class="mh-stat"><div class="mh-stat-n">{len(archived_all)}</div><div class="mh-stat-l">Reports</div></div>
    <div class="mh-stat"><div class="mh-stat-n">{'✓' if key_set else '✗'}</div><div class="mh-stat-l">{'Engine Ready' if key_set else 'Key Missing'}</div></div>
    <div class="mh-stat"><div class="mh-stat-n">~30s</div><div class="mh-stat-l">Time to Insight</div></div>
    <div class="mh-stat"><div class="mh-stat-n">4h+</div><div class="mh-stat-l">Video Replaced</div></div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

col_left, col_right = st.columns([11, 7], gap="large")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LEFT — Intelligence Viewport
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with col_left:
    st.markdown('<div class="sec-eyebrow">Intelligence Viewport</div>', unsafe_allow_html=True)

    # ── Action bar — always visible ──────────────────────────────────
    c1, c2 = st.columns([3, 1])
    analyze = c1.button("▶  Analyze Latest Meeting", use_container_width=True)
    refresh = c2.button("⟳  Refresh", use_container_width=True)

    if refresh:
        st.session_state.pop("range_meetings", None)
        _cached_load_from_supabase.clear()
        st.rerun()

    if analyze:
        with st.status("Fetching meeting calendar...", expanded=True) as s:
            meeting = get_latest_meeting()
            if not meeting:
                s.update(label="❌ No recent meetings found", state="error")
                st.error(
                    "No City Council meetings found in the last 90 days.\n\n"
                    "Note: Only meetings with published agendas appear in the RSS feed."
                )
                st.stop()
            st.write(f"✅ **Found:** {html.escape(meeting['name'])} — {html.escape(meeting['date'])}")
        run_analysis(meeting, backend_choice)

    # ── Viewport — report or empty state ─────────────────────────────
    if "current_summary" in st.session_state:
        meta    = st.session_state.get("current_meeting", {})
        backend = st.session_state.get("current_backend", "—")
        links   = res_links(meta)

        # BUG-16 FIX: html.escape on injected strings
        safe_date   = html.escape(str(meta.get("date", "—")))
        safe_engine = html.escape(BACKENDS.get(backend, {}).get("label", backend).upper())

        # BUG-A FIX: Render summary as HTML inside the dark shell.
        # st.markdown() renders in Streamlit's own light-themed container
        # which sits outside our HTML div, making text invisible on dark bg.
        # We convert the markdown summary to HTML and inject it directly.
        import re as _re

        def _md_to_html(md: str) -> str:
            """Minimal Markdown → HTML converter for report display."""
            lines, out, in_list = md.split("\n"), [], False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("## "):
                    if in_list:
                        out.append("</ul>"); in_list = False
                    out.append(f'<h2>{html.escape(stripped[3:])}</h2>')
                elif stripped.startswith("### "):
                    if in_list:
                        out.append("</ul>"); in_list = False
                    out.append(f'<h3>{html.escape(stripped[4:])}</h3>')
                elif stripped.startswith(("- ", "* ", "• ")):
                    if not in_list:
                        out.append("<ul>"); in_list = True
                    item = stripped[2:].strip()
                    # bold
                    item = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html.escape(item))
                    out.append(f"<li>{item}</li>")
                elif stripped == "":
                    if in_list:
                        out.append("</ul>"); in_list = False
                    out.append("<br>")
                else:
                    if in_list:
                        out.append("</ul>"); in_list = False
                    para = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html.escape(stripped))
                    out.append(f"<p>{para}</p>")
            if in_list:
                out.append("</ul>")
            return "\n".join(out)

        summary_html = _md_to_html(st.session_state.current_summary)

        st.markdown(f"""
        <div class="report-shell">
          <div class="report-top">
            <span class="rt-date">{safe_date}</span>
            <span class="rt-engine">via {safe_engine}</span>
          </div>
          <div class="report-body">
            <div class="report-content">{summary_html}</div>
          </div>
          <div class="report-foot">
            {links or '<span style="font-family:var(--font-m);font-size:.58rem;color:#4a5a72">No documents on record for this meeting</span>'}
          </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("✕  Clear Viewport"):
            for k in ["current_summary", "current_meeting", "current_backend"]:
                st.session_state.pop(k, None)
            st.rerun()

    else:
        st.markdown("""
        <div class="info-box">
          <div class="info-box-title">How It Works</div>
          <div class="info-box-body">
            Meetings are sourced from the IQM2 RSS feed (published agendas only).
            Transcripts are fetched from the City's YouTube channel automatically.
            Use the <strong>Meeting Browser</strong> to the right to analyze any past session.
            Each card shows direct links to the Agenda PDF, Minutes, and Video recording.
          </div>
        </div>
        """, unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RIGHT — Archive + Browser
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with col_right:

    st.markdown('<div class="sec-eyebrow">Recently Viewed</div>', unsafe_allow_html=True)

    if archived_all:
        for report in archived_all:
            eng_label = BACKENDS.get(report.get("backend_used", ""), {}).get(
                "label", report.get("backend_used", "—")
            )
            # BUG-05 FIX: sanitize key, BUG-16 FIX: escape title
            safe_id    = _safe_key(str(report.get("id", "unknown")))
            safe_title = html.escape(report.get("title", "City Council Meeting"))
            safe_date  = html.escape(report.get("meeting_date", "—"))
            safe_eng   = html.escape(eng_label)

            ca, cb = st.columns([5, 2])
            with ca:
                st.markdown(f"""
                <div class="arc-card">
                  <div class="arc-dot"></div>
                  <div class="arc-body">
                    <div class="arc-date">{safe_date}</div>
                    <div class="arc-title">{safe_title}</div>
                    <div class="arc-engine">via {safe_eng}</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
            with cb:
                if st.button("View →", key=f"arch_{safe_id}"):  # BUG-05 FIX
                    st.session_state.current_summary = report["summary"]
                    st.session_state.current_meeting = {
                        "date":        report.get("meeting_date"),
                        "name":        report.get("title"),
                        "agenda_url":  report.get("agenda_url"),
                        "minutes_url": report.get("minutes_url"),
                        "webcast_url": report.get("webcast_url"),
                    }
                    st.session_state.current_backend = report.get("backend_used", "—")
                    st.rerun()
    else:
        st.markdown("""
        <div class="empty-state">
          <div class="empty-state-icon">🗂</div>
          <div class="empty-state-text">No reports viewed yet.<br>Analyze a meeting below to begin.</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # ── Meeting Browser ──────────────────────────────────
    st.markdown('<div class="sec-eyebrow">Meeting Browser</div>', unsafe_allow_html=True)

    d1, d2 = st.columns(2)
    start_val = d1.date_input("From", key="s_in")
    end_val   = d2.date_input("To",   key="e_in")

    if st.button("▶  Load Meetings in Range", use_container_width=True):
        with st.spinner("Fetching from RSS feed..."):
            found = get_meetings_in_range(
                start_val.strftime("%Y-%m-%d"),
                end_val.strftime("%Y-%m-%d"),
            )
        st.session_state.range_meetings = found or []
        if not found:
            st.warning("No City Council meetings found in that date range.")

    if st.session_state.get("range_meetings"):
        meetings      = st.session_state.range_meetings
        archive_dates = {r.get("meeting_date") for r in archived_all}
        st.caption(f"{len(meetings)} meeting(s) · RSS feed — published agendas only")
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        for i, m in enumerate(meetings):
            already    = m["date"] in archive_dates
            card_links = res_links(m, cls="mcl")
            # BUG-16 FIX: escape meeting name
            safe_name  = html.escape(m.get("name", "City Council"))
            safe_mdate = html.escape(m["date"])
            badge      = '<span class="mc-badge">✓ Archived</span>' if already else ""
            no_links   = '<span style="font-family:var(--font-m);font-size:.56rem;color:var(--ink-faint)">Documents pending publication</span>'

            st.markdown(f"""
            <div class="meeting-card">
              <div class="mc-date">{safe_mdate}</div>
              <div class="mc-title">{safe_name} {badge}</div>
              <div class="mc-links">{card_links or no_links}</div>
            </div>
            """, unsafe_allow_html=True)

            btn_label = "✓ View Report" if already else "▶ Analyze & Archive"
            if st.button(btn_label, key=f"rng_{i}", use_container_width=True):
                if already:
                    match = next(
                        (r for r in archived_all if r.get("meeting_date") == m["date"]),
                        None,
                    )
                    if match:
                        st.session_state.current_summary = match["summary"]
                        st.session_state.current_meeting = {
                            "date":        match.get("meeting_date"),
                            "name":        match.get("title"),
                            "agenda_url":  match.get("agenda_url"),
                            "minutes_url": match.get("minutes_url"),
                            "webcast_url": match.get("webcast_url"),
                        }
                        st.session_state.current_backend = match.get("backend_used", "—")
                        st.rerun()
                else:
                    run_analysis(m, backend_choice)
