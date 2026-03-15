import logging
from typing import Any

from pymongo import MongoClient
from config import MONGODB_URI, ASSESSMENT_DB_NAME, EVENT_RESOURCES_COLLECTION

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
            _client = MongoClient(MONGODB_URI)
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
    if not client:
        return None
    _db = client[ASSESSMENT_DB_NAME]
    return _db


def get_latest_parsed_for_company(company_tag: str, batch: str | None = None) -> dict[str, Any] | None:
    """Get latest batch parsed content for company. Only uses resources with parsing_status 'completed' (or parsed_content set)."""
    db = get_db()
    if not db:
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
