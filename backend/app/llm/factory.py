"""Build the configured `LLMProvider` from settings."""

from ..config import Settings
from .base import LLMProvider

PLANNED_PROVIDERS = {"openai_api", "ollama", "codex_cli"}  # milestone M5


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
    if name == "anthropic_api":
        from .anthropic_api import AnthropicAPIProvider

        return AnthropicAPIProvider(
            settings.llm_model, effort=settings.llm_effort, timeout_s=settings.llm_timeout_s
        )
    if name == "fake":
        from .fake import FakeProvider

        return FakeProvider()
    if name in PLANNED_PROVIDERS:
        raise NotImplementedError(f"LLM provider {name!r} is planned for milestone M5 and not implemented yet.")
    raise ValueError(f"Unknown LLM_PROVIDER {name!r}. Use one of: claude_cli, anthropic_api, fake.")
