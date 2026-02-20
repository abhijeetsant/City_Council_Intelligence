import os
from dotenv import load_dotenv
from src.scraper import get_latest_meeting
from src.youtube_logic import get_transcript
from src.engine import CouncilEngine

# Load API keys from .env
load_dotenv()

def run_pipeline():
    print("🚀 Initializing San Ramon Intelligence Pipeline...")
    
    # 1. Scrape Portal for Metadata
    meeting = get_latest_meeting()
    if not meeting:
        print("❌ Could not reach San Ramon portal.")
        return

    # 2. Get YouTube Transcript
    transcript = get_transcript(meeting['date'])
    if not transcript:
        print("❌ No transcript found for this meeting.")
        return

    # 3. Generate AI Summary
    print("🧠 Analyzing transcript with Groq AI (Llama 3.3)...")
    engine = CouncilEngine()
    summary = engine.generate_summary(meeting, transcript)
    
    print("\n" + "="*40)
    print(f"FINAL SUMMARY: {meeting['date']}")
    print("="*40)
    print(summary)

if __name__ == "__main__":
    run_pipeline()