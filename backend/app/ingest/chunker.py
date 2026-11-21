"""Split documents into retrieval chunks.

Text is split on the coarsest separator that keeps pieces under `max_chars`
(blank line → line → sentence → space → hard cut), then neighbouring pieces are
packed back together. Every chunk starts with a short header naming the source
and title, so a chunk stays understandable on its own.
"""

from ..connectors.base import NormalizedDocument

SOURCE_LABELS = {"github": "GitHub", "notion": "Notion", "discord": "Discord", "decision": "Decision log"}
_SEPARATORS = ("\n\n", "\n", "。", ". ", " ")


def split_text(text: str, max_chars: int, separators: tuple[str, ...] = _SEPARATORS) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    for i, sep in enumerate(separators):
        if sep not in text:
            continue
        pieces: list[str] = []
        current = ""
        for part in text.split(sep):
            candidate = f"{current}{sep}{part}" if current else part
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    pieces.append(current)
                current = part
        if current:
            pieces.append(current)
        out: list[str] = []
        for piece in pieces:
            out.extend(split_text(piece, max_chars, separators[i + 1 :]) if len(piece) > max_chars else [piece])
        return [p.strip() for p in out if p.strip()]
    return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]


def chunk_document(doc: NormalizedDocument, max_chars: int = 1200) -> list[str]:
    header = f"[{SOURCE_LABELS.get(doc.source, doc.source)}] {doc.title}".strip()
    body = doc.text
    if body.startswith(doc.title):  # most connectors repeat the title as the first line
        body = body[len(doc.title) :]
    pieces = split_text(body, max_chars) or [""]
    return [f"{header}\n{piece}".strip() for piece in pieces]
