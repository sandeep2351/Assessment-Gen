import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_text_from_pdf(content: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text
        return extract_text(io.BytesIO(content)) or ""
    except Exception as e:
        logger.warning("pdfminer extraction failed: %s", e)
        return ""


def extract_text_from_docx(content: bytes) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs) or ""
    except Exception as e:
        logger.warning("python-docx extraction failed: %s", e)
        return ""


IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif", "webp"})


def _mime_for_image_ext(ext: str) -> str:
    if ext == "jpg":
        return "image/jpeg"
    return f"image/{ext}"


def parse_file_content(filename: str, content: bytes) -> dict[str, Any]:
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    text = ""
    if ext in IMAGE_EXTENSIONS:
        return {
            "text": "",
            "filename": filename,
            "is_image": True,
            "mime_type": _mime_for_image_ext(ext),
        }
    if ext == "pdf":
        text = extract_text_from_pdf(content)
    elif ext in ("docx", "doc"):
        text = extract_text_from_docx(content)
    else:
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = ""
    return {"text": text, "filename": filename, "is_image": False}
