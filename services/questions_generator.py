import json
import logging
import re
from typing import Any

from services.gemini_client import generate_raw, generate_structured, parse_json_from_text

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


QUESTIONS_SYSTEM_PROMPT = """You are an expert assessment question writer. You must generate questions that match the assessment plan EXACTLY.

PLAN STRUCTURE (follow precisely):
- The plan has "sections": an object where each key is a section type (e.g. "mcq", "descriptive", "coding").
- Each section has "topics": an object mapping topic/skill name to a list of objects: { "difficulty": "EASY"|"MEDIUM"|"HARD", "questions": number }.
- Example: sections.mcq.topics["JavaScript"] = [{"difficulty": "EASY", "questions": 2}, {"difficulty": "MEDIUM", "questions": 1}] means generate exactly 2 EASY and 1 MEDIUM MCQ questions for skill "JavaScript".
- The plan has "total_questions" (or "totalQuestions"): the total count across all sections. Your output must sum to this number exactly.

STRICT COUNT RULES (no exceptions):
1. Generate questions ONLY according to the plan. Do not add or remove any question.
2. For EACH section in the plan (use sectionOrder if present for order): for EACH topic in that section: for EACH entry in the topic list, generate exactly "questions" many questions at that "difficulty" for that topic. No more, no less.
3. Section key → question type: "mcq" → MCQ; "descriptive" → DESCRIPTIVE; "coding" → CODING; "interview" → INTERVIEW; "aptitude" → APTITUDE; "reasoning" → REASONING; "logical" → LOGICAL; "verbal" → VERBAL.
4. Before outputting, ensure: (a) total number of questions in your "questions" array equals plan.total_questions (or totalQuestions), (b) for each section, the count of questions of that type matches the section's totalQuestions/topics breakdown.
5. Do not generate extra questions beyond the plan. Do not skip any (section, topic, difficulty, count). Any mismatch is invalid.

CONTENT RULES:
- Every CODING question MUST have "title" (short name) and "description" (full problem statement). Never use "Untitled question".
- Every DESCRIPTIVE/INTERVIEW question MUST have a full "question" text (the prompt the candidate sees).
- Use the exact topic/skill names from the plan as each question's "skill" field.

OUTPUT FORMAT (MongoDB-friendly):
- questions: array of question objects. Each has "type", "skill" (topic name from plan), "difficulty" (EASY/MEDIUM/HARD), "question" (text).

  For MCQ/APTITUDE/REASONING/LOGICAL/VERBAL: include "choice_1", "choice_2", "choice_3", "choice_4" and "correct_choice" (one of "choice_1".."choice_4").

  For CODING: include "title", "description", "level", "tags", "language", and "test_cases": {"inputs": [...], "outputs": [...]} (required for validation).

  For DESCRIPTIVE/INTERVIEW: include "evaluation_criteria" (array of strings), "sample_answer".

- suggested_questions: 5–10 extra questions (same structure) that the admin can add; tailor to company/role. These are in addition to the exact plan count.
- source: "resources" if context was used, else "scraped".

Output only valid JSON. The "questions" array length MUST equal plan.total_questions exactly."""


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
    user_part += (
        "Generate the 'questions' array so that: (1) for each section in the plan, for each topic and each difficulty entry, "
        "you output exactly that many questions (e.g. if a topic has [{\"difficulty\": \"EASY\", \"questions\": 2}], output exactly 2 EASY questions for that topic); "
        "(2) the total length of 'questions' must equal the plan's total_questions. No extra questions, no missing questions. "
        "Then output the JSON with 'questions', 'suggested_questions', and 'source'."
    )

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


SINGLE_QUESTION_SYSTEM = """You are an assessment question generator. Your response must be exactly one valid JSON object.

STRICT OUTPUT RULES (follow exactly):
1. Output ONLY a single line of text that is valid JSON. No markdown, no code fences, no explanation, no newline inside the line.
2. The entire response must be parseable by a JSON parser. Inside string values: use \\n for line breaks; escape any double quote with backslash.
3. Do not put actual newline characters inside any string. Do not put unescaped double quotes inside strings.

QUESTION TYPE (from section_type):
- mcq -> type "MCQ"
- descriptive -> type "DESCRIPTIVE"
- coding -> type "CODING"

REQUIRED FIELDS (include these exact keys):
- "type": one of MCQ, DESCRIPTIVE, CODING
- "skill": string (topic name)
- "difficulty": EASY, MEDIUM, or HARD
- "question": string (the main question text)

FOR MCQ ALSO INCLUDE:
- "choice_1", "choice_2", "choice_3", "choice_4": strings
- "correct_choice": one of "choice_1", "choice_2", "choice_3", "choice_4"

FOR CODING ALSO INCLUDE:
- "title": string (short name)
- "description": string (full problem)
- "language": string (e.g. javascript)
- "test_cases": {"inputs": [], "outputs": []}

FOR DESCRIPTIVE ALSO INCLUDE:
- "evaluation_criteria": array of strings
- "sample_answer": string

Output exactly one JSON object. One line only. Valid JSON only."""


def _extract_string_value(text: str, key: str) -> str | None:
    """Try to extract a JSON string value for key from raw text (handles broken JSON)."""
    # Match "key": "value" where value may contain escaped quotes
    pattern = rf'"{re.escape(key)}"\s*:\s*"((?:[^"\\]|\\.)*)"'
    m = re.search(pattern, text)
    if m:
        return m.group(1).replace("\\n", "\n").replace('\\"', '"')
    return None


def _raw_response_to_question(
    raw: str,
    section_lower: str,
    skill: str,
    diff_upper: str,
) -> dict[str, Any]:
    """
    Convert raw Gemini response to our question format. Tries JSON parse first, then regex fallback.
    Always returns a valid question dict for the given section type.
    """
    # 1) Try structured parse
    obj = parse_json_from_text(raw)
    if isinstance(obj, dict) and obj:
        obj.setdefault("type", "MCQ" if section_lower == "mcq" else "CODING" if section_lower == "coding" else "DESCRIPTIVE")
        obj.setdefault("skill", skill)
        obj.setdefault("difficulty", diff_upper)
        return obj
    # 2) Fallback: build minimal valid question from raw text
    q_type = "MCQ" if section_lower == "mcq" else "CODING" if section_lower == "coding" else "DESCRIPTIVE"
    question_text = _extract_string_value(raw, "question") or _extract_string_value(raw, "description") or "Generated question"
    out = {
        "type": q_type,
        "skill": skill,
        "difficulty": diff_upper,
        "question": question_text[:2000],
    }
    if q_type == "MCQ":
        for i in range(1, 5):
            out[f"choice_{i}"] = _extract_string_value(raw, f"choice_{i}") or f"Option {i}"
        out["correct_choice"] = _extract_string_value(raw, "correct_choice") or "choice_1"
    elif q_type == "CODING":
        out["title"] = _extract_string_value(raw, "title") or "Coding Problem"
        out["description"] = _extract_string_value(raw, "description") or question_text
        out["language"] = _extract_string_value(raw, "language") or "javascript"
        out["test_cases"] = {"inputs": [], "outputs": []}
    else:
        out["evaluation_criteria"] = []
        out["sample_answer"] = _extract_string_value(raw, "sample_answer") or ""
    return out


def generate_single_question(
    section_type: str,
    skill: str,
    difficulty: str,
    prompt: str | None = None,
    company_tag: str | None = None,
    parsed_context: str | None = None,
) -> dict[str, Any]:
    """Generate a single question of the given section type (mcq, descriptive, coding)."""
    section_lower = (section_type or "mcq").lower().strip()
    if section_lower not in ("mcq", "descriptive", "coding"):
        section_lower = "mcq"
    diff_upper = (difficulty or "MEDIUM").upper().strip()
    if diff_upper not in ("EASY", "MEDIUM", "HARD"):
        diff_upper = "MEDIUM"

    user_part = f"section_type: {section_lower}\nskill: {skill}\ndifficulty: {diff_upper}\n"
    if prompt and prompt.strip():
        user_part += f"User prompt/hint: {prompt.strip()}\n"
    if parsed_context:
        user_part += f"\nContext (use to tailor the question):\n{parsed_context[:6000]}\n"

    full_prompt = f"{SINGLE_QUESTION_SYSTEM}\n\n{user_part}\nOutput the single question as one line of valid JSON."
    json_instruction = "You must respond with exactly one line of valid JSON. No newlines inside the JSON. No markdown."
    raw = generate_raw(full_prompt, json_instruction)
    obj = _raw_response_to_question(raw, section_lower, skill, diff_upper)
    return _normalize_question(obj)


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
