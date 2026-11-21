"""POST /ingest — pull documents from the configured tools and index them."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..connectors.base import ConnectorError
from ..connectors.factory import build_connector
from ..db.session import get_session
from ..embeddings.base import Embedder
from ..ingest.pipeline import ingest_documents
from .deps import embedder_dep

router = APIRouter()


class IngestRequest(BaseModel):
    sources: list[Literal["github", "notion", "discord"]] = ["github", "notion", "discord"]


@router.post("/ingest")
def ingest(
    body: IngestRequest,
    session: Annotated[Session, Depends(get_session)],
    embedder: Annotated[Embedder, Depends(embedder_dep)],
) -> dict:
    settings = get_settings()
    results = {}
    for name in body.sources:
        try:
            connector = build_connector(name, settings)
            results[name] = ingest_documents(session, connector.fetch(), embedder).as_dict()
        except ConnectorError as exc:
            session.rollback()
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ingested": results}
