"""Build the configured `LLMProvider` from settings."""

import importlib.util
import logging
import os
import shutil

from ..config import Settings
from .base import LLMProvider

log = logging.getLogger(__name__)

PLANNED_PROVIDERS = {"openai_api", "ollama", "codex_cli"}  # milestone M5


def resolve_provider_name(settings: Settings) -> str:
    """`auto`: Claude CLI if installed (subscription), else the API if a key is set, else the offline fake."""
    name = settings.llm_provider.strip().lower()
    if name != "auto":
        return name
    if shutil.which(settings.claude_cli_path):
        return "claude_cli"
    if os.environ.get("ANTHROPIC_API_KEY") and importlib.util.find_spec("anthropic"):
        return "anthropic_api"
    log.warning("No LLM available (no Claude CLI, no ANTHROPIC_API_KEY); using the offline fake provider.")
    return "fake"


def get_provider(settings: Settings, name: str | None = None) -> LLMProvider:
    name = (name or resolve_provider_name(settings)).strip().lower()

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
        try:
            from .anthropic_api import AnthropicAPIProvider
        except ImportError as exc:
            raise RuntimeError('anthropic_api needs the anthropic package: pip install -e ".[anthropic]"') from exc

        return AnthropicAPIProvider(
            settings.llm_model, effort=settings.llm_effort, timeout_s=settings.llm_timeout_s
        )
    if name == "fake":
        from .fake import FakeProvider

        return FakeProvider()
    if name in PLANNED_PROVIDERS:
        raise NotImplementedError(f"LLM provider {name!r} is planned for milestone M5 and not implemented yet.")
    raise ValueError(f"Unknown LLM_PROVIDER {name!r}. Use one of: auto, claude_cli, anthropic_api, fake.")
