from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from .db import engine, migrate
from .queue import redis
from .routers import companies, intake, jobs, metrics, scorecard
from .settings import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.app_env != "test":
        migrate()
    yield


app = FastAPI(title="Marketing Engineer API", version="0.0.1", lifespan=lifespan)
app.include_router(companies.router)
app.include_router(jobs.router)
app.include_router(metrics.router)
app.include_router(intake.router)
app.include_router(scorecard.router)


@app.get("/health")
def health():
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
    redis().ping()
    return {"ok": True, "env": settings.app_env, "providers": {
        "llm": settings.llm_provider, "enrichment": settings.enrichment_provider,
        "social": settings.social_provider}}
