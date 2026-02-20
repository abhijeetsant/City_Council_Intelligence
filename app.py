"""
app.py — San Ramon Council Intelligence Platform
Design direction: Premium civic editorial — think The Economist meets a Bloomberg Terminal.
Light background with deep ink tones for legibility. Gold accents for civic gravitas.
Typography: Cormorant Garamond (display) + Source Serif 4 (body) + IBM Plex Mono (labels)
"""

import logging
import os

import streamlit as st
from dotenv import load_dotenv

from src.scraper import get_latest_meeting, get_meetings_in_range
from src.youtube_logic import get_transcript
from src.engine import CouncilEngine
from st_supabase_connection import SupabaseConnection

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
logger.info("Platform starting")

st.set_page_config(
    page_title="San Ramon Council Intelligence",
    layout="wide",
    page_icon="🏛️",
    initial_sidebar_state="expanded",
)

BACKENDS = {
    "gemini": {
        "label": "Gemini 3 Flash", "model": "gemini-3-flash-preview",
        "env_key": "GEMINI_API_KEY", "icon": "◆", "ctx": "120k", "speed": "Recommended",
    },
    "groq_llama": {
        "label": "Llama 3.3 70B", "model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY", "icon": "▣", "ctx": "18k", "speed": "Fastest",
    },
    "trinity": {
        "label": "Trinity Large", "model": "arcee-ai/trinity-large-preview:free",
        "env_key": "OPENROUTER_API_KEY", "icon": "◈", "ctx": "40k", "speed": "Moderate",
    },
    "deepseek_r1": {
        "label": "DeepSeek R1", "model": "deepseek/deepseek-r1-0528:free",
        "env_key": "OPENROUTER_API_KEY", "icon": "◎", "ctx": "64k", "speed": "Thorough",
    },
}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,300;1,400&family=Source+Serif+4:ital,wght@0,300;0,400;0,600;1,300&family=IBM+Plex+Mono:wght@300;400;500&display=swap');

/* ═══════════════════════════════════════════════
   DESIGN SYSTEM TOKENS
═══════════════════════════════════════════════ */
:root {
    --ink-900:   #0f1117;
    --ink-800:   #1a1f2e;
    --ink-700:   #252c3d;
    --ink-500:   #4a5568;
    --ink-400:   #6b7a99;
    --ink-300:   #8896b3;
    --ink-200:   #adbdd4;
    --paper-100: #f8f6f1;
    --paper-50:  #faf9f6;
    --paper-0:   #ffffff;
    --gold-600:  #92610a;
    --gold-500:  #b07d10;
    --gold-400:  #c8911a;
    --gold-300:  #d4a135;
    --gold-100:  #f5ecd4;
    --gold-50:   #fdf8ed;
    --teal-600:  #0f5c5c;
    --teal-400:  #1a8080;
    --red-600:   #8b1a1a;
    --red-100:   #fde8e8;
    --green-600: #1a5c2e;
    --green-100: #e8f5ec;

    --font-display: 'Cormorant Garamond', Georgia, serif;
    --font-body:    'Source Serif 4', Georgia, serif;
    --font-mono:    'IBM Plex Mono', 'Courier New', monospace;

    --shadow-sm: 0 1px 3px rgba(15,17,23,0.08), 0 1px 2px rgba(15,17,23,0.06);
    --shadow-md: 0 4px 12px rgba(15,17,23,0.1), 0 2px 4px rgba(15,17,23,0.08);
    --shadow-lg: 0 12px 32px rgba(15,17,23,0.12), 0 4px 8px rgba(15,17,23,0.08);
    --radius:    6px;
}

/* ═══════════════════════════════════════════════
   BASE
═══════════════════════════════════════════════ */
*, *::before, *::after { box-sizing: border-box; }

html, body, [class*="css"] {
    font-family: var(--font-body);
    background: var(--paper-50);
    color: var(--ink-700);
    font-size: 15px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
}

.stApp {
    background: var(--paper-50);
}

/* ═══════════════════════════════════════════════
   SIDEBAR
═══════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background: var(--ink-900) !important;
    border-right: none !important;
    width: 280px !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding: 0 !important;
}

.sb-header {
    padding: 28px 20px 20px;
    border-bottom: 1px solid var(--ink-800);
    margin-bottom: 4px;
}
.sb-logo-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
}
.sb-logo-icon {
    width: 30px;
    height: 30px;
    background: var(--gold-500);
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
    flex-shrink: 0;
}
.sb-logo-name {
    font-family: var(--font-display);
    font-size: 1.05rem;
    font-weight: 600;
    color: #f0ece4;
    letter-spacing: -0.2px;
}
.sb-logo-sub {
    font-family: var(--font-mono);
    font-size: 0.58rem;
    color: var(--ink-400);
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-top: 2px;
}

.sb-section {
    font-family: var(--font-mono);
    font-size: 0.56rem;
    color: var(--ink-500);
    letter-spacing: 2.5px;
    text-transform: uppercase;
    padding: 16px 20px 8px;
}

/* Engine option rows */
.engine-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 20px;
    cursor: pointer;
    transition: background 0.12s;
    border-left: 2px solid transparent;
}
.engine-row:hover { background: rgba(255,255,255,0.03); }
.engine-row.active {
    background: rgba(176, 125, 16, 0.08);
    border-left-color: var(--gold-400);
}
.er-icon { font-size: 0.75rem; color: var(--gold-400); width: 16px; text-align: center; }
.er-content { flex: 1; min-width: 0; }
.er-name {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    color: #c8d0e0;
    font-weight: 400;
}
.er-meta {
    font-family: var(--font-mono);
    font-size: 0.57rem;
    color: var(--ink-500);
    margin-top: 1px;
}
.er-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
}
.er-dot.ok   { background: #22c55e; }
.er-dot.miss { background: #ef4444; }

.sb-divider {
    border: none;
    border-top: 1px solid var(--ink-800);
    margin: 8px 0;
}

.sb-footer {
    padding: 12px 20px 20px;
    font-family: var(--font-mono);
    font-size: 0.57rem;
    color: var(--ink-700);
    line-height: 2;
}

/* Radio hidden, engine-row is visual only */
[data-testid="stSidebar"] [data-testid="stRadio"] {
    display: none !important;
}

/* ═══════════════════════════════════════════════
   MASTHEAD — newspaper front page style
═══════════════════════════════════════════════ */
.masthead-wrap {
    background: var(--ink-900);
    padding: 0;
    margin: -1rem -1rem 0 -1rem;
}
.masthead-inner {
    max-width: 1200px;
    margin: 0 auto;
    padding: 36px 48px 32px;
}
.mh-flag {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24px;
    padding-bottom: 14px;
    border-bottom: 2px solid var(--gold-500);
}
.mh-flag-left {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    color: var(--gold-400);
    letter-spacing: 2.5px;
    text-transform: uppercase;
}
.mh-flag-right {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    color: var(--ink-500);
    letter-spacing: 1.5px;
}
.mh-nameplate {
    font-family: var(--font-display);
    font-size: clamp(2.8rem, 5vw, 4.5rem);
    font-weight: 300;
    color: #f5f0e8;
    line-height: 1.0;
    letter-spacing: -2px;
    margin-bottom: 8px;
}
.mh-nameplate strong { font-weight: 600; }
.mh-nameplate em { font-style: italic; color: var(--gold-300); }
.mh-deck {
    font-family: var(--font-body);
    font-size: 1.05rem;
    color: var(--ink-300);
    font-weight: 300;
    line-height: 1.55;
    max-width: 580px;
    margin-bottom: 24px;
}
.mh-metrics {
    display: flex;
    gap: 0;
    border-top: 1px solid var(--ink-800);
    padding-top: 16px;
}
.mh-metric {
    padding: 0 28px 0 0;
    margin: 0 28px 0 0;
    border-right: 1px solid var(--ink-800);
}
.mh-metric:first-child { padding-left: 0; }
.mh-metric:last-child { border-right: none; }
.mh-metric-val {
    font-family: var(--font-display);
    font-size: 1.8rem;
    font-weight: 300;
    color: #f5f0e8;
    line-height: 1;
}
.mh-metric-lbl {
    font-family: var(--font-mono);
    font-size: 0.55rem;
    color: var(--ink-500);
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-top: 3px;
}

/* ═══════════════════════════════════════════════
   PAGE BODY
═══════════════════════════════════════════════ */
.body-wrap {
    background: var(--paper-50);
    padding: 32px 0;
}

.section-eyebrow {
    font-family: var(--font-mono);
    font-size: 0.57rem;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    color: var(--gold-600);
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 10px;
}
.section-eyebrow::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--gold-100);
}

/* ═══════════════════════════════════════════════
   REPORT DISPLAY
═══════════════════════════════════════════════ */
.report-shell {
    background: var(--paper-0);
    border: 1px solid #e2d9c8;
    border-top: 3px solid var(--gold-500);
    border-radius: var(--radius);
    box-shadow: var(--shadow-md);
    overflow: hidden;
    margin-bottom: 16px;
}
.report-topper {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    background: var(--paper-100);
    border-bottom: 1px solid #e8dfc8;
}
.rt-date {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    color: var(--gold-600);
    font-weight: 500;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}
.rt-engine {
    font-family: var(--font-mono);
    font-size: 0.58rem;
    color: var(--ink-400);
    letter-spacing: 1px;
}
.report-body-wrap {
    padding: 24px 28px 20px;
}
/* Make Streamlit markdown match report style */
.report-body-wrap h2 {
    font-family: var(--font-display) !important;
    font-size: 1.15rem !important;
    font-weight: 600 !important;
    color: var(--ink-900) !important;
    letter-spacing: -0.3px !important;
    margin: 22px 0 8px !important;
    padding-bottom: 6px !important;
    border-bottom: 1px solid var(--gold-100) !important;
}
.report-body-wrap h2:first-child { margin-top: 0 !important; }
.report-body-wrap p {
    font-family: var(--font-body) !important;
    font-size: 0.92rem !important;
    color: var(--ink-700) !important;
    line-height: 1.75 !important;
    margin-bottom: 10px !important;
}
.report-body-wrap ul {
    padding-left: 20px !important;
    margin-bottom: 10px !important;
}
.report-body-wrap li {
    font-family: var(--font-body) !important;
    font-size: 0.9rem !important;
    color: var(--ink-700) !important;
    line-height: 1.65 !important;
    margin-bottom: 5px !important;
}
.report-body-wrap strong {
    color: var(--ink-900) !important;
    font-weight: 600 !important;
}
.report-footer {
    display: flex;
    gap: 8px;
    padding: 12px 20px;
    background: var(--paper-100);
    border-top: 1px solid #e8dfc8;
    flex-wrap: wrap;
    align-items: center;
}
.rf-link {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    letter-spacing: 0.8px;
    padding: 5px 12px;
    border-radius: 4px;
    text-decoration: none;
    border: 1px solid #d4c9a8;
    color: var(--gold-600);
    background: var(--gold-50);
    transition: all 0.15s;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-weight: 500;
}
.rf-link:hover {
    background: var(--gold-100);
    border-color: var(--gold-400);
    color: var(--gold-600);
    text-decoration: none;
}
.rf-link.video {
    color: var(--teal-600);
    background: #f0fafa;
    border-color: #b8d8d8;
}
.rf-link.video:hover { background: #ddf0f0; border-color: var(--teal-400); }
.rf-link.minutes {
    color: var(--green-600);
    background: var(--green-100);
    border-color: #b8d8c4;
}
.rf-link.minutes:hover { background: #ccecd8; border-color: var(--green-600); }

/* ═══════════════════════════════════════════════
   ACTION BUTTONS
═══════════════════════════════════════════════ */
.stButton > button {
    font-family: var(--font-mono) !important;
    font-size: 0.65rem !important;
    letter-spacing: 1.2px !important;
    text-transform: uppercase !important;
    font-weight: 500 !important;
    padding: 10px 20px !important;
    border-radius: 5px !important;
    border: 1px solid #d4c9a8 !important;
    background: var(--paper-0) !important;
    color: var(--gold-600) !important;
    transition: all 0.15s !important;
    box-shadow: var(--shadow-sm) !important;
}
.stButton > button:hover {
    background: var(--gold-50) !important;
    border-color: var(--gold-400) !important;
    color: var(--gold-600) !important;
    box-shadow: var(--shadow-md) !important;
}
.stButton > button:active {
    transform: translateY(1px) !important;
    box-shadow: none !important;
}
/* Secondary/clear button */
.btn-secondary .stButton > button {
    color: var(--ink-400) !important;
    border-color: #dde3ee !important;
}
.btn-secondary .stButton > button:hover {
    background: var(--paper-100) !important;
    border-color: var(--ink-300) !important;
    color: var(--ink-700) !important;
}

/* Sidebar buttons */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: var(--ink-400) !important;
    border-color: var(--ink-800) !important;
    box-shadow: none !important;
    font-size: 0.62rem !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.04) !important;
    border-color: var(--gold-400) !important;
    color: var(--gold-400) !important;
}

/* ═══════════════════════════════════════════════
   MEETING CARDS
═══════════════════════════════════════════════ */
.meeting-card {
    background: var(--paper-0);
    border: 1px solid #e4ddd0;
    border-left: 3px solid var(--gold-300);
    border-radius: var(--radius);
    padding: 14px 16px 12px;
    margin-bottom: 10px;
    box-shadow: var(--shadow-sm);
    transition: box-shadow 0.15s, border-color 0.15s;
}
.meeting-card:hover {
    box-shadow: var(--shadow-md);
    border-left-color: var(--gold-500);
}
.mc-date {
    font-family: var(--font-mono);
    font-size: 0.58rem;
    color: var(--gold-600);
    font-weight: 500;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 5px;
}
.mc-title {
    font-family: var(--font-display);
    font-size: 1rem;
    color: var(--ink-900);
    font-weight: 600;
    margin-bottom: 10px;
    letter-spacing: -0.2px;
}
.mc-links { display: flex; gap: 6px; flex-wrap: wrap; }
.mc-link {
    font-family: var(--font-mono);
    font-size: 0.57rem;
    letter-spacing: 0.5px;
    padding: 3px 9px;
    border-radius: 3px;
    text-decoration: none;
    border: 1px solid #d4c9a8;
    color: var(--gold-600);
    background: var(--gold-50);
    transition: all 0.12s;
    display: inline-flex;
    align-items: center;
    gap: 4px;
}
.mc-link:hover { background: var(--gold-100); border-color: var(--gold-400); }
.mc-link.vid {
    color: var(--teal-600);
    background: #f0fafa;
    border-color: #b8d8d8;
}
.mc-link.vid:hover { background: #d8eeee; border-color: var(--teal-400); }
.mc-link.min {
    color: var(--green-600);
    background: var(--green-100);
    border-color: #b8d8c4;
}
.mc-link.min:hover { background: #ccecd8; border-color: var(--green-600); }
.mc-badge {
    font-family: var(--font-mono);
    font-size: 0.54rem;
    padding: 2px 7px;
    border-radius: 3px;
    background: var(--gold-100);
    color: var(--gold-600);
    border: 1px solid #d4c9a8;
    font-weight: 500;
}

/* ═══════════════════════════════════════════════
   ARCHIVE LIST
═══════════════════════════════════════════════ */
.archive-card {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    background: var(--paper-0);
    border: 1px solid #e4ddd0;
    border-radius: var(--radius);
    margin-bottom: 8px;
    box-shadow: var(--shadow-sm);
    transition: all 0.15s;
    cursor: pointer;
}
.archive-card:hover {
    box-shadow: var(--shadow-md);
    border-color: #d4c9a8;
}
.ac-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--gold-400);
    flex-shrink: 0;
}
.ac-body { flex: 1; min-width: 0; }
.ac-date {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    color: var(--gold-600);
    letter-spacing: 1.5px;
    text-transform: uppercase;
    font-weight: 500;
}
.ac-title {
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--ink-700);
    margin-top: 1px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.ac-engine {
    font-family: var(--font-mono);
    font-size: 0.54rem;
    color: var(--ink-400);
    margin-top: 2px;
}

/* ═══════════════════════════════════════════════
   STATS BAR
═══════════════════════════════════════════════ */
.stats-bar {
    display: flex;
    gap: 0;
    background: var(--paper-0);
    border: 1px solid #e4ddd0;
    border-radius: var(--radius);
    overflow: hidden;
    box-shadow: var(--shadow-sm);
    margin-bottom: 20px;
}
.stat-cell {
    flex: 1;
    padding: 16px 20px;
    border-right: 1px solid #e4ddd0;
    text-align: center;
}
.stat-cell:last-child { border-right: none; }
.stat-n {
    font-family: var(--font-display);
    font-size: 2rem;
    font-weight: 300;
    color: var(--ink-900);
    line-height: 1;
}
.stat-l {
    font-family: var(--font-mono);
    font-size: 0.54rem;
    color: var(--ink-400);
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-top: 4px;
}

/* ═══════════════════════════════════════════════
   INPUTS & FORMS
═══════════════════════════════════════════════ */
.stDateInput input {
    font-family: var(--font-mono) !important;
    font-size: 0.78rem !important;
    border-color: #d4cbb8 !important;
    border-radius: 5px !important;
    background: var(--paper-0) !important;
    color: var(--ink-700) !important;
    padding: 9px 12px !important;
}
.stDateInput input:focus {
    border-color: var(--gold-400) !important;
    box-shadow: 0 0 0 3px var(--gold-50) !important;
}
label[data-testid="stWidgetLabel"] p {
    font-family: var(--font-mono) !important;
    font-size: 0.58rem !important;
    color: var(--ink-500) !important;
    letter-spacing: 1.5px !important;
    text-transform: uppercase !important;
    font-weight: 400 !important;
}

/* ═══════════════════════════════════════════════
   STREAMLIT OVERRIDES
═══════════════════════════════════════════════ */
[data-testid="stRadio"] { display: none !important; }

[data-testid="stStatusWidget"] {
    background: var(--paper-0) !important;
    border: 1px solid #e4ddd0 !important;
    border-radius: var(--radius) !important;
    font-family: var(--font-mono) !important;
    font-size: 0.72rem !important;
    color: var(--ink-700) !important;
    box-shadow: var(--shadow-sm) !important;
}
.stAlert {
    font-family: var(--font-body) !important;
    font-size: 0.88rem !important;
    border-radius: var(--radius) !important;
}
[data-testid="stExpander"] {
    background: var(--paper-0) !important;
    border: 1px solid #e4ddd0 !important;
    border-radius: var(--radius) !important;
    box-shadow: var(--shadow-sm) !important;
}
[data-testid="stExpander"] summary {
    font-family: var(--font-mono) !important;
    font-size: 0.68rem !important;
    color: var(--ink-500) !important;
}
.stSpinner > div { border-top-color: var(--gold-400) !important; }
.stProgress > div > div { background: var(--gold-400) !important; }
hr { border-color: #e4ddd0 !important; margin: 16px 0 !important; }
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: var(--paper-100); }
::-webkit-scrollbar-thumb { background: #d4cbb8; border-radius: 2px; }
#MainMenu, footer, header { visibility: hidden; }

/* ═══════════════════════════════════════════════
   INFO BOX
═══════════════════════════════════════════════ */
.info-box {
    background: var(--paper-0);
    border: 1px solid #e4ddd0;
    border-radius: var(--radius);
    padding: 18px 20px;
    margin-top: 20px;
    box-shadow: var(--shadow-sm);
}
.info-box-title {
    font-family: var(--font-mono);
    font-size: 0.57rem;
    color: var(--gold-600);
    letter-spacing: 2.5px;
    text-transform: uppercase;
    margin-bottom: 8px;
    font-weight: 500;
}
.info-box-body {
    font-family: var(--font-body);
    font-size: 0.85rem;
    color: var(--ink-500);
    line-height: 1.7;
}

/* ═══════════════════════════════════════════════
   EMPTY STATE
═══════════════════════════════════════════════ */
.empty-state {
    text-align: center;
    padding: 32px 20px;
    background: var(--paper-0);
    border: 1px dashed #d4cbb8;
    border-radius: var(--radius);
}
.empty-state-icon { font-size: 1.8rem; margin-bottom: 10px; opacity: 0.4; }
.empty-state-text {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--ink-400);
    letter-spacing: 1px;
    line-height: 1.8;
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def get_engine(backend: str) -> CouncilEngine | None:
    try:
        return CouncilEngine(backend=backend)
    except (ValueError, RuntimeError) as e:
        st.error(f"Engine error: {e}")
        return None


@st.cache_data(ttl=300)
def load_archive() -> list[dict]:
    try:
        conn   = st.connection("supabase", type=SupabaseConnection)
        result = conn.table("council_reports").select("*").order("created_at", desc=True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Archive: {e}", exc_info=True)
        return []


def resource_links_html(meeting: dict, style: str = "rf") -> str:
    """Renders agenda / minutes / webcast / YouTube links as HTML chips."""
    cls_base  = f"{style}-link"
    html = ""
    if meeting.get("agenda_url"):
        html += f'<a class="{cls_base}" href="{meeting["agenda_url"]}" target="_blank">📄 Agenda PDF</a>'
    if meeting.get("minutes_url"):
        html += f'<a class="{cls_base} minutes" href="{meeting["minutes_url"]}" target="_blank">📋 Minutes</a>'
    if meeting.get("webcast_url"):
        html += f'<a class="{cls_base} video" href="{meeting["webcast_url"]}" target="_blank">▶ Video</a>'
    return html


def run_analysis(meeting: dict, backend: str):
    """Full pipeline: transcript → AI → save → display. FIX#4: scrolls to report."""
    with st.status("Starting analysis...", expanded=True) as status:
        status.update(label=f"Fetching YouTube transcript for {meeting['date']}...")
        transcript = get_transcript(meeting["date"])
        if not transcript:
            status.update(label="❌ No transcript found", state="error")
            st.error(
                f"No YouTube transcript found for **{meeting['date']}**.\n\n"
                "The video may not be uploaded yet, or auto-captions are disabled on this video."
            )
            return

        st.write(f"✅ Transcript: **{len(transcript):,} segments**")
        status.update(label=f"Generating summary with {BACKENDS[backend]['label']}...")

        engine = get_engine(backend)
        if not engine:
            status.update(label="❌ Engine init failed", state="error")
            return

        summary = engine.generate_summary(meeting, transcript)
        saved   = engine.save_to_supabase(meeting, summary, backend)

        if saved:
            st.write("✅ Report saved to archive")
            load_archive.clear()  # FIX #4: bust cache so archive refreshes immediately

        st.session_state.current_summary = summary
        st.session_state.current_meeting = meeting
        st.session_state.current_backend = backend
        status.update(label="✅ Analysis complete", state="complete")
    st.rerun()  # FIX #4: rerun brings user to top where report is displayed


# ═══════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════
with st.sidebar:
    cfg_current = BACKENDS.get(
        st.session_state.get("backend_radio", "gemini"), BACKENDS["gemini"]
    )

    st.markdown(f"""
    <div class="sb-header">
        <div class="sb-logo-row">
            <div class="sb-logo-icon">🏛️</div>
            <div>
                <div class="sb-logo-name">Council Intel</div>
            </div>
        </div>
        <div class="sb-logo-sub">San Ramon, CA</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sb-section">AI Engine</div>', unsafe_allow_html=True)

    # Real radio (hidden via CSS) for state
    backend_choice = st.radio(
        "engine", options=list(BACKENDS.keys()),
        format_func=lambda k: BACKENDS[k]["label"],
        index=0, label_visibility="collapsed", key="backend_radio",
    )

    # Visual engine rows
    for key, cfg in BACKENDS.items():
        key_set  = bool(os.getenv(cfg["env_key"]))
        is_active = key == backend_choice
        active_cls = "active" if is_active else ""
        dot_cls    = "ok" if key_set else "miss"
        st.markdown(f"""
        <div class="engine-row {active_cls}">
            <span class="er-icon">{cfg['icon']}</span>
            <div class="er-content">
                <div class="er-name">{cfg['label']}</div>
                <div class="er-meta">{cfg['ctx']} · {cfg['speed']}</div>
            </div>
            <div class="er-dot {dot_cls}"></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="sb-section">Controls</div>', unsafe_allow_html=True)

    if st.button("⟳  Clear Cache", use_container_width=True):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.success("Cleared")

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    st.markdown("""
    <div class="sb-footer">
        Source · IQM2 RSS Feed<br>
        Transcripts · YouTube API<br>
        Storage · Supabase<br>
        Logs · logs/council_app.log
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# MASTHEAD
# ═══════════════════════════════════════════════════════════
archived_all = load_archive()
cfg = BACKENDS[backend_choice]
key_set = bool(os.getenv(cfg["env_key"]))
from datetime import datetime as _dt
today_str = _dt.now().strftime("%B %d, %Y").upper()

st.markdown(f"""
<div class="masthead-wrap">
  <div class="masthead-inner">
    <div class="mh-flag">
      <span class="mh-flag-left">San Ramon, CA &nbsp;·&nbsp; Civic Intelligence Platform</span>
      <span class="mh-flag-right">{today_str} &nbsp;·&nbsp; ENGINE: {cfg['label'].upper()}</span>
    </div>
    <div class="mh-nameplate"><strong>Council</strong> <em>Intelligence</em></div>
    <div class="mh-deck">
      AI-powered analysis of every San Ramon City Council meeting —
      votes, fiscal decisions, and public commentary distilled into a 30-second brief.
    </div>
    <div class="mh-metrics">
      <div class="mh-metric">
        <div class="mh-metric-val">{len(archived_all)}</div>
        <div class="mh-metric-lbl">Archived Reports</div>
      </div>
      <div class="mh-metric">
        <div class="mh-metric-val">{'●' if key_set else '○'}</div>
        <div class="mh-metric-lbl">{'Engine Ready' if key_set else 'Key Missing'}</div>
      </div>
      <div class="mh-metric">
        <div class="mh-metric-val">~30s</div>
        <div class="mh-metric-lbl">Time to Insight</div>
      </div>
      <div class="mh-metric">
        <div class="mh-metric-val">4h</div>
        <div class="mh-metric-lbl">Video Replaced</div>
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# MAIN COLUMNS
# ═══════════════════════════════════════════════════════════
col_left, col_right = st.columns([11, 7], gap="large")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LEFT — Viewport
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with col_left:
    st.markdown('<div class="section-eyebrow">Intelligence Viewport</div>', unsafe_allow_html=True)

    # ── Active report display ──────────────────────────────
    if "current_summary" in st.session_state:
        meta     = st.session_state.get("current_meeting", {})
        backend  = st.session_state.get("current_backend", "—")
        date_str = meta.get("date", "—")
        rf_links = resource_links_html(meta, style="rf")

        st.markdown(f"""
        <div class="report-shell">
          <div class="report-topper">
            <span class="rt-date">{date_str}</span>
            <span class="rt-engine">Generated via {backend.upper()}</span>
          </div>
          <div class="report-body-wrap">
        """, unsafe_allow_html=True)

        st.markdown(st.session_state.current_summary)

        st.markdown(f"""
          </div>
          <div class="report-footer">
            {rf_links if rf_links else '<span style="font-family:var(--font-mono);font-size:0.58rem;color:var(--ink-400)">No documents available</span>'}
          </div>
        </div>
        """, unsafe_allow_html=True)

        with st.container():
            st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
            if st.button("✕  Clear Report"):
                for key in ["current_summary", "current_meeting", "current_backend"]:
                    st.session_state.pop(key, None)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # ── Analyze latest ─────────────────────────────────────
    else:
        c1, c2 = st.columns([3, 1])
        analyze = c1.button("▶  Analyze Latest Meeting", use_container_width=True)
        with c2:
            st.markdown('<div class="btn-secondary">', unsafe_allow_html=True)
            refresh = st.button("⟳  Refresh", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        if analyze:
            with st.status("Connecting to meeting calendar...", expanded=True) as s:
                s.update(label="Fetching RSS feed...")
                meeting = get_latest_meeting()
                if not meeting:
                    s.update(label="❌ No recent meetings found", state="error")
                    st.error(
                        "No City Council meetings found in the last 90 days.\n\n"
                        "Only meetings with published agendas appear in the RSS feed."
                    )
                    st.stop()
                st.write(f"✅ **Found:** {meeting['name']} — {meeting['date']}")
            run_analysis(meeting, backend_choice)

        st.markdown("""
        <div class="info-box">
          <div class="info-box-title">How It Works</div>
          <div class="info-box-body">
            Meetings are sourced from the IQM2 RSS feed (published agendas only).
            Transcripts are fetched from the City's YouTube channel via auto-captions.
            AI summaries are generated by your selected engine and saved to the archive
            on the right. Use the <strong>Meeting Browser</strong> below to analyze any past session.
          </div>
        </div>
        """, unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RIGHT — Archive + Browser
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with col_right:

    # ── Archived Reports ───────────────────────────────────
    st.markdown('<div class="section-eyebrow">Archived Reports</div>', unsafe_allow_html=True)

    if archived_all:
        latest_date = archived_all[0].get("meeting_date", "—")
        engines_n   = len(set(r.get("backend_used", "") for r in archived_all))
        st.markdown(f"""
        <div class="stats-bar">
          <div class="stat-cell">
            <div class="stat-n">{len(archived_all)}</div>
            <div class="stat-l">Reports</div>
          </div>
          <div class="stat-cell">
            <div class="stat-n">{engines_n}</div>
            <div class="stat-l">Engines</div>
          </div>
          <div class="stat-cell">
            <div class="stat-n" style="font-size:0.9rem;padding-top:4px">{latest_date}</div>
            <div class="stat-l">Latest</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        for report in archived_all:
            engine_lbl = BACKENDS.get(report.get("backend_used",""), {}).get("label", report.get("backend_used","—"))
            col_a, col_b = st.columns([5, 2])
            with col_a:
                st.markdown(f"""
                <div class="archive-card">
                  <div class="ac-dot"></div>
                  <div class="ac-body">
                    <div class="ac-date">{report.get('meeting_date','—')}</div>
                    <div class="ac-title">{report.get('title','City Council Meeting')}</div>
                    <div class="ac-engine">via {engine_lbl}</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
            with col_b:
                if st.button("View →", key=f"arch_{report['id']}"):
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
          <div class="empty-state-text">No archived reports yet.<br>Analyze a meeting to begin.</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-eyebrow">Meeting Browser</div>', unsafe_allow_html=True)

    d1, d2 = st.columns(2)
    start_val = d1.date_input("From", key="s_in")
    end_val   = d2.date_input("To",   key="e_in")

    if st.button("▶  Load Meetings in Range", use_container_width=True):
        with st.spinner("Fetching from RSS feed..."):
            found = get_meetings_in_range(
                start_val.strftime("%Y-%m-%d"),
                end_val.strftime("%Y-%m-%d"),
            )
        st.session_state.range_meetings = found if found else []
        if not found:
            st.warning("No City Council meetings found in that date range.")

    # ── Render meeting cards ───────────────────────────────
    if "range_meetings" in st.session_state and st.session_state.range_meetings:
        meetings     = st.session_state.range_meetings
        archive_dates = {r.get("meeting_date") for r in archived_all}

        st.caption(f"{len(meetings)} meeting(s) · RSS feed with published agendas")
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        for i, m in enumerate(meetings):
            already = m["date"] in archive_dates

            # FIX #5 & #6: show all resource links including video + minutes
            links_html = ""
            if m.get("agenda_url"):
                links_html += f'<a class="mc-link" href="{m["agenda_url"]}" target="_blank">📄 Agenda</a>'
            if m.get("minutes_url"):
                links_html += f'<a class="mc-link min" href="{m["minutes_url"]}" target="_blank">📋 Minutes</a>'
            if m.get("webcast_url"):
                links_html += f'<a class="mc-link vid" href="{m["webcast_url"]}" target="_blank">▶ Video</a>'

            badge = '<span class="mc-badge">✓ Archived</span>' if already else ""

            st.markdown(f"""
            <div class="meeting-card">
              <div class="mc-date">{m['date']}</div>
              <div class="mc-title">{m.get('name','City Council')} {badge}</div>
              <div class="mc-links">{links_html if links_html else
                '<span style="font-family:var(--font-mono);font-size:0.57rem;color:var(--ink-400)">Documents pending publication</span>'}</div>
            </div>
            """, unsafe_allow_html=True)

            btn_label = "✓ View Report" if already else "▶ Analyze & Archive"
            if st.button(btn_label, key=f"rng_{i}", use_container_width=True):
                if already:
                    match = next((r for r in archived_all if r.get("meeting_date") == m["date"]), None)
                    if match:
                        st.session_state.current_summary = match["summary"]
                        st.session_state.current_meeting = {
                            "date": match.get("meeting_date"), "name": match.get("title"),
                            "agenda_url": match.get("agenda_url"),
                            "minutes_url": match.get("minutes_url"),
                            "webcast_url": match.get("webcast_url"),
                        }
                        st.session_state.current_backend = match.get("backend_used","—")
                        st.rerun()
                else:
                    run_analysis(m, backend_choice)
