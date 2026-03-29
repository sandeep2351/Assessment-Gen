import logging
from typing import Any

from pymongo import MongoClient
from config import (
    MONGODB_URI,
    ASSESSMENT_DB_NAME,
    EVENT_RESOURCES_COLLECTION,
    MONGODB_TLS_INSECURE,
)

logger = logging.getLogger(__name__)

_client: MongoClient | None = None
_db: Any = None


def get_client() -> MongoClient | None:
    global _client
    if not MONGODB_URI:
        logger.warning("MONGODB_URI not set")
        return None
    if _client is None:
        try:
            kwargs: dict[str, Any] = {}
            if MONGODB_TLS_INSECURE:
                kwargs["tlsAllowInvalidCertificates"] = True
            _client = MongoClient(MONGODB_URI, **kwargs)
            _client.admin.command("ping")
        except Exception as e:
            logger.exception("MongoDB connection failed: %s", e)
            return None
    return _client


def get_db():
    global _db
    if _db is not None:
        return _db
    client = get_client()
    if client is None:
        return None
    _db = client[ASSESSMENT_DB_NAME]
    return _db


def get_latest_parsed_for_company(company_tag: str, batch: str | None = None) -> dict[str, Any] | None:
    """Get latest batch parsed content for company. Only uses resources with parsing_status 'completed' (or parsed_content set)."""
    db = get_db()
    if db is None:
        return None
    coll = db[EVENT_RESOURCES_COLLECTION]
    query: dict[str, Any] = {"company_tag": company_tag}
    if batch:
        query["batch"] = batch
    # Only use resources that have parsed content (excludes pending/failed)
    query["parsed_content"] = {"$exists": True, "$ne": None}
    doc = coll.find_one(
        query,
        sort=[("batch_uploaded_at", -1)],
        projection={"parsed_content": 1, "batch": 1, "batch_uploaded_at": 1},
    )
    return doc


def get_aggregated_resources_for_company(
    company_tag: str,
    batch: str | None = None,
    max_docs: int = 25,
) -> dict[str, Any] | None:
    """
    Merge all completed resource batches for a company tag so generation can use
    full text, image captions, and hosted file URLs together.
    """
    db = get_db()
    if db is None:
        return None
    coll = db[EVENT_RESOURCES_COLLECTION]
    query: dict[str, Any] = {
        "company_tag": company_tag,
        "parsed_content": {"$exists": True, "$ne": None},
    }
    if batch:
        query["batch"] = batch
    cursor = (
        coll.find(
            query,
            projection={
                "parsed_content": 1,
                "batch": 1,
                "batch_uploaded_at": 1,
                "file_urls": 1,
                "file_names": 1,
            },
        )
        .sort("batch_uploaded_at", -1)
        .limit(max_docs)
    )
    docs = list(cursor)
    if not docs:
        return None
    text_blocks: list[str] = []
    all_urls: list[str] = []
    caption_lines: list[str] = []
    for doc in docs:
        pc = doc.get("parsed_content")
        if isinstance(pc, str):
            text_blocks.append(pc)
            continue
        if not isinstance(pc, dict):
            continue
        ft = pc.get("fullText")
        if isinstance(ft, str) and ft.strip():
            text_blocks.append(ft.strip())
        parts = pc.get("parts")
        if isinstance(parts, list):
            for p in parts:
                if not isinstance(p, dict):
                    continue
                fn = str(p.get("filename") or "file")
                tx = p.get("text")
                cap = p.get("image_caption") or p.get("caption")
                if isinstance(cap, str) and cap.strip():
                    caption_lines.append(f"[{fn}] {cap.strip()}")
                elif isinstance(tx, str) and tx.strip() and p.get("is_image"):
                    caption_lines.append(f"[{fn}] {tx.strip()}")
        for u in doc.get("file_urls") or []:
            if isinstance(u, str) and u.strip():
                all_urls.append(u.strip())
    merged_text = "\n\n---\n\n".join(text_blocks)
    if caption_lines:
        merged_text = (
            merged_text
            + "\n\n--- IMAGE / DIAGRAM CAPTIONS ---\n"
            + "\n".join(caption_lines)
        )
    # Dedupe URLs while preserving order
    seen: set[str] = set()
    unique_urls: list[str] = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)
    return {
        "merged_text": merged_text[:80000],
        "file_urls": unique_urls[:80],
        "resource_document_count": len(docs),
        "batches": [str(d.get("batch") or "") for d in docs],
    }
