"""Hybrid retrieval: BM25 keyword search + pgvector semantic search, fused with RRF.

After fusion, results are diversified so every source tool that produced a
candidate keeps at least one slot, then cross-tool links are expanded.
"""

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from threading import Lock

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Chunk, Document
from ..embeddings.base import Embedder
from .bm25 import BM25
from .linker import DocRef, find_references, github_repo_of
from .tokenize import tokenize

RRF_K = 60


@dataclass
class SearchHit:
    chunk_id: int
    document_id: int
    source: str
    url: str
    title: str
    author: str | None
    created_at: datetime | None
    text: str
    score: float
    matched_by: list[str] = field(default_factory=list)  # keyword | vector | link

    def as_dict(self) -> dict:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat() if self.created_at else None
        return data


class KeywordIndex:
    """In-memory BM25 over all chunks, rebuilt when the chunk table changes."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._signature: tuple | None = None
        self._ids: list[int] = []
        self._bm25: BM25 | None = None

    def search(self, session: Session, query: str, limit: int) -> list[int]:
        self._refresh(session)
        if not self._bm25:
            return []
        scores = self._bm25.scores(tokenize(query))
        ranked = sorted(((s, cid) for s, cid in zip(scores, self._ids, strict=True) if s > 0), reverse=True)
        return [cid for _, cid in ranked[:limit]]

    def _refresh(self, session: Session) -> None:
        signature = tuple(session.execute(select(func.count(Chunk.id), func.max(Chunk.id), func.sum(Chunk.id))).one())
        with self._lock:
            if signature == self._signature:
                return
            rows = session.execute(select(Chunk.id, Chunk.text).order_by(Chunk.id)).all()
            self._ids = [r.id for r in rows]
            self._bm25 = BM25([tokenize(r.text) for r in rows]) if rows else None
            self._signature = signature


class HybridRetriever:
    def __init__(self, session: Session, embedder: Embedder, keyword_index: KeywordIndex, *, candidates: int = 30):
        self.session = session
        self.embedder = embedder
        self.keyword_index = keyword_index
        self.candidates = candidates

    def search(self, query: str, top_k: int = 8, *, expand_links: bool = True, max_link_expansions: int = 4):
        keyword_ids = self.keyword_index.search(self.session, query, self.candidates)
        vector_ids = self._vector_search(query)

        fused: Counter[int] = Counter()
        matched: dict[int, list[str]] = {}
        for label, ids in (("keyword", keyword_ids), ("vector", vector_ids)):
            for rank, cid in enumerate(ids):
                fused[cid] += 1.0 / (RRF_K + rank + 1)
                matched.setdefault(cid, []).append(label)
        ranked = [cid for cid, _ in fused.most_common()]
        if not ranked:
            return []

        rows = self._load_chunks(ranked)
        selected = self._diversify(ranked, rows, top_k)
        hits = [self._hit(rows[cid], fused[cid], matched[cid]) for cid in selected]
        if expand_links:
            hits += self._expand_links(hits, max_link_expansions)
        return hits

    # -- steps ---------------------------------------------------------------------

    def _vector_search(self, query: str) -> list[int]:
        vector = self.embedder.embed_query(query)
        distance = Chunk.embedding.cosine_distance(vector)
        stmt = select(Chunk.id).where(Chunk.embedding.is_not(None)).order_by(distance).limit(self.candidates)
        return list(self.session.scalars(stmt))

    def _load_chunks(self, chunk_ids: list[int]) -> dict:
        stmt = (
            select(Chunk.id, Chunk.text, Chunk.document_id, Document.source, Document.url, Document.title,
                   Document.author, Document.created_at)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.id.in_(chunk_ids))
        )
        return {row.id: row for row in self.session.execute(stmt)}

    @staticmethod
    def _diversify(ranked: list[int], rows: dict, top_k: int) -> list[int]:
        selected = ranked[:top_k]
        counts = Counter(rows[cid].source for cid in selected)
        for cid in ranked[top_k:]:
            source = rows[cid].source
            if counts[source]:
                continue
            # Replace the lowest-ranked hit whose source is over-represented.
            for i in range(len(selected) - 1, -1, -1):
                if counts[rows[selected[i]].source] > 1:
                    counts[rows[selected[i]].source] -= 1
                    selected[i] = cid
                    counts[source] += 1
                    break
        return sorted(selected, key=ranked.index)

    @staticmethod
    def _hit(row, score: float, matched_by: list[str]) -> SearchHit:
        return SearchHit(
            chunk_id=row.id, document_id=row.document_id, source=row.source, url=row.url, title=row.title,
            author=row.author, created_at=row.created_at, text=row.text, score=score, matched_by=list(matched_by),
        )

    def _expand_links(self, hits: list[SearchHit], limit: int) -> list[SearchHit]:
        seen_docs = {h.document_id for h in hits}
        extra: list[SearchHit] = []
        for hit in hits:
            for ref in find_references(hit.text, source=hit.source):
                if len(extra) >= limit:
                    return extra
                doc_id = self._resolve(ref, citing_url=hit.url)
                if doc_id is None or doc_id in seen_docs:
                    continue
                row = self.session.execute(
                    select(Chunk.id, Chunk.text, Chunk.document_id, Document.source, Document.url, Document.title,
                           Document.author, Document.created_at)
                    .join(Document, Document.id == Chunk.document_id)
                    .where(Chunk.document_id == doc_id)
                    .order_by(Chunk.ordinal)
                    .limit(1)
                ).first()
                if row:
                    seen_docs.add(doc_id)
                    extra.append(self._hit(row, hit.score * 0.5, ["link"]))
        return extra

    def _resolve(self, ref: DocRef, *, citing_url: str) -> int | None:
        rows = self.session.execute(
            select(Document.id, Document.url)
            .where(Document.source == ref.source, Document.external_id.in_(ref.external_ids))
        ).all()
        if ref.source == "github":
            repo = ref.repo or github_repo_of(citing_url)
            rows = [r for r in rows if repo is None or github_repo_of(r.url) == repo]
        return rows[0].id if rows else None
