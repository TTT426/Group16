"""API and local providers (Anthropic, OpenAI-compatible, Ollama) with mocked HTTP / SDK."""

import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.llm import anthropic_api, ollama, openai_api
from app.llm.base import LLMError
from app.qa.prompts import ANSWER_SCHEMA

# ---------------------------------------------------------------- Anthropic API


class FakeAnthropic:
    """Stands in for AsyncAnthropic: records the request, returns `response` or raises `error`."""

    def __init__(self, response=None, error=None):
        self.response, self.error, self.params, self.closed = response, error, None, False
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    async def _create(self, **params):
        self.params = params
        if self.error:
            raise self.error
        return self.response

    async def close(self):
        self.closed = True


def message(text='{"ok": true}', stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason, model="claude-opus-5-5", usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def use_client(monkeypatch, fake):
    monkeypatch.setattr(anthropic_api, "_client", lambda key, timeout: fake)


async def test_anthropic_structured_output_and_fallbacks(monkeypatch):
    fake = FakeAnthropic(message())
    use_client(monkeypatch, fake)
    result = await anthropic_api.AnthropicAPIProvider("sk-ant-x").generate("sys", "hi", json_schema=ANSWER_SCHEMA)
    assert result.text == '{"ok": true}' and result.model == "claude-opus-5-5" and result.input_tokens == 10
    p = fake.params
    assert p["model"] == "claude-opus-5-5" and p["system"] == "sys" and p["max_tokens"] >= 16000
    assert p["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert p["fallbacks"] == "default" and p["betas"] == [anthropic_api.FALLBACK_BETA]
    assert fake.closed


async def test_anthropic_no_fallbacks_for_other_models(monkeypatch):
    fake = FakeAnthropic(message())
    use_client(monkeypatch, fake)
    await anthropic_api.AnthropicAPIProvider("sk-ant-x", "claude-haiku-5-5").generate("sys", "hi")
    assert "fallbacks" not in fake.params and "output_config" not in fake.params


@pytest.mark.parametrize("stop_reason, msg", [("refusal", anthropic_api.MSG_REFUSED),
                                              ("max_tokens", anthropic_api.MSG_TRUNCATED)])
async def test_anthropic_stop_reasons(monkeypatch, stop_reason, msg):
    use_client(monkeypatch, FakeAnthropic(message(stop_reason=stop_reason)))
    with pytest.raises(LLMError, match=msg):
        await anthropic_api.AnthropicAPIProvider("sk-ant-x").generate("sys", "hi")


async def test_anthropic_errors_are_friendly(monkeypatch):
    response = httpx.Response(401, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    error = anthropic.AuthenticationError("bad key", response=response, body=None)
    use_client(monkeypatch, FakeAnthropic(error=error))
    with pytest.raises(LLMError, match=anthropic_api.MSG_BAD_KEY):
        await anthropic_api.AnthropicAPIProvider("sk-ant-x").generate("sys", "hi")
    monkeypatch.undo()  # the real client builder refuses an empty key before any request
    with pytest.raises(LLMError, match=anthropic_api.MSG_NO_KEY):
        await anthropic_api.AnthropicAPIProvider("").generate("sys", "hi")


# ---------------------------------------------------------------- OpenAI-compatible


def openai_transport(seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.headers.get("authorization") != "Bearer sk-x":
            return httpx.Response(401, json={"error": {"message": "bad"}})
        return httpx.Response(200, json={"model": "gpt-x-2026", "choices": [{"message": {"content": "{}"}}],
                                         "usage": {"prompt_tokens": 7, "completion_tokens": 2}})
    return httpx.MockTransport(handler)


async def test_openai_chat_completion_with_strict_schema():
    seen: list[httpx.Request] = []
    provider = openai_api.OpenAIAPIProvider("sk-x", "gpt-x", transport=openai_transport(seen))
    result = await provider.generate("sys", "hi", json_schema=ANSWER_SCHEMA)
    assert (result.text, result.model, result.input_tokens, result.output_tokens) == ("{}", "gpt-x-2026", 7, 2)
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == "https://api.openai.com/v1/chat/completions"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["response_format"]["json_schema"]["strict"] is True


async def test_openai_errors():
    with pytest.raises(LLMError, match=openai_api.MSG_BAD_KEY):
        await openai_api.OpenAIAPIProvider("wrong", "gpt-x", transport=openai_transport([])).generate("s", "u")
    with pytest.raises(LLMError, match=openai_api.MSG_NO_KEY):
        await openai_api.OpenAIAPIProvider("", "gpt-x").generate("s", "u")


def test_openai_model_list_keeps_chat_models_on_openai_only():
    models = {"data": [{"id": i} for i in ("gpt-5", "text-embedding-3-small", "gpt-4o-audio-preview", "o3", "x")]}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=models)))
    assert [m["id"] for m in openai_api.list_models("sk-x", client=client)] == ["gpt-5", "o3"]
    # a compatible server: everything it lists, and no key needed
    assert len(openai_api.list_models("", "http://localhost:1234/v1", client=client)) == 5


# ---------------------------------------------------------------- Ollama


async def test_ollama_chat_passes_schema_and_context_window():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"model": "qwen3:8b", "message": {"content": "{}"},
                                         "prompt_eval_count": 50, "eval_count": 4})
    provider = ollama.OllamaProvider("qwen3:8b", num_ctx=8192, transport=httpx.MockTransport(handler))
    result = await provider.generate("sys", "hi", json_schema=ANSWER_SCHEMA)
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == "http://localhost:11434/api/chat"
    assert body["format"] == ANSWER_SCHEMA and body["options"] == {"num_ctx": 8192} and body["stream"] is False
    assert (result.text, result.input_tokens, result.output_tokens) == ("{}", 50, 4)


async def test_ollama_missing_model_and_server():
    missing = httpx.MockTransport(lambda r: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(LLMError, match="ollama pull nope"):
        await ollama.OllamaProvider("nope", transport=missing).generate("s", "u")

    def down(request):
        raise httpx.ConnectError("refused")
    with pytest.raises(LLMError, match="連不上 Ollama"):
        await ollama.OllamaProvider("qwen3:8b", transport=httpx.MockTransport(down)).generate("s", "u")


def test_ollama_model_list():
    tags = {"models": [{"name": "qwen3:8b", "details": {"parameter_size": "8.2B", "quantization_level": "Q4_K_M"}}]}
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=tags)))
    assert ollama.list_models(client=client) == [{"id": "qwen3:8b", "label": "qwen3:8b（8.2B Q4_K_M）"}]
