from typing import Any

from services.gemini_client import generate_structured


PLAN_SYSTEM_PROMPT = """You are an expert assessment designer. Given a job description (and optional admin command), output an assessment plan as JSON.

SECTION SELECTION RULES:
- If the admin command explicitly mentions section types (e.g. "only MCQ", "add coding", "include descriptive"), follow that. Otherwise use the default set below.
- Default section set when admin does not specify sections: always include these three types: mcq, descriptive, coding. Do not omit any of these unless the admin command says otherwise.
- You may also add: interview, aptitude, reasoning, logical, verbal when the job description strongly supports them (e.g. analytical role → reasoning; language role → verbal).
- Analyze the job description for: job title, required skills, technologies, and level (junior/mid/senior). Map these to section topics and difficulty (EASY, MEDIUM, HARD).
- For coding sections, infer languages/frameworks from the JD (e.g. React, Node, Python). For descriptive sections, infer open-ended areas (e.g. system design, problem-solving). For MCQs, infer knowledge areas (e.g. APIs, databases, concepts).

OUTPUT JSON SHAPE:
- name: short assessment name (e.g. job title).
- assessment_goal: one paragraph goal for the assessment.
- duration_minutes: total time in minutes (e.g. 45–90). Also set "duration" to the same value.
- total_questions: sum of all questions. Also set "totalQuestions" to the same value.
- stage_to_attach: e.g. "Screening" or "Interview".
- sectionOrder: array of section keys in display order. When using default sections, use ["mcq", "descriptive", "coding"] (or include any extra sections you add after these).
- sections: object where each key is a section type (lowercase). Supported types: mcq, descriptive, coding, interview, aptitude, reasoning, logical, verbal. Each section has: score: { "easy": 1, "medium": 2, "hard": 3 }; topics: object mapping topic/skill name to list of { "difficulty": "EASY"|"MEDIUM"|"HARD", "questions": number }; totalQuestions: number.
- Set hasMCQ, hasCoding, hasDescriptive (and has* for any other section you include) to true. Set mcqCount, codingCount, descriptiveCount (and *Count for others) to that section's totalQuestions.
- topics: optional string summarizing topics.
- status: "active".

DATES AND VALIDITY:
- start_date_required: true. end_date_required: true. (Assessment validity must be bounded by start and end; treat these as required in the plan.)

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
