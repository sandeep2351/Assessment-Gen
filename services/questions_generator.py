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
and optional context from company resources (parsed documents), generate assessment questions as a JSON object.

Output format (MongoDB-friendly so test cases can be validated when students attempt assessments):

- questions: array of question objects. Each has "type" (MCQ, DESCRIPTIVE, CODING, APTITUDE, REASONING, LOGICAL, VERBAL, INTERVIEW), "skill" (topic name), "difficulty" (EASY/MEDIUM/HARD), "question" (text).

  For MCQ / APTITUDE / REASONING / LOGICAL / VERBAL (multiple choice): include "choice_1", "choice_2", "choice_3", "choice_4" (strings) and "correct_choice" (one of "choice_1", "choice_2", "choice_3", "choice_4"). Optionally "subject_tag", "topic_tag", "key_words" (array), "level_tag" (Easy/Intermediate/Hard), "type_of_question" (technical/non-technical).

  For CODING: include "title", "description" (full problem text), "example" (optional examples), "level" (Easy/Medium/Hard), "tags" (array of strings). For test case validation you MUST include "test_cases" as an object with two arrays: "inputs" (array of inputs, one per test) and "outputs" (array of expected outputs, same length). Example: "test_cases": {"inputs": ["input1", 42], "outputs": ["output1", true]}. Also set "language" (e.g. python, javascript). Optionally "sample_code" with keys "python", "javascript", "java", "c++" for solution snippets.

  For DESCRIPTIVE / INTERVIEW (long-form): include "evaluation_criteria" (array of strings), "sample_answer" (string or object with "sample_answer_low", "sample_answer_mid", "sample_answer_high" and optional "low_answer_scores", "mid_answer_scores", "high_answer_scores" as objects mapping criteria to number). Optionally "type_of_question" (numerical/text), "criteria" (string), "level" (EASY/MEDIUM/HARD).

- suggested_questions: same structure, 3–5 extra questions the admin can add optionally.
- source: "resources" if context was used, else "scraped".

Generate exactly the number of questions per topic/difficulty as in the plan. For CODING questions always provide test_cases.inputs and test_cases.outputs so that student code can be validated. Output only valid JSON."""


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
    # Normalize to MongoDB-friendly format for validation
    out["questions"] = [_normalize_question(q) for q in out["questions"]]
    out["suggested_questions"] = [_normalize_question(q) for q in out["suggested_questions"]]
    return out


def _normalize_question(q: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy/question format to MongoDB schema (test_cases inputs/outputs, choice_1..4 + correct_choice)."""
    q = dict(q)
    # Coding: test_cases array of {input, expected_output} -> {inputs: [], outputs: []}
    if q.get("type") == "CODING" and "test_cases" in q:
        tc = q["test_cases"]
        if isinstance(tc, list):
            inputs = []
            outputs = []
            for item in tc:
                if isinstance(item, dict):
                    inp = item.get("input")
                    out = item.get("expected_output") or item.get("output")
                    inputs.append(inp)
                    outputs.append(out)
            q["test_cases"] = {"inputs": inputs, "outputs": outputs}
        elif isinstance(tc, dict) and "inputs" not in tc and "input" in tc:
            q["test_cases"] = {"inputs": [tc["input"]], "outputs": [tc.get("expected_output") or tc.get("output")]}
    # MCQ-style: options + correct_index -> choice_1..4 + correct_choice
    if "options" in q and isinstance(q["options"], list) and "correct_choice" not in q:
        opts = q["options"]
        for i in range(1, 5):
            q.setdefault(f"choice_{i}", opts[i - 1] if i <= len(opts) else "")
        idx = q.get("correct_index", 0)
        if 0 <= idx < 4:
            q["correct_choice"] = f"choice_{idx + 1}"
        q.pop("options", None)
        q.pop("correct_index", None)
    return q
