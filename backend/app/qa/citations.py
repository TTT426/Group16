"""Validate the model's citations against the sources it was actually given."""

from collections import Counter
from dataclasses import asdict, dataclass, field

CONFIDENCE = {"high", "medium", "low"}


@dataclass
class Source:
    id: str  # "S1" (rag / full) or a workspace file path (agent)
    document_id: int
    source: str  # github | notion | discord | decision
    url: str
    title: str
    author: str | None
    text: str

    def public(self, snippet_chars: int = 280) -> dict:
        data = asdict(self)
        text = " ".join(self.text.split())
        data["snippet"] = text[:snippet_chars] + ("…" if len(text) > snippet_chars else "")
        del data["text"]
        return data


@dataclass
class Section:
    text: str
    sources: list[str]
    supported: bool  # at least one valid citation


@dataclass
class CheckedAnswer:
    sections: list[Section]
    cited: list[Source]  # in order of first citation
    unanswerable: bool
    confidence: str
    missing: str
    suggested_contacts: list[str] = field(default_factory=list)
    dropped_citations: list[str] = field(default_factory=list)


def check_answer(raw: dict, sources: dict[str, Source], *, resolve=None) -> CheckedAnswer:
    """`resolve(cited_id) -> Source | None` handles ids not in `sources` (agent mode: file paths)."""
    sections: list[Section] = []
    cited: dict[str, Source] = {}
    dropped: list[str] = []
    for item in raw.get("sections") or []:
        if isinstance(item, str):
            item = {"text": item, "sources": []}
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        valid: list[str] = []
        for ref in item.get("sources") or []:
            ref = str(ref).strip().strip("[]")
            source = sources.get(ref) or (resolve(ref) if resolve else None)
            if source is None:
                dropped.append(ref)
                continue
            if source.id not in valid:
                valid.append(source.id)
            cited.setdefault(source.id, source)
        sections.append(Section(text=text, sources=valid, supported=bool(valid)))

    confidence = str(raw.get("confidence") or "").lower()
    unanswerable = bool(raw.get("unanswerable")) or not sections
    return CheckedAnswer(
        sections=sections,
        cited=list(cited.values()),
        unanswerable=unanswerable,
        confidence=confidence if confidence in CONFIDENCE else "low",
        missing=str(raw.get("missing") or "").strip(),
        suggested_contacts=suggest_contacts(list(cited.values()) or list(sources.values())),
        dropped_citations=dropped,
    )


def suggest_contacts(sources: list[Source], limit: int = 3) -> list[str]:
    """People who wrote the relevant material: a suggestion of whom to ask. The human decides."""
    counts = Counter(s.author for s in sources if s.author)
    return [name for name, _ in counts.most_common(limit)]
