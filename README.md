# 🏛️ San Ramon Council Intelligence Platform
### AI-Powered Civic Transparency · *Know what your city decided, in 30 seconds*

---

## Overview

The San Ramon Council Intelligence Platform automates the discovery, transcription, and summarization of City Council meetings. Inspired by [citymeetings.nyc](https://citymeetings.nyc), it reduces resident time-to-insight from 4 hours to under 30 seconds.

Each meeting card surfaces:
- **AI Summary** — structured executive brief with votes, fiscal impact, public commentary
- **📄 Agenda** — official PDF from IQM2
- **📋 Minutes** — official minutes when published
- **▶ Webcast** — embedded video player on the IQM2 portal

---

## Architecture

```
SanRamon_Council_Intelligence/
├── app.py                    # Streamlit UI — main entry point
├── requirements.txt          # Python dependencies
├── .env                      # API keys (never commit)
├── .streamlit/
│   └── secrets.toml          # Supabase connection (never commit)
├── src/
│   ├── __init__.py
│   ├── scraper.py            # IQM2 RSS feed parser
│   ├── engine.py             # Multi-backend LLM summarization
│   └── youtube_logic.py      # YouTube transcript fetcher
└── logs/
    └── council_app.log       # Structured application logs
```

### Data Flow

```
IQM2 RSS Feed
    └─→ scraper.py (meeting metadata + resource URLs)
            └─→ youtube_logic.py (transcript via YouTube)
                    └─→ engine.py (LLM summary)
                            └─→ Supabase (archived report)
                                    └─→ app.py (displayed to user)
```

---

## Data Sources

| Source | What it provides | Notes |
|--------|-----------------|-------|
| IQM2 RSS Feed | Meeting metadata, agenda/minutes/webcast URLs | Only includes meetings with published agendas |
| YouTube | Full meeting transcript (auto-captions) | Searched by date string |
| Supabase | Archived AI summaries | Persisted after each analysis |

**Disclaimer:** The RSS feed only contains meetings with published agendas. This is intentional — it ensures every record has associated documents.

---

## Supported AI Backends

| Backend | Model | Context | Free Tier |
|---------|-------|---------|-----------|
| Gemini Flash | gemini-2.5-flash-preview-04-17 | 120k chars | ✅ Recommended |
| Llama 3.3 70B | llama-3.3-70b-versatile (Groq) | 18k chars | ✅ Fast |
| Trinity Large | arcee-ai/trinity-large-preview (OpenRouter) | 40k chars | ✅ |
| DeepSeek R1 | deepseek/deepseek-r1-0528 (OpenRouter) | 64k chars | ✅ |

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
# .env
GEMINI_API_KEY=your_key
GROQ_API_KEY=your_key
OPENROUTER_API_KEY=your_key
```

```toml
# .streamlit/secrets.toml
[connections.supabase]
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "your_anon_key"
```

### 3. Supabase table schema

```sql
create table council_reports (
    id           bigserial primary key,
    created_at   timestamptz default now(),
    meeting_date text,
    title        text,
    summary      text,
    backend_used text,
    agenda_url   text,
    minutes_url  text,
    webcast_url  text
);
```

### 4. Run

```bash
streamlit run app.py
```

---

## Roadmap

- **Speaker Diarization** — Identify individual council members vs. public commenters
- **RAG Search** — Query across all past meetings ("When did the council last vote on housing?")
- **Email Digest** — Weekly subscriber newsletter with meeting highlights
- **Multi-City** — Abstract the scraper layer to support other IQM2-powered cities
