import base64
import json
import logging
import re
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


def _repair_newlines_in_strings(s: str) -> str:
    """Replace raw newlines inside double-quoted strings with \\n so JSON parses."""
    result = []
    i = 0
    in_string = False
    escape = False
    while i < len(s):
        c = s[i]
        if escape:
            escape = False
            result.append(c)
            i += 1
            continue
        if in_string:
            if c == "\\":
                escape = True
                result.append(c)
            elif c == '"':
                in_string = False
                result.append(c)
            elif c in ("\n", "\r"):
                result.append("\\n")
            else:
                result.append(c)
            i += 1
            continue
        if c == '"':
            in_string = True
        result.append(c)
        i += 1
    return "".join(result)


def parse_json_from_text(text: str) -> dict[str, Any] | None:
    """
    Try to parse a JSON object from raw model output. Strips markdown, repairs newlines, extracts object.
    Returns the parsed dict or None if all strategies fail.
    """
    if not text or not text.strip():
        return None
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_repair_newlines_in_strings(text))
    except json.JSONDecodeError:
        pass
    # Extract first complete { ... }
    start = text.find("{")
    if start != -1:
        depth = 0
        in_string = False
        escape = False
        i = start
        end = start
        while i < len(text):
            c = text[i]
            if escape:
                escape = False
                i += 1
                continue
            if in_string:
                if c == "\\":
                    escape = True
                elif c == '"':
                    in_string = False
                i += 1
                continue
            if c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
            i += 1
        if depth == 0 and end > start:
            subset = text[start:end]
            try:
                return json.loads(subset)
            except json.JSONDecodeError:
                try:
                    return json.loads(_repair_newlines_in_strings(subset))
                except json.JSONDecodeError:
                    pass
    return None


def generate_raw(prompt: str, json_instruction: str = "Respond with a single valid JSON object only, no markdown.") -> str:
    """Call OpenRouter and return raw response text (no JSON parsing)."""
    _check_key()
    full_prompt = f"{prompt}\n\n{json_instruction}"
    body = json.dumps({
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": full_prompt}],
        "temperature": 0.2,
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
    with urlopen(req, timeout=90, context=_ssl_context()) as resp:
        data = json.loads(resp.read().decode())
    choice = (data.get("choices") or [None])[0]
    if not choice:
        raise ValueError("Empty choices from OpenRouter")
    message = choice.get("message") or {}
    text = (message.get("content") or "").strip()
    if not text:
        raise ValueError("Empty response from Gemini via OpenRouter")
    return text


def describe_image_bytes(content: bytes, mime_type: str) -> str:
    """
    Use vision model via OpenRouter to describe an image for assessment context
    (text extraction, diagrams, puzzles). Returns plain text.
    """
    _check_key()
    b64 = base64.standard_b64encode(content).decode("ascii")
    mt = mime_type if "/" in mime_type else f"image/{mime_type}"
    data_url = f"data:{mt};base64,{b64}"
    body = json.dumps({
        "model": OPENROUTER_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Describe this image for use in campus placement assessments. "
                            "Extract visible text, numbers, diagrams, puzzle elements, and UI chrome. "
                            "If it is a chart or table, summarize the data structure. "
                            "Be concise but complete (max ~800 words)."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0.2,
        "max_tokens": 2048,
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
    with urlopen(req, timeout=120, context=_ssl_context()) as resp:
        data = json.loads(resp.read().decode())
    choice = (data.get("choices") or [None])[0]
    if not choice:
        raise ValueError("Empty choices from OpenRouter (vision)")
    message = choice.get("message") or {}
    text = (message.get("content") or "").strip()
    if not text:
        raise ValueError("Empty vision description from model")
    return text


def generate_structured(prompt: str, response_schema: dict[str, Any]) -> dict[str, Any]:
    """Call Gemini via OpenRouter and parse JSON from response."""
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
    obj = parse_json_from_text(text)
    if obj is not None:
        return obj
    logger.exception("Gemini response was not valid JSON")
    raise ValueError("AI returned invalid JSON")
