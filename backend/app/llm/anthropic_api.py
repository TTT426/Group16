"""Anthropic API provider (pay-as-you-go, needs ANTHROPIC_API_KEY or an `ant auth login` profile)."""

import time

import anthropic

from .base import LLMError, LLMResult

DEFAULT_MODEL = "claude-opus-5-5"

# Models that accept the server-side refusal fallback parameter.
_FALLBACK_MODELS = {
    "claude-fable-5-2",
    "claude-fable-5-1",
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-sonnet-5-5",
}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicAPIProvider:
    name = "anthropic_api"

    def __init__(
        self,
        model: str = "",
        *,
        effort: str = "medium",
        timeout_s: float = 180.0,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.model = model or DEFAULT_MODEL
        self.effort = effort
        self._client = client or anthropic.AsyncAnthropic(timeout=timeout_s)

    async def generate(self, system: str, user: str, *, max_tokens: int = 4000) -> LLMResult:
        params: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if self.effort:
            params["output_config"] = {"effort": self.effort}

        start = time.perf_counter()
        try:
            if self.model in _FALLBACK_MODELS:
                # On a safety decline, the API re-runs the request on a fallback model in the same call.
                response = await self._client.beta.messages.create(
                    **params, betas=[_FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = await self._client.messages.create(**params)
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.stop_reason == "refusal":
            raise LLMError("The model declined to answer this request.")

        text = "".join(block.text for block in response.content if block.type == "text")
        if not text.strip():
            raise LLMError(f"Empty response (stop_reason={response.stop_reason}).")

        return LLMResult(
            text=text,
            provider=self.name,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
        )
