from typing import Any, Optional
from pydantic import BaseModel, Field


class GeneratePlanRequest(BaseModel):
    job_description: str = Field(..., min_length=1)
    job_title: Optional[str] = None
    admin_command: Optional[str] = None
    company_name: Optional[str] = None


class TopicItem(BaseModel):
    difficulty: str  # EASY, MEDIUM, HARD
    questions: int


class SectionConfig(BaseModel):
    score: dict[str, int] = Field(default_factory=lambda: {"easy": 1, "medium": 2, "hard": 3})
    topics: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    totalQuestions: int = 0


class GeneratePlanResponse(BaseModel):
    name: str
    assessment_goal: str
    duration_minutes: int
    total_questions: int
    stage_to_attach: str = "Screening"
    sections: dict[str, Any]  # keyed by section type: mcq, descriptive, coding, verbal, reasoning, etc.


class GenerateQuestionsRequest(BaseModel):
    plan: dict[str, Any]
    company_tag: str = Field(..., min_length=1)
    batch: Optional[str] = None
    event_id: Optional[str] = None
    options: Optional[dict[str, Any]] = None


class QuestionItem(BaseModel):
    type: str  # MCQ, DESCRIPTIVE, CODING, VERBAL, REASONING, etc.
    skill: str
    difficulty: str
    question: str
    options: Optional[list[str]] = None
    correct_index: Optional[int] = None
    key_points: Optional[list[str]] = None
    sample_answer: Optional[str] = None
    test_cases: Optional[list[dict[str, Any]]] = None
    language: Optional[str] = None


class GenerateQuestionsResponse(BaseModel):
    questions: list[dict[str, Any]]
    suggested_questions: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "resources"  # "resources" | "scraped"


class OptimizeQuestionRequest(BaseModel):
    question: dict[str, Any] = Field(..., description="Single question object (same shape as generate-questions)")
    prompt_hint: str = Field(..., min_length=1, description="e.g. 'Increase difficulty', 'Add more context from JD'")


class OptimizeAllQuestionsRequest(BaseModel):
    questions: list[dict[str, Any]] = Field(..., description="List of question objects to improve")
    prompt: str = Field(..., min_length=1, description="Prompt to apply to all questions (e.g. 'Make more code-base oriented')")


class GenerateSingleQuestionRequest(BaseModel):
    section_type: str = Field(..., description="mcq, descriptive, or coding")
    skill: str = Field(..., min_length=1)
    difficulty: str = Field(..., description="EASY, MEDIUM, or HARD")
    prompt: Optional[str] = Field(None, description="Optional hint for AI (e.g. 'Make more code-base oriented')")
    company_tag: Optional[str] = Field(None, description="Optional company tag for context")
