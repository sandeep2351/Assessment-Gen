import logging
from typing import Any

from services.gemini_client import generate_structured

logger = logging.getLogger(__name__)


def _build_context_from_parsed(parsed_content: Any) -> str:
    if isinstance(parsed_content, str):
        return parsed_content[:50000]
    if isinstance(parsed_content, dict):
        if "fullText" in parsed_content and parsed_content["fullText"]:
            return str(parsed_content["fullText"])[:50000]
        if "text" in parsed_content and parsed_content["text"]:
            return str(parsed_content["text"])[:50000]
        import json
        return json.dumps(parsed_content, indent=0)[:50000]
    if isinstance(parsed_content, list):
        import json
        return json.dumps(parsed_content, indent=0)[:50000]
    return str(parsed_content)[:50000]


QUESTIONS_SYSTEM_PROMPT = """You are an expert assessment question writer. Given an assessment plan (sections with topics and difficulty counts)
and optional context from company resources (parsed documents), generate assessment questions as a JSON object with:
- questions: array of question objects. Each has: type (MCQ, DESCRIPTIVE, CODING, VERBAL, REASONING, etc.), skill (topic name), difficulty (EASY/MEDIUM/HARD), question (text).
  For MCQ/VERBAL/REASONING also include: options (array of 4 strings), correct_index (0-based).
  For DESCRIPTIVE include: key_points (array of strings), sample_answer (optional string).
  For CODING include: test_cases (array of { input, expected_output }), language (e.g. python).
- suggested_questions: same structure, 3–5 extra questions the admin can add optionally.
- source: "resources" if context was used, else "scraped".

Generate exactly the number of questions per topic/difficulty as in the plan. Output only valid JSON."""


def generate_questions(
    plan: dict[str, Any],
    company_tag: str,
    parsed_context: str | None = None,
) -> dict[str, Any]:
    import json
    plan_str = json.dumps(plan, indent=2)[:15000]
    user_part = f"Assessment plan:\n{plan_str}\n\nCompany tag: {company_tag}\n\n"
    if parsed_context:
        user_part += f"Context from company resources (use this to tailor questions):\n{parsed_context}\n\n"
    else:
        user_part += "No company resources provided. Generate questions based only on the plan and general best practices.\n\n"
    user_part += "Output the JSON with 'questions', 'suggested_questions', and 'source'."

    prompt = f"{QUESTIONS_SYSTEM_PROMPT}\n\n{user_part}"
    out = generate_structured(prompt, {})
    if "questions" not in out:
        out["questions"] = []
    if "suggested_questions" not in out:
        out["suggested_questions"] = []
    if "source" not in out:
        out["source"] = "resources" if parsed_context else "scraped"
    return out
