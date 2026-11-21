import json

import pytest

from app.config import Settings
from app.llm.base import LLMError, LLMProvider
from app.llm.claude_cli import ClaudeCLIProvider
from app.llm.factory import get_provider
from app.llm.fake import FakeProvider
from app.llm.json_utils import extract_json_object

# ---------- factory ----------

@pytest.mark.parametrize("name, cls", [("claude_cli", ClaudeCLIProvider), ("fake", FakeProvider)])
def test_factory_builds_provider(name, cls):
    provider = get_provider(Settings(_env_file=None), name)
    assert isinstance(provider, cls)
    assert isinstance(provider, LLMProvider)


def test_factory_defaults_to_claude_cli_and_rejects_others():
    assert isinstance(get_provider(Settings(_env_file=None)), ClaudeCLIProvider)
    for name in ("anthropic_api", "ollama", "auto", "nope"):
        with pytest.raises(ValueError):
            get_provider(Settings(_env_file=None), name)


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
    prompt_file = args[args.index("--system-prompt-file") + 1]
    assert open(prompt_file, encoding="utf-8").read() == "SYS"
    assert all(a.isascii() for a in args[1:])  # nothing non-ASCII goes through the (Windows .cmd) command line
    assert args[args.index("--model") + 1] == "claude-sonnet-5-5"
    assert "--output-format" in args and "json" in args


def test_cli_chinese_prompt_and_schema_stay_off_the_command_line():
    provider = ClaudeCLIProvider()
    args = provider.build_args("你是專案助理", json_schema={"type": "object", "description": "回答"})
    assert all(a.isascii() for a in args[1:])
    assert open(args[args.index("--system-prompt-file") + 1], encoding="utf-8").read() == "你是專案助理"
    assert json.loads(args[args.index("--json-schema") + 1])["description"] == "回答"


def test_cli_prefers_structured_output():
    data = {**CLI_OK, "result": "some prose", "structured_output": {"sections": [], "note": "結構化"}}
    result = ClaudeCLIProvider().parse_output(json.dumps(data).encode(), b"", 0, 1)
    assert json.loads(result.text) == {"sections": [], "note": "結構化"}


def test_cli_workspace_enables_only_read_only_tools(tmp_path):
    args = ClaudeCLIProvider().build_args("SYS", workspace=tmp_path)
    assert args[args.index("--tools") + 1] == "Read,Grep,Glob"
    assert args[args.index("--allowedTools") + 1] == "Read,Grep,Glob"
    assert args[args.index("--permission-mode") + 1] == "dontAsk"


async def test_cli_generate_runs_inside_workspace(monkeypatch, tmp_path):
    provider = ClaudeCLIProvider()
    seen = {}

    async def fake_run(args, stdin_text, cwd=None):
        seen["cwd"] = cwd
        return json.dumps(CLI_OK).encode(), b"", 0

    monkeypatch.setattr(provider, "_run", fake_run)
    await provider.generate("SYS", "Q", workspace=tmp_path)
    assert seen["cwd"] == tmp_path


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

    async def fake_run(args, stdin_text, cwd=None):
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
