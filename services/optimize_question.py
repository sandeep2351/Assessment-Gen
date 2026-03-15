import json
import logging
from typing import Any

from services.gemini_client import generate_structured

logger = logging.getLogger(__name__)

OPTIMIZE_SINGLE_SYSTEM = """You are an expert assessment question editor. You will receive a single assessment question (JSON) and a user prompt/hint. Your task is to return ONE improved question that applies the hint while preserving the question type and structure.

RULES:
- Output ONLY a single valid JSON object: the improved question. No markdown, no explanation.
- Preserve all required fields: type, skill, difficulty, question (or title/description for coding).
- For MCQ/APTITUDE/REASONING/LOGICAL/VERBAL: keep choice_1..choice_4 and correct_choice (or options + correct_index).
- For CODING: keep title, description, test_cases, language.
- For DESCRIPTIVE/INTERVIEW: keep evaluation_criteria, sample_answer.
- Apply the user's hint to improve the content (e.g. increase difficulty = harder wording or options; add context = weave in job-relevant details).
- Do not add or remove questions; return exactly one question object."""

OPTIMIZE_ALL_SYSTEM = """You are an expert assessment question editor. You will receive an array of assessment questions (JSON) and a user prompt. Your task is to return an array of improved questions, applying the prompt to each question while preserving types, order, and count.

RULES:
- Output ONLY a single valid JSON object with one key: "questions" (array of question objects). No markdown, no explanation.
- The output "questions" array MUST have the exact same length and order as the input.
- For each question, preserve type, skill, difficulty, and structure (choice_1..4 + correct_choice for MCQ; title/description/test_cases for CODING; evaluation_criteria/sample_answer for DESCRIPTIVE).
- Apply the user prompt consistently across all questions (e.g. "make more code-base oriented" = add code/implementation angle where relevant).
- Do not add or remove questions; do not reorder."""


def optimize_single_question(question: dict[str, Any], prompt_hint: str) -> dict[str, Any]:
    """Improve a single question based on the user's prompt hint. Returns the updated question object."""
    question_str = json.dumps(question, indent=2)[:8000]
    user_content = f"Question to improve:\n{question_str}\n\nUser hint: {prompt_hint}\n\nReturn the single improved question as a JSON object only."
    full_prompt = f"{OPTIMIZE_SINGLE_SYSTEM}\n\n{user_content}"
    out = generate_structured(full_prompt, {})
    if not isinstance(out, dict):
        raise ValueError("AI returned non-object for single question")
    return out


def optimize_all_questions(questions: list[dict[str, Any]], prompt: str) -> list[dict[str, Any]]:
    """Improve all questions based on the user prompt. Returns the list of updated questions (same order and count)."""
    if not questions:
        return []
    questions_str = json.dumps(questions, indent=2)[:40000]
    user_content = f"Questions to improve ({len(questions)} total):\n{questions_str}\n\nUser prompt to apply to all: {prompt}\n\nReturn a JSON object with a single key 'questions' containing the array of improved questions (same length and order)."
    full_prompt = f"{OPTIMIZE_ALL_SYSTEM}\n\n{user_content}"
    out = generate_structured(full_prompt, {})
    if not isinstance(out, dict) or "questions" not in out:
        raise ValueError("AI response must contain 'questions' array")
    result = out["questions"]
    if not isinstance(result, list):
        raise ValueError("'questions' must be an array")
    if len(result) != len(questions):
        raise ValueError(f"Expected {len(questions)} questions, got {len(result)}")
    return result
