"""Database schema (see docs/PROJECT_PLAN.md §5).

Stored in a single SQLite file. Embeddings are float32 blobs; similarity is computed in memory (retrieval/hybrid.py).
"""

from array import array
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class Float32Vector(TypeDecorator):
    """A list of floats stored as float32 bytes (native byte order; no pgvector needed)."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        packed = array("f", value)
        if packed.itemsize != 4:  # pragma: no cover - every mainstream platform uses 4-byte floats
            raise RuntimeError("float32 storage requires 4-byte C floats")
        return packed.tobytes()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        unpacked = array("f")
        unpacked.frombytes(value)
        return unpacked.tolist()


class Base(DeclarativeBase):
    pass


class Document(Base):
    """One item from a source tool: GitHub issue/PR, Notion page, Discord thread, or confirmed decision."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))  # github | notion | discord | decision
    external_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    raw_json: Mapped[dict | None] = mapped_column(JSON)

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Float32Vector)
    # Which embedder produced `embedding`; search only compares vectors from the same model.
    embedding_model: Mapped[str | None] = mapped_column(String(160), index=True)

    document: Mapped[Document] = relationship(back_populates="chunks")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("eval_sessions.id"))
    question: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(16))  # rag | full | agent
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    sections_json: Mapped[dict | None] = mapped_column(JSON)  # the full answer payload returned to the UI
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CitationLabel(Base):
    """Human judgement: does this cited source really support this answer section? (evaluation metric)"""

    __tablename__ = "citation_labels"
    __table_args__ = (UniqueConstraint("answer_id", "section_index", "source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"), index=True)
    section_index: Mapped[int] = mapped_column(Integer)
    source_id: Mapped[str] = mapped_column(String(255))
    supported: Mapped[bool] = mapped_column(Boolean)
    labeled_by: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    source_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | confirmed
    created_by: Mapped[str] = mapped_column(String(255))
    required_participants: Mapped[list[str]] = mapped_column(JSON, default=list)
    answer_id: Mapped[int | None] = mapped_column(ForeignKey("answers.id"))  # the AI answer it was drafted from
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    confirmations: Mapped[list["DecisionConfirmation"]] = relationship(cascade="all, delete-orphan")


class DecisionConfirmation(Base):
    __tablename__ = "decision_confirmations"
    __table_args__ = (UniqueConstraint("decision_id", "participant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"))
    participant: Mapped[str] = mapped_column(String(255))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvalSession(Base):
    """One participant in one round of the structured-observation study."""

    __tablename__ = "eval_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    pair_id: Mapped[str] = mapped_column(String(32))
    participant: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))  # newcomer | senior
    round: Mapped[str] = mapped_column(String(16))  # baseline | tool
    mode: Mapped[str | None] = mapped_column(String(16))  # ai | search (tool round only)
    scenario: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    senior_questions: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float | None]
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("eval_sessions.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))  # query | answer | source_click | senior_question | ...
    payload: Mapped[dict | None] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
