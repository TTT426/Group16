"""FastAPI entry point:  uvicorn app.main:app --reload --app-dir backend"""

from fastapi import FastAPI

from .api import ingest, search
from .config import get_settings

app = FastAPI(title="Group16 Context Engine", version="0.1.0")
app.include_router(search.router)
app.include_router(ingest.router)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "llm_provider": settings.llm_provider, "embedding_provider": settings.embedding_provider}
