from typing import Any

from services.gemini_client import generate_structured


PLAN_SYSTEM_PROMPT = """You are an expert assessment designer. Given a job description (and optional admin command),
output an assessment plan as JSON with:
- name: short assessment name (e.g. job title)
- assessment_goal: one paragraph goal for the assessment
- duration_minutes: total time (e.g. 60–90)
- total_questions: sum of all questions
- stage_to_attach: e.g. "Screening" or "Interview"
- sections: object where each key is a section type. Supported section types include: mcq, descriptive, coding, verbal, reasoning.
  You may include any subset. Each section has:
  - score: { "easy": 1, "medium": 2, "hard": 3 }
  - topics: object mapping topic/skill name to list of { "difficulty": "EASY"|"MEDIUM"|"HARD", "questions": number }
  - totalQuestions: number (sum of questions in topics)

Examples of section types: mcq (multiple choice), descriptive (written answers), coding (programming), verbal (language/grammar), reasoning (logical/analytical).
Output only valid JSON."""


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
    return out
