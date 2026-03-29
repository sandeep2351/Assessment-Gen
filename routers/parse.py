from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import ASSESSMENT_SERVICE_TOKEN
from services.file_parser import parse_file_content
from services.gemini_client import describe_image_bytes

router = APIRouter(prefix="/parse-resource", tags=["parse"])
security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials):
    if ASSESSMENT_SERVICE_TOKEN and credentials.credentials != ASSESSMENT_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return credentials


@router.post("", response_model=dict)
async def post_parse_resource(
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(verify_token),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    result = parse_file_content(file.filename or "unknown", content)
    if result.get("is_image"):
        try:
            mime = str(result.get("mime_type") or "image/png")
            caption = describe_image_bytes(content, mime)
            result["image_caption"] = caption
            result["text"] = caption
        except Exception:
            result["image_caption"] = ""
            result["text"] = ""
    return {"parsed_content": result}
