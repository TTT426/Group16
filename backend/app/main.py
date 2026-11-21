"""FastAPI entry point:  uvicorn app.main:app --app-dir backend   (or just run start.bat / start.sh)

Pages:  /  (ask / search)   /observer  (evaluation sessions)   /decisions  (decision log)   /docs  (API)
"""

from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from .api import ask, decisions, evaluation, ingest, search
from .config import REPO_ROOT, get_settings
from .db.models import Document
from .db.session import get_session_factory, init_db
from .embeddings.factory import get_embedder
from .qa.service import MODES

WEB_DIR = Path(__file__).parent / "web"
SCENARIO_DIR = REPO_ROOT / "scripts" / "seed_workspace"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # create tables / add new columns on start
    yield


app = FastAPI(title="Group16 Context Engine", version="0.2.0", lifespan=lifespan)
app.include_router(search.router)
app.include_router(ask.router)
app.include_router(ingest.router)
app.include_router(evaluation.router)
app.include_router(decisions.router)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def _page(name: str) -> FileResponse:
    return FileResponse(WEB_DIR / name, headers={"Cache-Control": "no-cache"})


@app.get("/", include_in_schema=False)
def index_page() -> FileResponse:
    return _page("index.html")


@app.get("/observer", include_in_schema=False)
def observer_page() -> FileResponse:
    return _page("observer.html")


@app.get("/decisions", include_in_schema=False)
def decisions_page() -> FileResponse:
    return _page("decisions.html")


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "llm_provider": settings.llm_provider, "embedding_model": get_embedder().model_id}


@app.get("/api/config")
def config() -> dict:
    settings = get_settings()
    with get_session_factory()() as session:
        counts = session.execute(select(Document.source, func.count(Document.id)).group_by(Document.source))
        documents = dict(counts.all())
    scenarios = []
    for path in sorted(SCENARIO_DIR.glob("scenario_*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        scenarios.append({"id": data["id"], "task": data["task"].strip()})
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model or "(CLI default)",
        "qa_mode": settings.qa_mode,
        "qa_modes": list(MODES),
        "embedding_model": get_embedder().model_id,
        "documents": documents,
        "scenarios": scenarios,
    }
