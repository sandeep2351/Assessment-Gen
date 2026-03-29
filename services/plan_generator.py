from typing import Any

from services.gemini_client import generate_structured


PLAN_SYSTEM_PROMPT = """You are an expert assessment designer for education and campus hiring. Given a job description (and optional admin command), output an assessment plan as JSON.

PEDAGOGY AND FAIRNESS:
- The assessment tests real skills from the JD (technologies, CS fundamentals, soft skills the role needs). It is not a branding exercise: the plan text must NOT assume every future question will name the employer.
- Use the company name sparingly in assessment_goal (e.g. one phrase naming the target organization) or when the admin command requires it. Do not instruct templated questions that repeat the employer name in every item.
- Balance question styles: mix conceptual knowledge, short scenarios, and problem-solving—not only generic "company scenario" prompts.

SECTION SELECTION RULES:
- If the admin command explicitly mentions section types (e.g. "only MCQ", "add verbal", "include quantitative"), follow that. Otherwise use the default set below.
- Default section set when admin does not specify sections: always include mcq, descriptive, and coding. Do not omit these unless the admin command says otherwise.
- You may add any of: interview, aptitude, reasoning, logical, verbal, quantitative, games, puzzles when the JD or admin command supports them (e.g. quantitative for data/analytics; verbal for communication-heavy roles; games/puzzles for logical thinking when requested).
- Analyze the JD for: title, required skills, stack, and seniority. Map skills to topic keys under each section (use concrete skill names from the JD, e.g. "REST APIs", "SQL joins", "React hooks", "Operating Systems").

CODING SECTION (CRITICAL):
- Topics must emphasize data structures and algorithms used in real interviews: arrays, strings, linked lists, stacks, queues, hash maps, trees, graphs, recursion, DFS, BFS, two pointers, sliding window, binary search, sorting, dynamic programming (when level fits)—similar in spirit to LeetCode / HackerRank style tasks for the role level.
- Prefer language-agnostic algorithmic problems. You may note a primary language from the JD in topics metadata intent, but the plan should distribute coding topics across these DSA themes, not only "API integration" or vague "company use-case N" placeholders.
- It is fine to include 1–2 problems that reflect the stack (e.g. parsing JSON, simple API design) if the JD stresses it, but the majority should be classic coding/DSA at appropriate difficulty.

OUTPUT JSON SHAPE:
- name: short assessment name (e.g. job title or "{title} — technical screen").
- assessment_goal: one paragraph: educational objective, skills tested, and level—professional tone, minimal employer repetition.
- duration_minutes: total time in minutes (e.g. 45–90). Also set "duration" to the same value.
- total_questions: sum of all questions. Also set "totalQuestions" to the same value.
- stage_to_attach: e.g. "Screening" or "Interview".
- sectionOrder: array of section keys in display order. Default order example: ["mcq", "descriptive", "coding"]; insert additional sections where the admin/JD requires them.
- sections: object keyed by lowercase section type. Supported types: mcq, descriptive, coding, interview, aptitude, reasoning, logical, verbal, quantitative, games, puzzles. Each section has: score: { "easy": 1, "medium": 2, "hard": 3 }; topics: object mapping topic/skill name to list of { "difficulty": "EASY"|"MEDIUM"|"HARD", "questions": number }; totalQuestions: number.
- Set hasMCQ, hasCoding, hasDescriptive (and has* flags) and mcqCount, codingCount, descriptiveCount (and matching counts) for every section you include.
- topics: optional string summarizing cross-section themes.
- status: "active".

DATES AND VALIDITY:
- start_date_required: true. end_date_required: true.

Output only valid JSON."""


def _minimal_section(section_type: str) -> dict[str, Any]:
    """Return a minimal section stub so UI always has mcq, descriptive, coding."""
    return {
        "score": {"easy": 1, "medium": 2, "hard": 3},
        "topics": {"General": [{"difficulty": "MEDIUM", "questions": 1}]},
        "totalQuestions": 1,
    }


def generate_plan(
    job_description: str,
    job_title: str | None = None,
    admin_command: str | None = None,
    company_name: str | None = None,
) -> dict[str, Any]:
    user_part = f"Job description:\n{job_description}\n\n"
    if job_title:
        user_part += f"Job title: {job_title}\n\n"
    if company_name:
        user_part += f"Company: {company_name}\n\n"
    if admin_command:
        user_part += f"Admin instruction: {admin_command}\n\n"
    user_part += "Generate the assessment plan JSON."

    prompt = f"{PLAN_SYSTEM_PROMPT}\n\n{user_part}"
    out = generate_structured(prompt, {})
    # Normalize section keys to lowercase
    if "sections" in out and isinstance(out["sections"], dict):
        out["sections"] = {k.lower(): v for k, v in out["sections"].items()}
    else:
        out["sections"] = {}
    # Enforce default sections: always include mcq, descriptive, coding if missing
    required_sections = ("mcq", "descriptive", "coding")
    for sec in required_sections:
        if sec not in out["sections"] or not out["sections"][sec]:
            out["sections"][sec] = _minimal_section(sec)
    # Ensure sectionOrder exists and includes default order
    if "sectionOrder" not in out or not isinstance(out["sectionOrder"], list):
        out["sectionOrder"] = list(out.get("sections", {}).keys()) if out.get("sections") else []
    order = out["sectionOrder"]
    for sec in required_sections:
        if sec not in order:
            order.append(sec)
    out["sectionOrder"] = order
    # Required dates (frontend will validate)
    out["start_date_required"] = True
    out["end_date_required"] = True
    # Aliases for compatibility
    if "duration_minutes" in out and "duration" not in out:
        out["duration"] = out["duration_minutes"]
    if "total_questions" in out and "totalQuestions" not in out:
        out["totalQuestions"] = out["total_questions"]
    return out
