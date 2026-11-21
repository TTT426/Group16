"""FastAPI entry point:  uvicorn app.main:app --app-dir backend   (or just run start.bat / start.sh)"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from .api import ingest, search
from .config import get_settings
from .db.session import init_db
from .embeddings.factory import get_embedder
from .llm.factory import resolve_provider_name


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # create tables on first start
    yield


app = FastAPI(title="Group16 Context Engine", version="0.1.0", lifespan=lifespan)
app.include_router(search.router)
app.include_router(ingest.router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/docs")


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "llm_provider": resolve_provider_name(settings),
        "embedding_model": get_embedder().model_id,
    }
