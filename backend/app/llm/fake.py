"""Deterministic provider for tests and offline development (no model is called)."""

from collections.abc import Callable

from .base import LLMResult


class FakeProvider:
    name = "fake"

    def __init__(self, responder: Callable[[str, str], str] | None = None) -> None:
        self._responder = responder or (lambda system, user: f"[fake answer] {user[:200]}")
        self.calls: list[tuple[str, str]] = []

    async def generate(self, system: str, user: str, *, max_tokens: int = 4000) -> LLMResult:
        self.calls.append((system, user))
        return LLMResult(text=self._responder(system, user), provider=self.name, model="fake", latency_ms=0)
