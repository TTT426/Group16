"""Store normalized documents: upsert by (source, external_id), re-chunk and re-embed."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors.base import NormalizedDocument
from ..db.models import Chunk, Document
from ..embeddings.base import Embedder
from .chunker import chunk_document


@dataclass
class IngestStats:
    documents: int = 0
    chunks: int = 0
    by_source: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict:
        return {"documents": self.documents, "chunks": self.chunks, "by_source": dict(self.by_source)}


def ingest_documents(
    session: Session, docs: Iterable[NormalizedDocument], embedder: Embedder, *, max_chars: int = 1200
) -> IngestStats:
    stats = IngestStats()
    for doc in docs:
        row = session.scalar(
            select(Document).where(Document.source == doc.source, Document.external_id == doc.external_id)
        )
        if row is None:
            row = Document(source=doc.source, external_id=doc.external_id)
            session.add(row)
        row.url = doc.url
        row.title = doc.title
        row.author = doc.author
        row.created_at = doc.created_at
        row.raw_json = doc.raw

        texts = chunk_document(doc, max_chars=max_chars)
        vectors = embedder.embed(texts)
        pairs = zip(texts, vectors, strict=True)
        row.chunks = [Chunk(ordinal=i, text=t, embedding=v) for i, (t, v) in enumerate(pairs)]

        stats.documents += 1
        stats.chunks += len(texts)
        stats.by_source[doc.source] += 1
    session.commit()
    return stats
