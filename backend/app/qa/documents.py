"""Read whole documents back from the database.

Only chunks are stored; each chunk starts with a "[Source] title" header line
(see ingest/chunker.py), which is removed when the chunks are joined again.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Chunk, Document


@dataclass
class FullDocument:
    id: int
    source: str
    external_id: str
    url: str
    title: str
    author: str | None
    created_at: datetime | None
    text: str


def _strip_header(chunk_text: str) -> str:
    first, _, rest = chunk_text.partition("\n")
    return rest if first.startswith("[") else chunk_text


def load_documents(session: Session, document_ids: list[int] | None = None) -> list[FullDocument]:
    stmt = select(Document).order_by(Document.source, Document.id)
    if document_ids is not None:
        stmt = stmt.where(Document.id.in_(document_ids))
    docs = list(session.scalars(stmt))
    if not docs:
        return []
    texts: dict[int, list[str]] = {}
    rows = session.execute(
        select(Chunk.document_id, Chunk.text).where(Chunk.document_id.in_([d.id for d in docs]))
        .order_by(Chunk.document_id, Chunk.ordinal)
    )
    for row in rows:
        texts.setdefault(row.document_id, []).append(_strip_header(row.text))
    return [
        FullDocument(d.id, d.source, d.external_id, d.url, d.title, d.author, d.created_at,
                     "\n".join(texts.get(d.id, [])).strip())
        for d in docs
    ]


def corpus_signature(session: Session) -> tuple:
    """Changes whenever documents are added, removed or re-ingested (re-ingest replaces chunk ids)."""
    stmt = select(
        func.count(Chunk.id), func.max(Chunk.id), func.sum(Chunk.id), func.count(func.distinct(Chunk.document_id))
    )
    return tuple(session.execute(stmt).one())
