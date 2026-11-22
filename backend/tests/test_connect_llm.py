"""/connect/llm: choose the provider and model, save API keys, test the model (no real model is called)."""

import pytest
from fastapi.testclient import TestClient

from app.api import connect_llm, deps
from app.config import Settings
from app.llm import anthropic_api, ollama, openai_api
from app.llm.base import LLMError
from app.llm.factory import UnavailableProvider
from app.llm.fake import FakeProvider
from app.main import app

client = TestClient(app)


@pytest.fixture
def env(monkeypatch):
    """A fake `.env`: update_env writes into `values`, get_settings reads from it."""
    values: dict[str, str] = {}
    writes: list[dict] = []

    def update_env(updates):
        writes.append(updates)
        values.update(updates)

    monkeypatch.setattr(connect_llm, "update_env", update_env)
    monkeypatch.setattr(connect_llm, "get_settings",
                        lambda: Settings(_env_file=None, **{k.lower(): v for k, v in values.items()}))
    return writes


@pytest.fixture
def anthropic_models(monkeypatch):
    async def list_models(key):
        if key != "sk-ant-good":
            raise LLMError(anthropic_api.MSG_BAD_KEY)
        return [{"id": "claude-opus-5-5", "label": "Claude Opus 5.5"}]
    monkeypatch.setattr(anthropic_api, "list_models", list_models)


def test_page_and_local_only_guard():
    assert 'id="providers"' in client.get("/connect/llm").text
    assert client.get("/api/llm/status", headers={"host": "evil.example"}).status_code == 403
    response = client.post("/api/llm/select", json={"provider": "claude_cli"}, headers={"origin": "https://evil.example"})
    assert response.status_code == 403


def test_save_key_keeps_only_valid_keys_and_never_echoes_them(env, anthropic_models):
    assert client.post("/api/llm/key", json={"provider": "anthropic_api", "api_key": "bad"}).status_code == 400
    assert env == []
    response = client.post("/api/llm/key", json={"provider": "anthropic_api", "api_key": " sk-ant-good "})
    assert response.status_code == 200 and "sk-ant-good" not in response.text
    assert response.json()["models"][0]["id"] == "claude-opus-5-5"
    assert env == [{"ANTHROPIC_API_KEY": "sk-ant-good"}]


def test_openai_compatible_server_without_key(env, monkeypatch):
    monkeypatch.setattr(openai_api, "list_models", lambda key, base_url: [{"id": "local-model", "label": "local"}])
    assert client.post("/api/llm/key", json={"provider": "openai_api"}).status_code == 400  # no key, no server
    assert client.post("/api/llm/key", json={"provider": "openai_api", "base_url": "ftp://x"}).status_code == 400
    response = client.post("/api/llm/key", json={"provider": "openai_api", "base_url": "http://localhost:1234/v1/"})
    assert response.status_code == 200
    assert env == [{"OPENAI_API_KEY": "", "OPENAI_BASE_URL": "http://localhost:1234/v1"}]


def test_select_checks_the_model_is_offered(env, anthropic_models):
    client.post("/api/llm/key", json={"provider": "anthropic_api", "api_key": "sk-ant-good"})
    assert client.post("/api/llm/select", json={"provider": "anthropic_api", "model": "gpt-5"}).status_code == 400
    response = client.post("/api/llm/select", json={"provider": "anthropic_api", "model": "claude-opus-5-5"})
    assert response.status_code == 200
    assert response.json() == {"provider": "anthropic_api", "model": "claude-opus-5-5",
                               "label": "Anthropic API · claude-opus-5-5", "agent_mode": False, "problem": None}
    assert env[-1] == {"LLM_PROVIDER": "anthropic_api", "LLM_MODEL": "claude-opus-5-5"}


def test_select_claude_cli_alias_and_rejects_odd_names(env):
    assert client.post("/api/llm/select", json={"provider": "claude_cli", "model": "sonnet"}).status_code == 200
    assert client.post("/api/llm/select", json={"provider": "claude_cli", "model": "a b; rm"}).status_code == 400
    assert client.post("/api/llm/select", json={"provider": "fake"}).status_code == 422  # not offered on the page


def test_select_unreachable_ollama(env, monkeypatch):
    def down(base_url):
        raise LLMError(ollama.MSG_NOT_RUNNING)
    monkeypatch.setattr(ollama, "list_models", down)
    response = client.post("/api/llm/select", json={"provider": "ollama", "model": "qwen3:8b"})
    assert response.status_code == 400 and response.json()["detail"] == ollama.MSG_NOT_RUNNING


def test_select_takes_effect_for_the_next_question(env, monkeypatch):
    monkeypatch.setattr(ollama, "list_models", lambda base_url: [{"id": "qwen3:8b", "label": "qwen3:8b"}])
    cleared = []
    monkeypatch.setattr(connect_llm.llm_dep, "cache_clear", lambda: cleared.append(True))
    client.post("/api/llm/select", json={"provider": "ollama", "model": "qwen3:8b"})
    assert cleared


def test_forget_key_of_the_provider_in_use_goes_back_to_claude_code(env, anthropic_models):
    client.post("/api/llm/key", json={"provider": "anthropic_api", "api_key": "sk-ant-good"})
    client.post("/api/llm/select", json={"provider": "anthropic_api", "model": "claude-opus-5-5"})
    response = client.post("/api/llm/forget", json={"provider": "anthropic_api"})
    assert response.json()["provider"] == "claude_cli"
    assert env[-2:] == [{"ANTHROPIC_API_KEY": ""}, {"LLM_PROVIDER": "claude_cli", "LLM_MODEL": ""}]


def test_test_call_reports_reply_or_error(env, monkeypatch):
    seen = []

    def provider(settings, name, model):
        seen.append((name, model))
        return FakeProvider(lambda system, user: "我是測試模型。")
    monkeypatch.setattr(connect_llm, "get_provider", provider)
    response = client.post("/api/llm/test", json={"provider": "ollama", "model": "qwen3:8b"})
    assert response.json()["text"] == "我是測試模型。" and seen == [("ollama", "qwen3:8b")]

    class Broken(FakeProvider):
        async def generate(self, *args, **kwargs):
            raise LLMError("連不上")
    monkeypatch.setattr(connect_llm, "get_provider", lambda settings, name, model: Broken())
    response = client.post("/api/llm/test", json={})
    assert response.status_code == 400 and response.json()["detail"] == "連不上"


def test_current_reports_a_missing_setup(env):
    client.post("/api/llm/select", json={"provider": "claude_cli"})
    env.clear()
    connect_llm.update_env({"LLM_PROVIDER": "anthropic_api"})  # chosen, but no key saved
    assert client.get("/api/llm/current").json()["problem"] == anthropic_api.MSG_NO_KEY


async def test_invalid_provider_fails_with_a_message_when_asking(monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(_env_file=None, llm_provider="nope"))
    deps.llm_dep.cache_clear()
    try:
        provider = deps.llm_dep()  # a typo in .env must not turn into a server error
        assert isinstance(provider, UnavailableProvider)
        with pytest.raises(LLMError, match="LLM_PROVIDER=nope") as error:
            await provider.generate("s", "u")
        assert error.value.retryable is False
    finally:
        deps.llm_dep.cache_clear()
