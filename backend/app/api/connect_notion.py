"""/connect/notion: save the connection's API token, show what it can read, import.

Same rules as the GitHub routes: localhost only, no cross-site requests, the token is never sent back.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import notion_account as notion
from ..config import get_settings
from ..connectors.base import ConnectorError
from ..connectors.factory import build_connector
from ..connectors.scenario import NOTION_URL as SCENARIO_NOTION_URL
from ..db.models import Document
from ..db.session import get_session
from ..embeddings.base import Embedder
from ..envfile import update_env
from ..ingest.pipeline import ingest_documents
from .deps import embedder_dep
from .hub import local_only, page

router = APIRouter(dependencies=[Depends(local_only)], tags=["connect"])
SessionDep = Annotated[Session, Depends(get_session)]


def _status(session: Session, check: dict | None = None) -> dict:
    """What the connect pages show: whether a token is saved, what it can read, how much was imported."""
    token = get_settings().notion_token
    result: dict = {"connected": bool(token), "check": None, "error": None, "documents": 0}
    if token:
        try:
            result["check"] = check or notion.check(token)
        except notion.NotionError as exc:
            result["error"] = str(exc)
        result["documents"] = session.scalar(select(func.count()).select_from(Document).where(
            Document.source == "notion", ~Document.url.startswith(SCENARIO_NOTION_URL))) or 0
    return result


@router.get("/connect/notion", include_in_schema=False)
def notion_page() -> FileResponse:
    return page("connect-notion.html")


@router.get("/api/notion/status")
def status(session: SessionDep) -> dict:
    return _status(session)


class TokenIn(BaseModel):
    token: str


@router.post("/api/notion/token")
def save_token(body: TokenIn, session: SessionDep) -> dict:
    token = body.token.strip()
    try:
        check = notion.check(token)  # valid token: save it even if no pages are shared yet
    except notion.NotionError as exc:
        raise HTTPException(400, str(exc)) from exc
    update_env({"NOTION_TOKEN": token})
    return _status(session, check)


@router.post("/api/notion/disconnect")
def disconnect() -> dict:
    update_env({"NOTION_TOKEN": ""})
    return {"ok": True}


@router.post("/api/notion/import")
def import_notion(session: SessionDep, embedder: Annotated[Embedder, Depends(embedder_dep)]) -> dict:
    try:
        stats = ingest_documents(session, build_connector("notion", get_settings()).fetch(), embedder)
    except ConnectorError as exc:
        session.rollback()
        raise HTTPException(502, str(exc)) from exc
    return {"imported": stats.as_dict()}
