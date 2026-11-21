"""POST /ask — AI answer with cited sources.  GET /go — open a source link (and log the click)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.models import Answer, Document, EvalSession
from ..db.session import get_session
from ..embeddings.base import Embedder
from ..evaluation.service import log_event
from ..llm.base import LLMError, LLMProvider
from ..qa.service import QAError, QAService
from ..qa.workspace import WorkspaceExport
from ..retrieval.hybrid import ChunkIndex
from .deps import chunk_index_dep, embedder_dep, llm_dep, workspace_dep

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    mode: Literal["rag", "full", "agent"] | None = None
    session_id: int | None = None


@router.post("/ask")
async def ask(
    body: AskRequest,
    session: Annotated[Session, Depends(get_session)],
    embedder: Annotated[Embedder, Depends(embedder_dep)],
    index: Annotated[ChunkIndex, Depends(chunk_index_dep)],
    provider: Annotated[LLMProvider, Depends(llm_dep)],
    workspace: Annotated[WorkspaceExport, Depends(workspace_dep)],
) -> dict:
    service = QAService(session, embedder, index, provider, get_settings(), workspace)
    try:
        result = await service.answer(body.question.strip(), body.mode)
    except LLMError as exc:
        raise HTTPException(503, f"無法使用 Claude CLI：{exc}") from exc
    except QAError as exc:
        raise HTTPException(502, str(exc)) from exc

    session_id = body.session_id if body.session_id and session.get(EvalSession, body.session_id) else None
    answer = Answer(session_id=session_id, question=result.question, mode=result.mode, provider=result.provider,
                    model=result.model, sections_json=result.as_dict(), latency_ms=result.latency_ms)
    session.add(answer)
    session.commit()
    log_event(session, session_id, "ask", {"answer_id": answer.id, "question": result.question, "mode": result.mode,
                                           "latency_ms": result.latency_ms, "unanswerable": result.unanswerable})
    return {"answer_id": answer.id, **result.as_dict()}


@router.get("/go")
def go(
    url: Annotated[str, Query(min_length=1, max_length=2000)],
    session: Annotated[Session, Depends(get_session)],
    session_id: int | None = None,
    answer_id: int | None = None,
    source_id: str | None = None,
) -> RedirectResponse:
    """Redirect to a source the tool showed, logging the click (CP1: did the user verify the answer?).

    Only URLs of indexed documents (or this app's decision pages) are allowed, so this is not an open redirect.
    """
    known = url.startswith("/decisions") or session.scalar(select(Document.id).where(Document.url == url))
    if not known:
        raise HTTPException(404, "Unknown source URL.")
    log_event(session, session_id, "source_click", {"url": url, "answer_id": answer_id, "source_id": source_id})
    return RedirectResponse(url, status_code=302)
