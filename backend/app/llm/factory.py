"""Build the configured `LLMProvider` from settings.

The provider and model are chosen on the /connect/llm page (saved as LLM_PROVIDER / LLM_MODEL in `.env`).
`fake` exists only for tests and offline development.
"""

from pathlib import Path

from ..config import Settings
from .base import LLMError, LLMProvider, LLMResult

PROVIDERS = ("claude_cli", "anthropic_api", "openai_api", "ollama", "fake")


def get_provider(settings: Settings, name: str | None = None, model: str | None = None) -> LLMProvider:
    name = (name or settings.llm_provider).strip().lower()
    model = settings.llm_model if model is None else model
    if name == "claude_cli":
        from .claude_cli import ClaudeCLIProvider

        return ClaudeCLIProvider(
            model,
            executable=settings.claude_cli_path,
            timeout_s=settings.llm_timeout_s,
            max_concurrency=settings.llm_max_concurrency,
            strip_api_key=settings.claude_cli_strip_api_key,
        )
    if name == "anthropic_api":
        from .anthropic_api import AnthropicAPIProvider

        return AnthropicAPIProvider(settings.anthropic_api_key, model, timeout_s=settings.llm_timeout_s)
    if name == "openai_api":
        from .openai_api import OpenAIAPIProvider

        return OpenAIAPIProvider(settings.openai_api_key, model, base_url=settings.openai_base_url,
                                 timeout_s=settings.llm_timeout_s)
    if name == "ollama":
        from .ollama import OllamaProvider

        return OllamaProvider(model, base_url=settings.ollama_base_url, num_ctx=settings.ollama_num_ctx,
                              timeout_s=settings.llm_timeout_s)
    if name == "fake":
        from .fake import FakeProvider

        return FakeProvider()
    raise ValueError(f"Unknown LLM_PROVIDER {name!r}. Use one of: {', '.join(PROVIDERS)}.")


class UnavailableProvider:
    """Stands in when LLM_PROVIDER is invalid, so asking fails with a message instead of a server error."""

    supports_workspace = False

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self.reason = reason

    async def generate(
        self, system: str, user: str, *, max_tokens: int = 4000, workspace: Path | None = None,
        json_schema: dict | None = None,
    ) -> LLMResult:
        raise LLMError(self.reason, retryable=False)
