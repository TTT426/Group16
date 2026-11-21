"""Decision log: the AI drafts, people edit and confirm, confirmed decisions become searchable.

Human-AI boundary (CP1): a decision record is saved as confirmed only after every participant
of the discussion has confirmed it. Until then it can be edited freely.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..connectors.base import NormalizedDocument
from ..db.models import Answer, Decision, DecisionConfirmation
from ..embeddings.base import Embedder
from ..ingest.pipeline import ingest_documents
from ..llm.base import LLMError, LLMProvider
from ..llm.json_utils import extract_json_object
from ..qa import prompts
from ..qa.citations import Source

EDITABLE_FIELDS = ("title", "context", "decision", "rationale", "required_participants")


class DecisionError(ValueError):
    pass


def decision_url(decision_id: int) -> str:
    return f"/decisions#d{decision_id}"


def to_dict(decision: Decision) -> dict:
    confirmed_by = sorted(c.participant for c in decision.confirmations)
    return {
        "id": decision.id,
        "title": decision.title,
        "context": decision.context,
        "decision": decision.decision,
        "rationale": decision.rationale,
        "source_urls": decision.source_urls or [],
        "status": decision.status,
        "created_by": decision.created_by,
        "required_participants": decision.required_participants or [],
        "confirmed_by": confirmed_by,
        "waiting_for": [p for p in decision.required_participants or [] if p not in confirmed_by],
        "answer_id": decision.answer_id,
        "url": decision_url(decision.id),
        "created_at": decision.created_at.isoformat() if decision.created_at else None,
        "confirmed_at": decision.confirmed_at.isoformat() if decision.confirmed_at else None,
    }


def _clean_participants(names: list[str]) -> list[str]:
    seen: list[str] = []
    for name in names:
        name = name.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


async def draft_from_answer(
    session: Session, provider: LLMProvider, answer_id: int, *, created_by: str, participants: list[str]
) -> Decision:
    answer = session.get(Answer, answer_id)
    if answer is None or not answer.sections_json:
        raise DecisionError(f"Answer {answer_id} not found.")
    payload = answer.sections_json
    participants = _clean_participants(participants or [created_by])
    if not participants:
        raise DecisionError("At least one participant is required.")
    answer_text = "\n".join(s["text"] for s in payload.get("sections", []))
    sources = [
        Source(s["id"], s["document_id"], s["source"], s["url"], s["title"], s.get("author"), s.get("snippet", ""))
        for s in payload.get("sources", [])
    ]

    draft = {"title": answer.question[:120], "context": answer.question, "decision": answer_text, "rationale": ""}
    try:
        result = await provider.generate(prompts.SYSTEM_DECISION,
                                         prompts.decision_prompt(answer.question, answer_text, sources),
                                         json_schema=prompts.DECISION_SCHEMA)
        parsed = extract_json_object(result.text)
        draft.update({k: str(parsed[k]).strip() for k in ("title", "context", "decision", "rationale")
                      if parsed.get(k)})
    except (LLMError, ValueError):
        pass  # keep the plain draft built from the answer; people edit it anyway

    decision = Decision(
        title=draft["title"], context=draft["context"], decision=draft["decision"], rationale=draft["rationale"],
        source_urls=[s.url for s in sources], status="pending", created_by=created_by.strip() or participants[0],
        required_participants=participants, answer_id=answer_id,
    )
    session.add(decision)
    session.commit()
    return decision


def create_manual(session: Session, *, title: str, decision_text: str, context: str = "", rationale: str = "",
                  created_by: str, participants: list[str], source_urls: list[str] | None = None) -> Decision:
    participants = _clean_participants(participants or [created_by])
    if not title.strip() or not decision_text.strip() or not participants:
        raise DecisionError("title, decision and at least one participant are required.")
    decision = Decision(title=title.strip(), context=context, decision=decision_text.strip(), rationale=rationale,
                        source_urls=source_urls or [], status="pending", created_by=created_by.strip(),
                        required_participants=participants)
    session.add(decision)
    session.commit()
    return decision


def update(session: Session, decision_id: int, changes: dict) -> Decision:
    decision = _get(session, decision_id)
    if decision.status != "pending":
        raise DecisionError("Confirmed decisions cannot be edited; create a new decision instead.")
    for key, value in changes.items():
        if key not in EDITABLE_FIELDS or value is None:
            continue
        setattr(decision, key, _clean_participants(value) if key == "required_participants" else str(value))
    # Any edit invalidates earlier confirmations: people confirmed a different text.
    decision.confirmations.clear()
    session.commit()
    return decision


def confirm(session: Session, decision_id: int, participant: str, embedder: Embedder) -> Decision:
    decision = _get(session, decision_id)
    participant = participant.strip()
    if participant not in (decision.required_participants or []):
        raise DecisionError(f"{participant!r} is not a participant of this decision.")
    if decision.status == "pending" and participant not in {c.participant for c in decision.confirmations}:
        decision.confirmations.append(DecisionConfirmation(participant=participant))
        session.flush()
    confirmed_by = {c.participant for c in decision.confirmations}
    if decision.status == "pending" and set(decision.required_participants) <= confirmed_by:
        decision.status = "confirmed"
        decision.confirmed_at = datetime.now(UTC)
        session.commit()
        ingest_documents(session, [as_document(decision)], embedder)  # feeds back into search and Q&A
    else:
        session.commit()
    return decision


def as_document(decision: Decision) -> NormalizedDocument:
    text = "\n\n".join(part for part in (
        f"決策：{decision.title}",
        f"背景：{decision.context}" if decision.context else "",
        f"決定：{decision.decision}",
        f"理由：{decision.rationale}" if decision.rationale else "",
        f"參與者：{', '.join(decision.required_participants or [])}",
        "來源：\n" + "\n".join(decision.source_urls) if decision.source_urls else "",
    ) if part)
    return NormalizedDocument(
        source="decision", external_id=f"decision:{decision.id}", url=decision_url(decision.id),
        title=f"決策紀錄：{decision.title}", author=decision.created_by, created_at=decision.confirmed_at, text=text,
    )


def to_markdown(decisions: list[Decision]) -> str:
    """Same layout as the repo's DECISIONS.md, so confirmed records can be pasted there."""
    blocks = ["# Decisions Log (exported)"]
    for d in decisions:
        date = (d.confirmed_at or d.created_at or datetime.now(UTC)).date().isoformat()
        status = "已確認" if d.status == "confirmed" else "待確認"
        lines = [f"## {date} — {d.title}（{status}）", f"**What:** {d.decision}"]
        if d.rationale:
            lines.append(f"**Why:** {d.rationale}")
        if d.context:
            lines.append(f"**Context:** {d.context}")
        lines.append(f"**Participants:** {', '.join(d.required_participants or [])}")
        if d.source_urls:
            lines.append("**Sources:** " + " ".join(d.source_urls))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def list_all(session: Session) -> list[Decision]:
    return list(session.scalars(select(Decision).order_by(Decision.id.desc())))


def _get(session: Session, decision_id: int) -> Decision:
    decision = session.get(Decision, decision_id)
    if decision is None:
        raise DecisionError(f"Decision {decision_id} not found.")
    return decision
