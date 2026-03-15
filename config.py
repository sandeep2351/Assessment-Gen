import os
from dotenv import load_dotenv

load_dotenv()

OPEROUTER_GEMINI_API_KEY = os.getenv("OPEROUTER_GEMINI_API_KEY", "")
MONGODB_URI = os.getenv("MONGODB_URI", "")
ASSESSMENT_SERVICE_TOKEN = os.getenv("ASSESSMENT_SERVICE_TOKEN", "")

# MongoDB database name for event resources (parsed content)
ASSESSMENT_DB_NAME = os.getenv("ASSESSMENT_DB_NAME", "jobParsed")
EVENT_RESOURCES_COLLECTION = os.getenv("EVENT_RESOURCES_COLLECTION", "event_resources")
# Set to "true" in dev if you get SSL: CERTIFICATE_VERIFY_FAILED (e.g. macOS Python)
MONGODB_TLS_INSECURE = os.getenv("MONGODB_TLS_INSECURE", "").lower() in ("1", "true", "yes")
