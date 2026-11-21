"""Export the indexed project as a folder of markdown files for the `agent` QA mode.

Claude Code searches that folder itself with its read-only Grep / Glob / Read tools
("let the LLM search the project directly"). Each file starts with a small header
(title, source, url, author) so citations can be mapped back to the original link.
The export is rebuilt only when the indexed documents change.
"""

import json
import re
import shutil
from pathlib import Path
from threading import Lock

from sqlalchemy.orm import Session

from .documents import FullDocument, corpus_signature, load_documents

INDEX_FILE = "_index.json"
README_FILE = "README.md"
_UNSAFE = re.compile(r"[^\w.-]+", re.UNICODE)


def file_name(doc: FullDocument) -> str:
    slug = _UNSAFE.sub("-", doc.external_id.replace(":", "-")).strip("-")[:80] or str(doc.id)
    return f"{doc.source}/{slug}.md"


def render(doc: FullDocument) -> str:
    lines = [f"# {doc.title}", "", f"- source: {doc.source}", f"- url: {doc.url}"]
    if doc.author:
        lines.append(f"- author: {doc.author}")
    if doc.created_at:
        lines.append(f"- created: {doc.created_at.isoformat()}")
    return "\n".join(lines + ["", doc.text, ""])


class WorkspaceExport:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._lock = Lock()
        self._signature: tuple | None = None
        self._files: dict[str, int] = {}  # relative path -> document id

    def sync(self, session: Session) -> Path:
        signature = corpus_signature(session)
        with self._lock:
            if signature == self._signature and self.root.exists():
                return self.root
            docs = load_documents(session)
            if self.root.exists():
                shutil.rmtree(self.root)
            self.root.mkdir(parents=True)
            files: dict[str, int] = {}
            for doc in docs:
                name = file_name(doc)
                if name in files:  # extremely unlikely slug collision
                    name = name[:-3] + f"-{doc.id}.md"
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(render(doc).encode("utf-8"))
                files[name] = doc.id
            (self.root / README_FILE).write_bytes(
                b"# Project workspace export\n\nOne file per item: github/ (issues, pull requests, files), "
                 b"notion/ (pages), discord/ (threads and channel logs), decision/ (confirmed decisions).\n"
                 )
            (self.root / INDEX_FILE).write_bytes(json.dumps(files, ensure_ascii=False, indent=1).encode("utf-8"))
            self._files, self._signature = files, signature
            return self.root

    @property
    def files(self) -> dict[str, int]:
        """Relative file path -> document id, as of the last sync."""
        return dict(self._files)

    def path_of(self, document_id: int) -> str | None:
        return next((p for p, i in self._files.items() if i == document_id), None)

    def document_id(self, cited_path: str) -> int | None:
        """Map a path the model cited (possibly './github/pr-5.md' or an absolute path) to a document id."""
        cleaned = cited_path.strip().strip("`'\"").replace("\\", "/")
        root = self.root.as_posix().rstrip("/") + "/"
        if cleaned.lower().startswith(root.lower()):
            cleaned = cleaned[len(root):]
        cleaned = cleaned.removeprefix("./")
        if cleaned in self._files:
            return self._files[cleaned]
        matches = [p for p in self._files if p.endswith("/" + cleaned) or cleaned.endswith("/" + p)]
        return self._files[matches[0]] if len(matches) == 1 else None
