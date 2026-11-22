"""Deterministic provider for tests and offline development (no model is called)."""

from collections.abc import Callable
from pathlib import Path

from .base import LLMResult


class FakeProvider:
    name = "fake"
    supports_workspace = True

    def __init__(self, responder: Callable[[str, str], str] | None = None) -> None:
        self._responder = responder or (lambda system, user: f"[fake answer] {user[:200]}")
        self.calls: list[tuple[str, str]] = []
        self.workspaces: list[Path | None] = []
        self.schemas: list[dict | None] = []

    async def generate(
        self, system: str, user: str, *, max_tokens: int = 4000, workspace: Path | None = None,
        json_schema: dict | None = None,
    ) -> LLMResult:
        self.calls.append((system, user))
        self.workspaces.append(workspace)
        self.schemas.append(json_schema)
        return LLMResult(text=self._responder(system, user), provider=self.name, model="fake", latency_ms=0)
