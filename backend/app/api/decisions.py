"""/api/decisions — draft (by AI), edit and confirm (by people) decision records."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db.session import get_session
from ..decisions import service as ds
from ..embeddings.base import Embedder
from ..llm.base import LLMProvider
from .deps import embedder_dep, llm_dep

router = APIRouter(prefix="/api/decisions")
DB = Annotated[Session, Depends(get_session)]


class DraftRequest(BaseModel):
    answer_id: int
    created_by: str = Field(min_length=1, max_length=255)
    participants: list[str] = Field(min_length=1)


class ManualRequest(BaseModel):
    title: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    context: str = ""
    rationale: str = ""
    created_by: str = Field(min_length=1, max_length=255)
    participants: list[str] = Field(min_length=1)
    source_urls: list[str] = []


class UpdateRequest(BaseModel):
    title: str | None = None
    context: str | None = None
    decision: str | None = None
    rationale: str | None = None
    required_participants: list[str] | None = None


class ConfirmRequest(BaseModel):
    participant: str = Field(min_length=1, max_length=255)


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ds.DecisionError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("")
def list_decisions(session: DB) -> list[dict]:
    return [ds.to_dict(d) for d in ds.list_all(session)]


@router.post("/draft")
async def draft(body: DraftRequest, session: DB, provider: Annotated[LLMProvider, Depends(llm_dep)]) -> dict:
    try:
        decision = await ds.draft_from_answer(session, provider, body.answer_id, created_by=body.created_by,
                                              participants=body.participants)
    except ds.DecisionError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ds.to_dict(decision)


@router.post("")
def create(body: ManualRequest, session: DB) -> dict:
    return ds.to_dict(_run(ds.create_manual, session, title=body.title, decision_text=body.decision,
                           context=body.context, rationale=body.rationale, created_by=body.created_by,
                           participants=body.participants, source_urls=body.source_urls))


@router.patch("/{decision_id}")
def update(decision_id: int, body: UpdateRequest, session: DB) -> dict:
    return ds.to_dict(_run(ds.update, session, decision_id, body.model_dump(exclude_none=True)))


@router.post("/{decision_id}/confirm")
def confirm(decision_id: int, body: ConfirmRequest, session: DB,
            embedder: Annotated[Embedder, Depends(embedder_dep)]) -> dict:
    return ds.to_dict(_run(ds.confirm, session, decision_id, body.participant, embedder))


@router.get("/export.md", response_class=PlainTextResponse)
def export(session: DB) -> PlainTextResponse:
    return PlainTextResponse(ds.to_markdown(ds.list_all(session)), media_type="text/markdown; charset=utf-8")
