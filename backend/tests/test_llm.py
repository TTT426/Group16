import json
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.llm.anthropic_api import AnthropicAPIProvider
from app.llm.base import LLMError, LLMProvider
from app.llm.claude_cli import ClaudeCLIProvider
from app.llm.factory import get_provider
from app.llm.fake import FakeProvider
from app.llm.json_utils import extract_json_object

# ---------- factory ----------

@pytest.mark.parametrize("name, cls", [
    ("claude_cli", ClaudeCLIProvider),
    ("anthropic_api", AnthropicAPIProvider),
    ("fake", FakeProvider),
])
def test_factory_builds_provider(name, cls, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")  # AsyncAnthropic needs some credential to construct
    provider = get_provider(Settings(_env_file=None), name)
    assert isinstance(provider, cls)
    assert isinstance(provider, LLMProvider)


def test_factory_planned_and_unknown():
    settings = Settings(_env_file=None)
    with pytest.raises(NotImplementedError):
        get_provider(settings, "ollama")
    with pytest.raises(ValueError):
        get_provider(settings, "nope")


# ---------- claude_cli ----------

CLI_OK = {
    "type": "result", "is_error": False, "result": "OK",
    "usage": {"input_tokens": 12, "output_tokens": 3},
    "modelUsage": {"claude-opus-5-5[1m]": {"inputTokens": 12}},
}


def test_cli_reports_main_model_not_background_model():
    data = {**CLI_OK, "modelUsage": {
        "claude-haiku-5-5": {"outputTokens": 18, "canonicalModel": "claude-haiku-5-5"},
        "claude-opus-5-5[1m]": {"outputTokens": 70},
    }}
    result = ClaudeCLIProvider().parse_output(json.dumps(data).encode(), b"", 0, 1)
    assert result.model == "claude-opus-5-5"


def test_cli_args_disable_tools_and_pass_system():
    provider = ClaudeCLIProvider("claude-sonnet-5-5")
    args = provider.build_args("SYS")
    assert args[1] == "-p"
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--system-prompt") + 1] == "SYS"
    assert args[args.index("--model") + 1] == "claude-sonnet-5-5"
    assert "--output-format" in args and "json" in args


def test_cli_strips_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    assert "ANTHROPIC_API_KEY" not in ClaudeCLIProvider().build_env()
    assert ClaudeCLIProvider(strip_api_key=False).build_env()["ANTHROPIC_API_KEY"] == "secret"


def test_cli_parse_ok():
    result = ClaudeCLIProvider().parse_output(json.dumps(CLI_OK).encode(), b"", 0, 42)
    assert result.text == "OK"
    assert result.model == "claude-opus-5-5"
    assert (result.input_tokens, result.output_tokens, result.latency_ms) == (12, 3, 42)


@pytest.mark.parametrize("stdout, code", [
    (b"not json", 1),
    (json.dumps({**CLI_OK, "is_error": True, "result": "rate limited"}).encode(), 1),
    (json.dumps({**CLI_OK, "result": ""}).encode(), 0),
])
def test_cli_parse_errors(stdout, code):
    with pytest.raises(LLMError):
        ClaudeCLIProvider().parse_output(stdout, b"boom", code, 1)


async def test_cli_generate_uses_stdin(monkeypatch):
    provider = ClaudeCLIProvider()
    seen = {}

    async def fake_run(args, stdin_text):
        seen["args"], seen["stdin"] = args, stdin_text
        return json.dumps(CLI_OK).encode(), b"", 0

    monkeypatch.setattr(provider, "_run", fake_run)
    result = await provider.generate("SYS", "使用者問題")
    assert seen["stdin"] == "使用者問題"
    assert result.text == "OK"


async def test_cli_missing_executable():
    provider = ClaudeCLIProvider(executable="definitely-not-a-real-binary-xyz")
    with pytest.raises(LLMError, match="not found"):
        await provider.generate("SYS", "hi")


# ---------- anthropic_api ----------

class _FakeMessages:
    def __init__(self, response):
        self.response, self.kwargs = response, None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def _fake_client(response):
    messages = _FakeMessages(response)
    client = SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages))
    return client, messages


def _response(stop_reason="end_turn", blocks=None):
    blocks = blocks if blocks is not None else [
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text="答案"),
    ]
    return SimpleNamespace(
        content=blocks, stop_reason=stop_reason, model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


async def test_anthropic_generate_with_fallback_and_effort():
    client, messages = _fake_client(_response())
    provider = AnthropicAPIProvider(client=client)
    result = await provider.generate("SYS", "Q", max_tokens=123)
    assert result.text == "答案"
    assert result.model == "claude-opus-5-5"
    kw = messages.kwargs
    assert kw["model"] == "claude-opus-5-5"
    assert kw["system"] == "SYS" and kw["max_tokens"] == 123
    assert kw["output_config"] == {"effort": "medium"}
    assert kw["fallbacks"] == "default"


async def test_anthropic_no_fallback_for_other_models():
    client, messages = _fake_client(_response())
    await AnthropicAPIProvider("claude-haiku-4-5", effort="", client=client).generate("S", "Q")
    assert "fallbacks" not in messages.kwargs
    assert "output_config" not in messages.kwargs


async def test_anthropic_refusal_raises():
    client, _ = _fake_client(_response(stop_reason="refusal", blocks=[]))
    with pytest.raises(LLMError, match="declined"):
        await AnthropicAPIProvider(client=client).generate("S", "Q")


# ---------- fake + json utils ----------

async def test_fake_provider_records_calls():
    provider = FakeProvider(lambda s, u: u.upper())
    result = await provider.generate("S", "abc")
    assert result.text == "ABC" and provider.calls == [("S", "abc")]


@pytest.mark.parametrize("text", [
    '{"a": 1}',
    'Here you go:\n```json\n{"a": 1}\n```',
    '說明文字 {"a": 1} 結尾',
    '{bad} then {"a": 1}',
])
def test_extract_json_object(text):
    assert extract_json_object(text) == {"a": 1}


def test_extract_json_object_fails():
    with pytest.raises(ValueError):
        extract_json_object("no json here [1, 2]")


# ---------- auto selection ----------

def test_auto_prefers_claude_cli_then_api_then_fake(monkeypatch):
    import app.llm.factory as factory

    settings = Settings(_env_file=None, llm_provider="auto")
    monkeypatch.setattr(factory.shutil, "which", lambda exe: "/usr/bin/claude")
    assert factory.resolve_provider_name(settings) == "claude_cli"

    monkeypatch.setattr(factory.shutil, "which", lambda exe: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert factory.resolve_provider_name(settings) == "anthropic_api"

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert factory.resolve_provider_name(settings) == "fake"
    assert isinstance(get_provider(settings), FakeProvider)
    assert factory.resolve_provider_name(Settings(_env_file=None, llm_provider="claude_cli")) == "claude_cli"
