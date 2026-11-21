"""GET /search — integrated search across all tools, no AI (the 'search-only' mode of the evaluation)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db.session import get_session
from ..embeddings.base import Embedder
from ..retrieval.hybrid import ChunkIndex, HybridRetriever
from .deps import chunk_index_dep, embedder_dep

router = APIRouter()


@router.get("/search")
def search(
    q: Annotated[str, Query(min_length=1, max_length=500)],
    session: Annotated[Session, Depends(get_session)],
    embedder: Annotated[Embedder, Depends(embedder_dep)],
    index: Annotated[ChunkIndex, Depends(chunk_index_dep)],
    top_k: Annotated[int, Query(ge=1, le=30)] = 8,
    expand_links: bool = True,
) -> dict:
    retriever = HybridRetriever(session, embedder, index)
    hits = retriever.search(q, top_k, expand_links=expand_links)
    return {"query": q, "embedding_model": embedder.model_id, "warnings": retriever.warnings,
            "results": [h.as_dict() for h in hits]}
