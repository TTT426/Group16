"""What the /connect/llm page shows: each provider, whether it is ready, and the models it offers.

Two kinds of problems are told apart:
- `setup_problem`: the chosen provider is not set up at all (no key, no model, Claude Code missing or
  logged out). Known without calling any service, so every page can warn about it.
- Anything that needs a real call (bad key, server down, timeout) only shows up when a question is
  asked, or on /connect/llm, which lists each provider's models.
"""

import asyncio
import json
import shutil
import subprocess

from ..config import Settings
from . import anthropic_api, ollama, openai_api
from .base import LLMError

LABELS = {
    "claude_cli": "Claude Code（訂閱）",
    "anthropic_api": "Anthropic API",
    "openai_api": "OpenAI API",
    "ollama": "Ollama（本機模型）",
    "fake": "測試用（不呼叫模型）",
}
CLAUDE_CLI_MODELS = [
    {"id": "", "label": "預設（Claude Code 目前使用的模型）"},
    {"id": "opus", "label": "Opus"},
    {"id": "sonnet", "label": "Sonnet"},
    {"id": "haiku", "label": "Haiku"},
]
MSG_CLI_MISSING = "找不到 Claude Code。請先安裝 Claude Code，並在終端機執行一次 claude 登入。"
MSG_CLI_LOGGED_OUT = "Claude Code 還沒有登入。請在終端機執行 claude，依照畫面登入。"


def claude_cli_login(executable: str) -> dict:
    """{'logged_in': bool, 'method': str} from `claude auth status`; raises LLMError if the CLI is missing."""
    exe = shutil.which(executable)
    if not exe:
        raise LLMError(MSG_CLI_MISSING)
    try:
        out = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=20).stdout
        data = json.loads(out)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {"logged_in": None, "method": ""}  # older CLI without `auth status`: the test call will tell
    return {"logged_in": bool(data.get("loggedIn")), "method": data.get("authMethod") or ""}


def _entry(provider: str, **fields) -> dict:
    return {"id": provider, "label": LABELS[provider], "ready": False, "error": None, "models": [],
            "agent_mode": provider == "claude_cli", **fields}


async def _claude_cli(settings: Settings) -> dict:
    entry = _entry("claude_cli", models=list(CLAUDE_CLI_MODELS), account=None)
    try:
        login = await asyncio.to_thread(claude_cli_login, settings.claude_cli_path)
    except LLMError as exc:
        return {**entry, "error": str(exc)}
    if login["logged_in"] is False:
        return {**entry, "error": MSG_CLI_LOGGED_OUT}
    return {**entry, "ready": True, "account": login["method"]}


async def _anthropic(settings: Settings) -> dict:
    entry = _entry("anthropic_api", key_saved=bool(settings.anthropic_api_key),
                   default_model=anthropic_api.DEFAULT_MODEL)
    if not settings.anthropic_api_key:
        return entry
    try:
        return {**entry, "ready": True, "models": await anthropic_api.list_models(settings.anthropic_api_key)}
    except LLMError as exc:
        return {**entry, "error": str(exc)}


async def _openai(settings: Settings) -> dict:
    base_url = settings.openai_base_url
    entry = _entry("openai_api", key_saved=bool(settings.openai_api_key), base_url=base_url,
                   default_base_url=openai_api.DEFAULT_BASE_URL)
    if not settings.openai_api_key and not base_url:
        return entry
    try:
        models = await asyncio.to_thread(openai_api.list_models, settings.openai_api_key, base_url)
        return {**entry, "ready": True, "models": models}
    except LLMError as exc:
        return {**entry, "error": str(exc)}


async def _ollama(settings: Settings) -> dict:
    entry = _entry("ollama", base_url=settings.ollama_base_url, default_base_url=ollama.DEFAULT_BASE_URL)
    try:
        models = await asyncio.to_thread(ollama.list_models, settings.ollama_base_url)
    except LLMError as exc:
        return {**entry, "error": str(exc)}
    if not models:
        return {**entry, "error": "Ollama 已開啟，但還沒有下載任何模型。請在終端機執行 ollama pull qwen3:8b。"}
    return {**entry, "ready": True, "models": models}


def setup_problem(settings: Settings) -> str | None:
    """Why the chosen provider cannot be used at all, or None. No network calls."""
    provider, model = settings.llm_provider, settings.llm_model
    if provider == "claude_cli":
        try:
            login = claude_cli_login(settings.claude_cli_path)
        except LLMError as exc:
            return str(exc)
        return MSG_CLI_LOGGED_OUT if login["logged_in"] is False else None
    if provider == "anthropic_api":
        return None if settings.anthropic_api_key else anthropic_api.MSG_NO_KEY
    if provider == "openai_api":
        if not settings.openai_api_key and not settings.openai_base_url:
            return "還沒有設定 OpenAI API key。"
        return None if model else "還沒有選擇模型。"
    if provider == "ollama":
        return None if model else "還沒有選擇 Ollama 模型。"
    if provider == "fake":
        return None
    return f"不認得 LLM_PROVIDER={provider}。"


def current(settings: Settings) -> dict:
    """The model in use, a readable label, and `problem` (see setup_problem)."""
    provider, model = settings.llm_provider, settings.llm_model
    label = LABELS.get(provider, provider)
    if provider == "claude_cli":
        model_label = next((m["label"] for m in CLAUDE_CLI_MODELS if m["id"] == model and model), model or "預設模型")
    else:
        model_label = model or (anthropic_api.DEFAULT_MODEL if provider == "anthropic_api" else "尚未選擇模型")
    return {"provider": provider, "model": model, "label": f"{label} · {model_label}",
            "agent_mode": provider in ("claude_cli", "fake"), "problem": setup_problem(settings)}


async def status(settings: Settings) -> dict:
    providers = await asyncio.gather(_claude_cli(settings), _anthropic(settings), _openai(settings),
                                     _ollama(settings))
    return {"current": await asyncio.to_thread(current, settings), "providers": list(providers)}
