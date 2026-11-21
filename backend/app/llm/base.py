"""Provider-neutral LLM interface.

Every part of the app talks to models through `LLMProvider`, so the backing
model (Claude subscription via CLI, Anthropic API, local model, ...) can be
switched with the `LLM_PROVIDER` setting without touching callers.
"""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class LLMResult(BaseModel):
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int


class LLMError(RuntimeError):
    """Raised when a provider fails to produce a usable answer."""


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    async def generate(self, system: str, user: str, *, max_tokens: int = 4000) -> LLMResult:
        """Return the model's text reply to a single-turn prompt."""
        ...
