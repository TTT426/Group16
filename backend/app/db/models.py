"""Database schema (see docs/PROJECT_PLAN.md §5)."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ..config import get_settings

EMBEDDING_DIM = get_settings().embedding_dim


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
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    document: Mapped[Document] = relationship(back_populates="chunks")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("eval_sessions.id"))
    question: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(16))  # ai | search
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    sections_json: Mapped[dict | None] = mapped_column(JSON)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

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


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("eval_sessions.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))  # query | answer | source_click | senior_question | ...
    payload: Mapped[dict | None] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
