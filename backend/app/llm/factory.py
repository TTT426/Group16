"""Build the configured `LLMProvider` from settings.

The project uses one LLM: the logged-in Claude Code CLI (Claude Pro/Max subscription).
`fake` exists only for tests and offline development.
"""

from ..config import Settings
from .base import LLMProvider

PROVIDERS = ("claude_cli", "fake")


def get_provider(settings: Settings, name: str | None = None) -> LLMProvider:
    name = (name or settings.llm_provider).strip().lower()
    if name == "claude_cli":
        from .claude_cli import ClaudeCLIProvider

        return ClaudeCLIProvider(
            settings.llm_model,
            executable=settings.claude_cli_path,
            timeout_s=settings.llm_timeout_s,
            max_concurrency=settings.llm_max_concurrency,
            strip_api_key=settings.claude_cli_strip_api_key,
        )
    if name == "fake":
        from .fake import FakeProvider

        return FakeProvider()
    raise ValueError(f"Unknown LLM_PROVIDER {name!r}. Use one of: {', '.join(PROVIDERS)}.")
