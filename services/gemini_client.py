import json
import logging
import ssl
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from config import OPEROUTER_GEMINI_API_KEY

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = "google/gemini-2.0-flash-001"


def _ssl_context() -> ssl.SSLContext:
    """Use certifi CA bundle if available (fixes SSL errors on macOS Python.org installs)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _check_key():
    if not OPEROUTER_GEMINI_API_KEY or not OPEROUTER_GEMINI_API_KEY.strip():
        raise ValueError("OPEROUTER_GEMINI_API_KEY is not set in .env")


def generate_structured(prompt: str, response_schema: dict[str, Any]) -> dict[str, Any]:
    """Call Gemini via OpenRouter and parse JSON from response. Schema is for documentation; we ask for JSON in prompt."""
    _check_key()
    full_prompt = (
        f"{prompt}\n\n"
        "Respond with a single valid JSON object only, no markdown or extra text. "
        "Ensure all required fields are present."
    )
    body = json.dumps({
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": full_prompt}],
        "temperature": 0.3,
    }).encode("utf-8")
    req = Request(
        OPENROUTER_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {OPEROUTER_GEMINI_API_KEY.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://assessment-gen.local",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=60, context=_ssl_context()) as resp:
            data = json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        logger.exception("OpenRouter HTTP error %s: %s", e.code, body)
        raise
    except URLError as e:
        logger.exception("OpenRouter request failed: %s", e)
        raise
    choice = (data.get("choices") or [None])[0]
    if not choice:
        raise ValueError("Empty choices from OpenRouter")
    message = choice.get("message") or {}
    text = (message.get("content") or "").strip()
    if not text:
        raise ValueError("Empty response from Gemini via OpenRouter")
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.exception("Gemini response was not valid JSON: %s", e)
        raise ValueError("AI returned invalid JSON") from e
