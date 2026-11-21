"""/api/eval — sessions for the structured-observation study, citation labelling and CSV export."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Answer, CitationLabel
from ..db.session import get_session
from ..evaluation import service as ev

router = APIRouter(prefix="/api/eval")
DB = Annotated[Session, Depends(get_session)]


class SessionCreate(BaseModel):
    pair_id: str = Field(min_length=1, max_length=32)
    participant: str = Field(min_length=1, max_length=255)
    role: Literal["newcomer", "senior"] = "newcomer"
    round: Literal["baseline", "tool"]
    mode: Literal["ai", "search"] | None = None
    scenario: str = Field(min_length=1, max_length=64)


class SessionUpdate(BaseModel):
    senior_delta: int = 0
    score: float | None = None
    notes: str | None = None


class Label(BaseModel):
    section_index: int
    source_id: str
    supported: bool


class LabelRequest(BaseModel):
    labels: list[Label]
    labeled_by: str | None = None


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ev.EvalError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/sessions")
def create(body: SessionCreate, session: DB) -> dict:
    row = _run(ev.create_session, session, **body.model_dump())
    return ev.metrics(session, row)


@router.get("/sessions")
def list_sessions(session: DB) -> list[dict]:
    return ev.list_metrics(session)


@router.get("/sessions/{session_id}")
def get_session_metrics(session_id: int, session: DB) -> dict:
    return ev.metrics(session, _run(ev.get, session, session_id))


@router.post("/sessions/{session_id}/start")
def start(session_id: int, session: DB) -> dict:
    return ev.metrics(session, _run(ev.start, session, session_id))


@router.post("/sessions/{session_id}/end")
def end(session_id: int, session: DB) -> dict:
    return ev.metrics(session, _run(ev.end, session, session_id))


@router.patch("/sessions/{session_id}")
def update(session_id: int, body: SessionUpdate, session: DB) -> dict:
    return ev.metrics(session, _run(ev.update, session, session_id, **body.model_dump()))


@router.get("/export.csv", response_class=PlainTextResponse)
def export(session: DB) -> PlainTextResponse:
    # BOM so Excel opens the Chinese text correctly.
    return PlainTextResponse("﻿" + ev.export_csv(session), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="evaluation.csv"'})


@router.get("/answers")
def answers(session: DB, session_id: int | None = None) -> list[dict]:
    stmt = select(Answer).order_by(Answer.id.desc())
    if session_id is not None:
        stmt = stmt.where(Answer.session_id == session_id)
    out = []
    for answer in session.scalars(stmt.limit(200)):
        labels = session.scalars(select(CitationLabel).where(CitationLabel.answer_id == answer.id))
        payload = answer.sections_json or {}
        out.append({
            "id": answer.id, "session_id": answer.session_id, "question": answer.question, "mode": answer.mode,
            "created_at": answer.created_at.isoformat() if answer.created_at else None,
            "sections": payload.get("sections", []), "sources": payload.get("sources", []),
            "labels": [{"section_index": lb.section_index, "source_id": lb.source_id, "supported": lb.supported}
                       for lb in labels],
        })
    return out


@router.post("/answers/{answer_id}/labels")
def label(answer_id: int, body: LabelRequest, session: DB) -> dict:
    count = _run(ev.set_labels, session, answer_id, [lb.model_dump() for lb in body.labels], body.labeled_by)
    supported, labelled = ev.support_rate(session)
    return {"saved": count, "overall_supported": supported, "overall_labelled": labelled}


@router.get("/summary")
def summary(session: DB) -> dict:
    supported, labelled = ev.support_rate(session)
    return {
        "sessions": len(ev.list_metrics(session)),
        "citations_labelled": labelled,
        "citations_supported": supported,
        "citation_support_rate": round(supported / labelled, 3) if labelled else None,
        "threshold": 0.8,  # CP1 minimum evidence threshold
    }
