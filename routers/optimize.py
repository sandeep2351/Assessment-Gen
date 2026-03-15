import json
import logging

from fastapi import APIRouter, HTTPException, Request

from config import ASSESSMENT_SERVICE_TOKEN
from models.schemas import OptimizeQuestionRequest, OptimizeAllQuestionsRequest
from services.optimize_question import optimize_single_question, optimize_all_questions

logger = logging.getLogger(__name__)
router = APIRouter(tags=["optimize"])


def _get_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


@router.post("/optimize-question", response_model=dict)
async def post_optimize_question(request: Request):
    """Improve a single question based on a prompt hint. Body: { question, prompt_hint }."""
    if ASSESSMENT_SERVICE_TOKEN:
        token = _get_bearer_token(request)
        if not token or token != ASSESSMENT_SERVICE_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
    try:
        raw = await request.body()
        if not raw:
            raise HTTPException(status_code=422, detail="Request body is required")
        data = json.loads(raw)
        body = OptimizeQuestionRequest.model_validate(data)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=422, detail=str(e))
    try:
        result = optimize_single_question(body.question, body.prompt_hint)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("optimize-question failed: %s", e)
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable")


@router.post("/optimize-all-questions", response_model=dict)
async def post_optimize_all_questions(request: Request):
    """Improve all questions based on a prompt. Body: { questions, prompt }."""
    if ASSESSMENT_SERVICE_TOKEN:
        token = _get_bearer_token(request)
        if not token or token != ASSESSMENT_SERVICE_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
    try:
        raw = await request.body()
        if not raw:
            raise HTTPException(status_code=422, detail="Request body is required")
        data = json.loads(raw)
        body = OptimizeAllQuestionsRequest.model_validate(data)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=422, detail=str(e))
    try:
        result = optimize_all_questions(body.questions, body.prompt)
        return {"questions": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("optimize-all-questions failed: %s", e)
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable")
