"""Anthropic API provider: Claude models billed per token with an API key from console.anthropic.com.

Uses the official `anthropic` SDK. Replies are constrained with structured outputs
(`output_config.format`) when a JSON schema is given. Models that support it get server-side
refusal fallbacks (`fallbacks: "default"`), so a safety decline is retried on another model
inside the same call instead of failing the question.
"""

import time
from pathlib import Path

import anthropic

from .base import LLMError, LLMResult
from .json_utils import strict_schema

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000  # room for adaptive thinking plus the answer; non-streaming stays under SDK timeouts
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}

MSG_NO_KEY = "還沒有設定 Anthropic API key。"
MSG_BAD_KEY = "Anthropic API key 無效，請到 console.anthropic.com 重新建立一把。"
MSG_NO_PERMISSION = "這把 Anthropic API key 沒有使用權限（帳號可能還沒有儲值或被停用）。"
MSG_RATE_LIMIT = "Anthropic API 使用量已達上限，請稍後再試。"
MSG_UNREACHABLE = "連不上 Anthropic API，請檢查網路。"
MSG_TIMEOUT = "Anthropic API 太久沒有回應，請稍後再試。"
MSG_REFUSED = "模型拒絕回答這個問題。"
MSG_TRUNCATED = "回答太長被截斷了，請把問題問得更具體一點。"


def _error(exc: anthropic.AnthropicError) -> LLMError:
    """A user-facing error for an SDK exception (most specific first)."""
    if isinstance(exc, anthropic.AuthenticationError):
        return LLMError(MSG_BAD_KEY, retryable=False)
    if isinstance(exc, anthropic.PermissionDeniedError):
        return LLMError(MSG_NO_PERMISSION, retryable=False)
    if isinstance(exc, anthropic.NotFoundError):
        return LLMError(f"Anthropic API 找不到這個模型：{exc.message}", retryable=False)
    if isinstance(exc, anthropic.RateLimitError):
        return LLMError(MSG_RATE_LIMIT, retryable=False)
    if isinstance(exc, anthropic.APIStatusError):
        return LLMError(f"Anthropic API 錯誤（{exc.status_code}）：{exc.message}", retryable=exc.status_code >= 500)
    if isinstance(exc, anthropic.APITimeoutError):
        return LLMError(MSG_TIMEOUT, retryable=False)
    if isinstance(exc, anthropic.APIConnectionError):
        return LLMError(MSG_UNREACHABLE, retryable=False)
    return LLMError(f"Anthropic API 錯誤：{exc}")


def _client(api_key: str, timeout_s: float) -> anthropic.AsyncAnthropic:
    if not api_key:
        raise LLMError(MSG_NO_KEY, retryable=False)
    return anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_s)


async def list_models(api_key: str, timeout_s: float = 10.0) -> list[dict]:
    """The models this key can use, newest first: [{'id', 'label'}]. Also how a key is checked."""
    client = _client(api_key, timeout_s)
    try:
        return [{"id": m.id, "label": m.display_name or m.id} async for m in client.models.list()]
    except anthropic.AnthropicError as exc:
        raise _error(exc) from exc
    finally:
        await client.close()


class AnthropicAPIProvider:
    name = "anthropic_api"
    supports_workspace = False

    def __init__(self, api_key: str, model: str = "", *, timeout_s: float = 180.0) -> None:
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.timeout_s = timeout_s

    async def generate(
        self, system: str, user: str, *, max_tokens: int = 4000, workspace: Path | None = None,
        json_schema: dict | None = None,
    ) -> LLMResult:
        params: dict = {"model": self.model, "max_tokens": max(max_tokens, MAX_TOKENS), "system": system,
                        "messages": [{"role": "user", "content": user}]}
        if json_schema is not None:
            params["output_config"] = {"format": {"type": "json_schema", "schema": strict_schema(json_schema)}}
        if self.model in FALLBACK_MODELS:
            params.update(betas=[FALLBACK_BETA], fallbacks="default")

        client = _client(self.api_key, self.timeout_s)
        start = time.perf_counter()
        try:
            response = await client.beta.messages.create(**params)
        except anthropic.AnthropicError as exc:
            raise _error(exc) from exc
        finally:
            await client.close()
        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.stop_reason == "refusal":
            raise LLMError(MSG_REFUSED, retryable=False)
        if response.stop_reason == "max_tokens":
            raise LLMError(MSG_TRUNCATED, retryable=False)
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            raise LLMError("Anthropic API 回傳了空白的回答。")
        return LLMResult(text=text, provider=self.name, model=response.model,
                         input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
                         latency_ms=latency_ms)
