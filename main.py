import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer

from config import ASSESSMENT_SERVICE_TOKEN
from routers import plan, questions, parse, optimize, single_question

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Assessment Service",
    version="1.0",
    description="Generate assessment plans and questions using Gemini",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(plan.router, prefix="")
app.include_router(questions.router, prefix="")
app.include_router(parse.router, prefix="")
app.include_router(optimize.router, prefix="")
app.include_router(single_question.router, prefix="")


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
