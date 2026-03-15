import json

from fastapi import APIRouter, HTTPException, Request

from config import ASSESSMENT_SERVICE_TOKEN
from db.mongodb import get_latest_parsed_for_company
from models.schemas import GenerateQuestionsRequest
from services.questions_generator import generate_questions

router = APIRouter(prefix="/generate-questions", tags=["questions"])


def _get_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


@router.post("", response_model=dict)
async def post_generate_questions(request: Request):
    """Accept JSON body with plan, company_tag, batch?, event_id?. No Depends(HTTPBearer) to avoid 422 on missing header."""
    if ASSESSMENT_SERVICE_TOKEN:
        token = _get_bearer_token(request)
        if not token or token != ASSESSMENT_SERVICE_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
    try:
        raw = await request.body()
        if not raw:
            raise HTTPException(status_code=422, detail="Request body is required")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=422, detail=f"Invalid JSON: {e}")
        body = GenerateQuestionsRequest.model_validate(data)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=422, detail=str(e))
    try:
        parsed_doc = get_latest_parsed_for_company(body.company_tag, body.batch)
        parsed_context = None
        if parsed_doc and parsed_doc.get("parsed_content"):
            from services.questions_generator import _build_context_from_parsed
            parsed_context = _build_context_from_parsed(parsed_doc["parsed_content"])

        result = generate_questions(
            plan=body.plan,
            company_tag=body.company_tag,
            parsed_context=parsed_context,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable")
