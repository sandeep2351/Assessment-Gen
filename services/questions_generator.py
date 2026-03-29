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


def _build_context_from_aggregation(agg: dict[str, Any]) -> str:
    """Format merged Mongo resource bundles (text + URLs) for the model."""
    parts: list[str] = []
    mt = agg.get("merged_text")
    if isinstance(mt, str) and mt.strip():
        parts.append(mt.strip()[:75000])
    urls = agg.get("file_urls") or []
    if isinstance(urls, list) and urls:
        ulist = [str(u).strip() for u in urls if str(u).strip()][:60]
        parts.append(
            "Hosted resource URLs (you may set question image_url to one of these when the question refers to that asset):\n"
            + "\n".join(f"- {u}" for u in ulist)
        )
    n = agg.get("resource_document_count")
    if n is not None:
        parts.append(f"Merged resource batches/documents: {n}")
    return "\n\n".join(parts)[:80000]


def _infer_placement_priority(
    plan: dict[str, Any],
    company_tag: str,
    job_description: str | None,
    tech_stack: list[str] | None,
    job_title: str | None,
    assessment_round: str | None,
    resource_excerpt: str,
) -> str:
    """
    Use the model to synthesize priority-ranked topics and round focus (campus placement).
    Does not replace web search; uses model knowledge + provided materials.
    """
    plan_str = json.dumps(plan, indent=0)[:6000]
    excerpt = (resource_excerpt or "")[:6000]
    jd = (job_description or "")[:6000]
    ts = ", ".join(str(s).strip() for s in (tech_stack or []) if str(s).strip())
    prompt = f"""You support Indian campus placement and early-career technical hiring assessments.

Output ONLY valid JSON with these keys:
- ranked_skills: array of max 18 objects {{ "skill": string, "priority": number (1 = highest), "reason": string }}
- common_patterns: string (2-5 sentences: typical online test + interview question patterns for this role, drawing on public knowledge of hiring — e.g. LeetCode-style topics, aptitude, verbal — without claiming live web scraping)
- round_focus: string (1-3 sentences on what the named assessment stage usually stresses)
- resource_alignment: string (1-3 sentences on how to use company resource text when generating questions)

Company tag (internal targeting): {company_tag}
Job title: {job_title or "not specified"}
Assessment round / stage: {assessment_round or "not specified"}
Tech stack: {ts or "not specified"}

Job description excerpt:
{jd}

Assessment plan excerpt:
{plan_str}

Merged resource excerpt (documents + captions; may be empty):
{excerpt}
"""
    try:
        out = generate_structured(prompt, {})
        return json.dumps(out, ensure_ascii=False, indent=0)[:14000]
    except Exception as e:
        logger.warning("placement priority inference failed: %s", e)
        return ""


QUESTIONS_SYSTEM_PROMPT = """You are an expert assessment question writer for campus placement, college hiring drives, and early-career technical screening in India and similar markets. You must generate questions that match the assessment plan EXACTLY.

AUDIENCE: Undergraduate and postgraduate students; difficulty and wording should be fair, exam-like, and free of unnecessary corporate jargon.

PRIORITY AND "MOST ASKED" TOPICS:
- You receive a JSON block "placement_priority" (may be empty). Use its ranked_skills and common_patterns to bias which skills and question styles appear first within each section and to mirror frequently assessed areas for this role (public interview-prep patterns, not live web browsing).
- Assign each question "placement_priority" integer 1–5 (5 = highest alignment with ranked skills / common patterns for this round). Spread priorities across the assessment; do not make every item priority 5.

PLAN STRUCTURE (follow precisely):
- The plan has "sections": an object where each key is a section type (e.g. "mcq", "descriptive", "coding").
- Each section has "topics": an object mapping topic/skill name to a list of objects: { "difficulty": "EASY"|"MEDIUM"|"HARD", "questions": number }.
- Example: sections.mcq.topics["JavaScript"] = [{"difficulty": "EASY", "questions": 2}, {"difficulty": "MEDIUM", "questions": 1}] means generate exactly 2 EASY and 1 MEDIUM MCQ questions for skill "JavaScript".
- The plan has "total_questions" (or "totalQuestions"): the total count across all sections. Your output must sum to this number exactly.

STRICT COUNT RULES (no exceptions):
1. Generate questions ONLY according to the plan. Do not add or remove any question.
2. For EACH section in the plan (use sectionOrder if present for order): for EACH topic in that section: for EACH entry in the topic list, generate exactly "questions" many questions at that "difficulty" for that topic. No more, no less.
3. Section key → question "type" field:
   - mcq → MCQ
   - descriptive → DESCRIPTIVE
   - coding → CODING
   - interview → INTERVIEW
   - aptitude → APTITUDE
   - reasoning → REASONING
   - logical → LOGICAL
   - verbal → VERBAL
   - quantitative → QUANTITATIVE (numeric/word-problem style; usually MCQ with four choices unless the plan implies otherwise—use MCQ shape with choices)
   - games → GAMES (prefer MCQ with four choices when possible; include image_url and/or image_description when visual)
   - puzzles → PUZZLES (prefer MCQ with four choices for logic puzzles; include image_url and/or image_description when visual)
4. Before outputting, ensure: (a) total questions in "questions" equals plan.total_questions (or totalQuestions), (b) counts per section/topic/difficulty match the plan.
5. Do not generate extra questions beyond the plan. Do not skip any (section, topic, difficulty, count).

COMPANY TAG AND CONTEXT (how to use them):
- You receive a "company_tag" for targeting only (e.g. which employer's interview patterns or uploaded resources apply). You may use it internally to choose difficulty distribution or common problem patterns for similar roles.
- Do NOT put the company name (or "At <employer>", "In <employer>") in every question stem. At most one question in the entire assessment may reference the employer explicitly, and only if natural (e.g. architecture question about a product named in provided resources). Default: zero employer mentions in stems.
- If "Context from company resources" is provided: ground themes, tech choices, and facts in that text; still write neutral, reusable question wording. If no resources: use JD + general best practices + widely known interview patterns (LeetCode/HackerRank style for coding).

JOB DESCRIPTION AND SKILLS:
- When a job description or tech stack is supplied, prioritize those skills in topic coverage, distractors, and coding tags. Questions should read like real exams/interviews, not placeholders.

CONTENT VARIETY (not only scenarios):
- Mix styles: definitions, "what happens when", code output/tracing, compare approaches, short realistic scenarios without naming the employer, design trade-offs, and pure algorithmic tasks.
- Avoid repetitive templates like "Explain how you would solve a <company> scenario using <skill>" or "Which option best applies <skill> at <company>?".

CODING SECTION (CRITICAL):
- Problems must be concrete DSA/programming tasks: arrays, strings, linked lists, stacks, queues, hash maps, trees, graphs, recursion, DFS, BFS, two pointers, sliding window, binary search, sorting, heaps, basic DP as appropriate to difficulty—similar to problems seen on LeetCode, HackerRank, Codeforces, GeeksforGeeks.
- Use clear I/O and constraints in "description". Include "tags" (e.g. ["arrays", "two-pointers"]). Prefer the language implied by the plan/JD (default python or javascript if unclear).
- Avoid vague stems like "Write a function for <company> use-case 1". Every coding item needs a self-contained problem statement a candidate could solve without knowing the employer.

VISUALS (GAMES, PUZZLES, DIAGRAM MCQs):
- When a list of "Hosted resource URLs" is provided, you may set "image_url" to an absolute or site-relative URL from that list when a question should display that asset (e.g. diagram, poster, puzzle image).
- If no suitable hosted URL exists, set "image_url" to null and use "image_description" for a diagram the UI could render later.
- For GAMES and PUZZLES with visuals, prefer MCQ shape with "choice_1".."choice_4", "correct_choice", plus "image_url" when applicable so candidates see the picture above the options.

OUTPUT FORMAT (MongoDB-friendly):
- questions: array. Each has "type", "skill" (exact topic name from plan), "difficulty" (EASY/MEDIUM/HARD), "placement_priority" (1–5), "question" (primary text; for CODING you may use a one-line summary in "question").

  For MCQ, APTITUDE, REASONING, LOGICAL, VERBAL, QUANTITATIVE, GAMES, PUZZLES (when MCQ): "choice_1".."choice_4", "correct_choice".

  For CODING: "title", "description", "level" (Easy/Medium/Hard), "tags", "language", "test_cases": {"inputs": [...], "outputs": [...]}.

  For DESCRIPTIVE, INTERVIEW, and open-ended GAMES/PUZZLES: "evaluation_criteria", "sample_answer".

  Optional for any type: "image_url" (string or null), "image_description" (string or null).

- suggested_questions: 5–10 extra questions (same structure) the admin can add; skill-focused, varied, no employer name spam.
- source: "resources" if company resource context was used meaningfully, else "scraped".

Output only valid JSON. The "questions" array length MUST equal plan.total_questions exactly."""


def generate_questions(
    plan: dict[str, Any],
    company_tag: str,
    parsed_context: str | None = None,
    job_description: str | None = None,
    tech_stack: list[str] | None = None,
    job_title: str | None = None,
    assessment_round: str | None = None,
    resource_file_urls: list[str] | None = None,
) -> dict[str, Any]:
    plan_str = json.dumps(plan, indent=2)[:15000]
    priority_json = _infer_placement_priority(
        plan,
        company_tag,
        job_description,
        tech_stack,
        job_title,
        assessment_round,
        parsed_context or "",
    )
    user_part = f"Assessment plan:\n{plan_str}\n\nCompany tag (targeting only; do not repeat in every stem): {company_tag}\n\n"
    if job_title and job_title.strip():
        user_part += f"Job title: {job_title.strip()}\n\n"
    if assessment_round and assessment_round.strip():
        user_part += f"Assessment round / stage: {assessment_round.strip()}\n\n"
    if job_description and job_description.strip():
        user_part += f"Job description (prioritize these skills and terms):\n{job_description.strip()[:12000]}\n\n"
    if tech_stack:
        ts = ", ".join(str(s).strip() for s in tech_stack if str(s).strip())
        if ts:
            user_part += f"Tech stack / skills emphasis: {ts}\n\n"
    if priority_json:
        user_part += f"placement_priority (use to rank and weight topics):\n{priority_json}\n\n"
    if resource_file_urls:
        user_part += (
            "Hosted resource URLs (optional image_url source for questions):\n"
            + "\n".join(f"- {u}" for u in resource_file_urls[:40])
            + "\n\n"
        )
    if parsed_context:
        user_part += (
            "Context from company-tagged resources (documents, captions from images, merged batches; "
            "use for themes and facts; still avoid putting the employer name in every question):\n"
            f"{parsed_context}\n\n"
        )
    else:
        user_part += "No company resources provided. Use the plan, job description if any, placement_priority, and standard industry interview practice.\n\n"
    user_part += (
        "Generate the 'questions' array so that: (1) for each section in the plan, for each topic and each difficulty entry, "
        "you output exactly that many questions (e.g. if a topic has [{\"difficulty\": \"EASY\", \"questions\": 2}], output exactly 2 EASY questions for that topic); "
        "(2) the total length of 'questions' must equal the plan's total_questions. No extra questions, no missing questions. "
        "Include placement_priority on every question. "
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

CONTENT:
- Write a concrete, skill-based question. Do not use a repetitive template that names a specific employer in the stem unless the user prompt explicitly requires it.
- For coding, prefer clear DSA-style problems (arrays, strings, trees, graphs, stacks, queues, recursion, DFS/BFS, etc.) with explicit I/O or constraints—not vague "company use-case" placeholders.

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
    if q.get("placement_priority") is None:
        q["placement_priority"] = 3
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
