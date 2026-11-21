"""Common types for source connectors."""

from collections.abc import Iterator
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

Source = Literal["github", "notion", "discord", "decision"]


class NormalizedDocument(BaseModel):
    """One item from a source tool, in the shape the ingest pipeline expects."""

    source: Source
    external_id: str  # stable id inside the source, e.g. "pr:12", "thread:1234"
    url: str  # link a user can open to verify the answer
    title: str = ""
    author: str | None = None
    created_at: datetime | None = None
    text: str
    raw: dict | None = None


class ConnectorError(RuntimeError):
    """Raised when a source cannot be read (bad token, missing permission, ...)."""


class Connector(Protocol):
    source: Source

    def fetch(self) -> Iterator[NormalizedDocument]: ...


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
