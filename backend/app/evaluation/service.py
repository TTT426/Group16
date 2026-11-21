"""Structured-observation study (CP1 §4): sessions, event log, metrics and CSV export.

Metrics per session map directly to the minimum evidence thresholds:
time to complete, questions asked to the senior member, answer score (against the answer key),
whether source links were opened, and the share of cited sources that really support the answer.
"""

import csv
import io
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Answer, CitationLabel, EvalSession, Event

ROLES = ("newcomer", "senior")
ROUNDS = ("baseline", "tool")
TOOL_MODES = ("ai", "search")


class EvalError(ValueError):
    pass


def create_session(session: Session, *, pair_id: str, participant: str, role: str, round: str,
                   scenario: str, mode: str | None = None) -> EvalSession:
    if role not in ROLES or round not in ROUNDS:
        raise EvalError(f"role must be one of {ROLES}, round one of {ROUNDS}.")
    if round == "tool" and mode not in TOOL_MODES:
        raise EvalError(f"A tool round needs mode {TOOL_MODES}.")
    row = EvalSession(pair_id=pair_id.strip(), participant=participant.strip(), role=role, round=round,
                      scenario=scenario.strip(), mode=mode if round == "tool" else None)
    session.add(row)
    session.commit()
    return row


def get(session: Session, session_id: int) -> EvalSession:
    row = session.get(EvalSession, session_id)
    if row is None:
        raise EvalError(f"Session {session_id} not found.")
    return row


def start(session: Session, session_id: int) -> EvalSession:
    row = get(session, session_id)
    row.started_at = datetime.now(UTC)
    row.ended_at = None
    log_event(session, session_id, "start", {})
    return row


def end(session: Session, session_id: int) -> EvalSession:
    row = get(session, session_id)
    if row.started_at is None:
        raise EvalError("Session has not been started.")
    row.ended_at = datetime.now(UTC)
    log_event(session, session_id, "end", {})
    return row


def update(session: Session, session_id: int, *, senior_delta: int = 0, score: float | None = None,
           notes: str | None = None) -> EvalSession:
    row = get(session, session_id)
    if senior_delta:
        row.senior_questions = max(0, (row.senior_questions or 0) + senior_delta)
        log_event(session, session_id, "senior_question", {"delta": senior_delta}, commit=False)
    if score is not None:
        row.score = score
    if notes is not None:
        row.notes = notes
    session.commit()
    return row


def log_event(session: Session, session_id: int | None, type_: str, payload: dict, *, commit: bool = True) -> None:
    if session_id is None:
        return
    if session.get(EvalSession, session_id) is None:
        return  # unknown session id from a stale link: ignore rather than fail the user's request
    session.add(Event(session_id=session_id, type=type_, payload=payload))
    if commit:
        session.commit()


def set_labels(session: Session, answer_id: int, labels: list[dict], labeled_by: str | None = None) -> int:
    if session.get(Answer, answer_id) is None:
        raise EvalError(f"Answer {answer_id} not found.")
    count = 0
    for label in labels:
        key = (answer_id, int(label["section_index"]), str(label["source_id"]))
        row = session.scalar(select(CitationLabel).where(
            CitationLabel.answer_id == key[0], CitationLabel.section_index == key[1],
            CitationLabel.source_id == key[2]))
        if row is None:
            row = CitationLabel(answer_id=key[0], section_index=key[1], source_id=key[2], supported=False)
            session.add(row)
        row.supported = bool(label["supported"])
        row.labeled_by = labeled_by
        count += 1
    session.commit()
    return count


def support_rate(session: Session, session_id: int | None = None) -> tuple[int, int]:
    """(supported, labelled) over citation labels, optionally limited to one session's answers."""
    stmt = select(CitationLabel.supported)
    if session_id is not None:
        stmt = stmt.join(Answer, Answer.id == CitationLabel.answer_id).where(Answer.session_id == session_id)
    values = list(session.scalars(stmt))
    return sum(1 for v in values if v), len(values)


def metrics(session: Session, row: EvalSession) -> dict:
    events = list(session.scalars(select(Event).where(Event.session_id == row.id)))
    counts: dict[str, int] = {}
    for e in events:
        counts[e.type] = counts.get(e.type, 0) + 1
    duration = None
    if row.started_at and row.ended_at:
        started, ended = _aware(row.started_at), _aware(row.ended_at)
        duration = round((ended - started).total_seconds(), 1)
    supported, labelled = support_rate(session, row.id)
    return {
        "id": row.id,
        "pair_id": row.pair_id,
        "participant": row.participant,
        "role": row.role,
        "round": row.round,
        "mode": row.mode or "",
        "scenario": row.scenario,
        "started_at": row.started_at.isoformat() if row.started_at else "",
        "ended_at": row.ended_at.isoformat() if row.ended_at else "",
        "duration_s": duration,
        "senior_questions": row.senior_questions or 0,
        "score": row.score,
        "ai_questions": counts.get("ask", 0),
        "searches": counts.get("search", 0),
        "source_clicks": counts.get("source_click", 0),
        "opened_sources": counts.get("source_click", 0) > 0,
        "citations_labelled": labelled,
        "citations_supported": supported,
        "citation_support_rate": round(supported / labelled, 3) if labelled else None,
        "notes": row.notes or "",
    }


def list_metrics(session: Session) -> list[dict]:
    rows = session.scalars(select(EvalSession).order_by(EvalSession.pair_id, EvalSession.id))
    return [metrics(session, r) for r in rows]


def export_csv(session: Session) -> str:
    rows = list_metrics(session)
    out = io.StringIO()
    fields = list(rows[0]) if rows else ["id", "pair_id", "participant", "role", "round", "mode", "scenario",
                                         "duration_s", "senior_questions", "score"]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
