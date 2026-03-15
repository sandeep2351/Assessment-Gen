import json
import logging
from typing import Any

import google.generativeai as genai

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def get_model():
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set")
    return genai.GenerativeModel("gemini-2.0-flash")


def generate_structured(prompt: str, response_schema: dict[str, Any]) -> dict[str, Any]:
    """Call Gemini and parse JSON from response. Schema is for documentation; we ask for JSON in prompt."""
    try:
        model = get_model()
        full_prompt = (
            f"{prompt}\n\n"
            "Respond with a single valid JSON object only, no markdown or extra text. "
            "Ensure all required fields are present."
        )
        response = model.generate_content(full_prompt)
        if not response or not response.text:
            raise ValueError("Empty response from Gemini")
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.exception("Gemini response was not valid JSON: %s", e)
        raise ValueError("AI returned invalid JSON") from e
    except Exception as e:
        logger.exception("Gemini call failed: %s", e)
        raise
