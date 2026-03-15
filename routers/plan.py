import json

from fastapi import APIRouter, HTTPException, Request

from config import ASSESSMENT_SERVICE_TOKEN
from models.schemas import GeneratePlanRequest
from services.plan_generator import generate_plan

router = APIRouter(prefix="/generate-plan", tags=["plan"])


def _get_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


@router.post("", response_model=dict)
async def post_generate_plan(request: Request):
    """Accept JSON body with job_description, job_title?, admin_command?, company_name?. No dependency injection on body to avoid 422."""
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
        body = GeneratePlanRequest.model_validate(data)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=422, detail=str(e))
    try:
        result = generate_plan(
            job_description=body.job_description,
            job_title=body.job_title,
            admin_command=body.admin_command,
            company_name=body.company_name,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable")
