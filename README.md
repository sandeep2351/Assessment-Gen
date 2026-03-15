# Assessment Service

Python microservice for generating assessment plans and questions using Google Gemini. Used by Vishnu Placements backend.

## Endpoints

- `POST /generate-plan` – Generate assessment plan from job description (Bearer token required)
- `POST /generate-questions` – Generate questions from plan; uses latest batch parsed resources for `company_tag` from MongoDB
- `POST /parse-resource` – Parse uploaded file (PDF/DOCX) and return extracted text as JSON (Bearer token required)
- `GET /health` – Health check

## Setup

```bash
cd assessment_service
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env: GEMINI_API_KEY, MONGODB_URI, ASSESSMENT_SERVICE_TOKEN
uvicorn main:app --host 0.0.0.0 --port 8001
```

## Environment

- `GEMINI_API_KEY` – Google Gemini API key
- `MONGODB_URI` – MongoDB connection (to read `event_resources` parsed_content)
- `ASSESSMENT_SERVICE_TOKEN` – Bearer token for API auth. **Use the same value as in Vishnu .env**; generate once and keep for the whole lifecycle (see Vishnu `.env.example`).
- `ASSESSMENT_DB_NAME` – Database name (default: jobParsed)
- `EVENT_RESOURCES_COLLECTION` – Collection for event resources (default: event_resources)
