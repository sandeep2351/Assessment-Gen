from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import ASSESSMENT_SERVICE_TOKEN
from db.mongodb import get_latest_parsed_for_company
from models.schemas import GenerateQuestionsRequest
from services.questions_generator import generate_questions

router = APIRouter(prefix="/generate-questions", tags=["questions"])
security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials):
    if ASSESSMENT_SERVICE_TOKEN and credentials.credentials != ASSESSMENT_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials


@router.post("", response_model=dict)
def post_generate_questions(
    body: GenerateQuestionsRequest,
    credentials: HTTPAuthorizationCredentials = Depends(verify_token),
):
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
