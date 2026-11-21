"""Provider-neutral LLM interface.

Every part of the app talks to the model through `LLMProvider`. The project uses the
Claude Code CLI (`claude_cli`); `fake` replaces it in tests and offline development.
"""

from pathlib import Path
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

    async def generate(
        self, system: str, user: str, *, max_tokens: int = 4000, workspace: Path | None = None,
        json_schema: dict | None = None,
    ) -> LLMResult:
        """Return the model's text reply to a single-turn prompt.

        With `workspace`, the model may search and read the files in that folder (read-only) before answering.
        With `json_schema`, the reply text is a JSON object that matches the schema.
        """
        ...
