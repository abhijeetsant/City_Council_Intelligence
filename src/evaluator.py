import pandas as pd
import datetime
import os
from google import genai

class SummaryEvaluator:
    def __init__(self):
        # Uses same Gemini client structure as engine.py
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        # Use same model as engine.py for consistency
        self._model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

    def score_summary(self, transcript, summary, model_name):
        """Scores a summary based on Faithfulness and Coverage."""
        prompt = (
            f"You are a civic auditor. Rate this city council summary based on the transcript.\n"
            f"TRANSCRIPT SNIPPET: {transcript[:5000]}\n\n"
            f"SUMMARY: {summary}\n\n"
            f"Rate 1-5 for:\n1. Faithfulness (Accuracy)\n2. Coverage (Key votes found)\n"
            f"Return format: 'Score: F=X, C=X'"
        )

        try:
            response = self.client.models.generate_content(
                model=self._model, contents=prompt
            )
            return {
                "Model":      model_name,
                "Evaluation": response.text,
                "Date":       datetime.date.today(),
            }
        except Exception as e:
            return {
                "Model":      model_name,
                "Evaluation": f"Error: {e}",
                "Date":       datetime.date.today(),  # BUG-F FIX: was missing on error path
            }

    def save_comparison(self, results_list):
        import os as _os
        _os.makedirs("logs", exist_ok=True)
        df = pd.DataFrame(results_list)
        df.to_csv("logs/model_evaluation.csv", index=False, mode='a')
