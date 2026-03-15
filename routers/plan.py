from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import ASSESSMENT_SERVICE_TOKEN
from models.schemas import GeneratePlanRequest, GeneratePlanResponse
from services.plan_generator import generate_plan

router = APIRouter(prefix="/generate-plan", tags=["plan"])
security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials):
    if ASSESSMENT_SERVICE_TOKEN and credentials.credentials != ASSESSMENT_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials


@router.post("", response_model=dict)
def post_generate_plan(
    body: GeneratePlanRequest,
    credentials: HTTPAuthorizationCredentials = Depends(verify_token),
):
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
