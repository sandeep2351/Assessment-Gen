import json
import logging

from fastapi import APIRouter, HTTPException, Request

from config import ASSESSMENT_SERVICE_TOKEN
from db.mongodb import get_latest_parsed_for_company
from models.schemas import GenerateSingleQuestionRequest
from services.questions_generator import generate_single_question, _build_context_from_parsed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/generate-single-question", tags=["questions"])


def _get_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


@router.post("", response_model=dict)
async def post_generate_single_question(request: Request):
    """Generate a single question (MCQ, descriptive, or coding). Body: section_type, skill, difficulty, prompt?, company_tag?."""
    if ASSESSMENT_SERVICE_TOKEN:
        token = _get_bearer_token(request)
        if not token or token != ASSESSMENT_SERVICE_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
    try:
        raw = await request.body()
        if not raw:
            raise HTTPException(status_code=422, detail="Request body is required")
        data = json.loads(raw)
        body = GenerateSingleQuestionRequest.model_validate(data)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=422, detail=str(e))

    parsed_context = None
    if body.company_tag and body.company_tag.strip():
        parsed_doc = get_latest_parsed_for_company(body.company_tag.strip(), None)
        if parsed_doc and parsed_doc.get("parsed_content"):
            parsed_context = _build_context_from_parsed(parsed_doc["parsed_content"])

    try:
        result = generate_single_question(
            section_type=body.section_type,
            skill=body.skill,
            difficulty=body.difficulty,
            prompt=body.prompt,
            company_tag=body.company_tag,
            parsed_context=parsed_context,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("generate-single-question failed: %s", e)
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable")
