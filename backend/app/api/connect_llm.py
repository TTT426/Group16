"""/connect/llm: choose the AI model that writes answers (provider + model), save API keys, test it.

Same rules as the tool connect routes: localhost only, no cross-site requests, keys are never sent back.
The choice is saved to `.env` (LLM_PROVIDER / LLM_MODEL) and takes effect for the next question.
"""

import asyncio
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import get_settings
from ..envfile import update_env
from ..llm import anthropic_api, catalog, ollama, openai_api
from ..llm.base import LLMError
from ..llm.factory import get_provider
from .deps import llm_dep
from .hub import local_only, page

router = APIRouter(dependencies=[Depends(local_only)], tags=["connect"])

Provider = Literal["claude_cli", "anthropic_api", "openai_api", "ollama"]
KEY_SETTINGS = {"anthropic_api": "ANTHROPIC_API_KEY", "openai_api": "OPENAI_API_KEY"}
CLI_MODEL = re.compile(r"[A-Za-z0-9._\[\]-]{0,80}")  # an alias (opus) or a full model name
TEST_SYSTEM = "You are a concise assistant. Reply in Traditional Chinese, in one sentence."
TEST_PROMPT = "請用一句話介紹你自己，並說出你是哪一個模型。"


async def _models(provider: str) -> list[dict]:
    """The models a provider offers right now (raises LLMError if it is not set up)."""
    s = get_settings()
    if provider == "anthropic_api":
        return await anthropic_api.list_models(s.anthropic_api_key)
    if provider == "openai_api":
        return await asyncio.to_thread(openai_api.list_models, s.openai_api_key, s.openai_base_url)
    if provider == "ollama":
        return await asyncio.to_thread(ollama.list_models, s.ollama_base_url)
    return catalog.CLAUDE_CLI_MODELS


def _select(provider: str, model: str) -> dict:
    update_env({"LLM_PROVIDER": provider, "LLM_MODEL": model})
    llm_dep.cache_clear()
    return catalog.current(get_settings())


@router.get("/connect/llm", include_in_schema=False)
def llm_page() -> FileResponse:
    return page("connect-llm.html")


@router.get("/api/llm/status")
async def status() -> dict:
    """Every provider, checked for real (lists each one's models): for /connect/llm and the ask page picker."""
    return await catalog.status(get_settings())


@router.get("/api/llm/current")
def current() -> dict:
    """The model in use and whether it is set up, without calling any service."""
    return catalog.current(get_settings())


class KeyIn(BaseModel):
    provider: Literal["anthropic_api", "openai_api"]
    api_key: str = ""
    base_url: str = ""  # openai_api only: an OpenAI-compatible server; empty = api.openai.com


@router.post("/api/llm/key")
async def save_key(body: KeyIn) -> dict:
    key, base_url = body.api_key.strip(), body.base_url.strip().rstrip("/")
    if base_url and not re.match(r"https?://", base_url):
        raise HTTPException(400, "網址要以 http:// 或 https:// 開頭。")
    try:
        if body.provider == "anthropic_api":
            models = await anthropic_api.list_models(key)
        else:
            if not key and not base_url:
                raise LLMError(openai_api.MSG_NO_KEY)
            models = await asyncio.to_thread(openai_api.list_models, key, base_url)
    except LLMError as exc:
        raise HTTPException(400, str(exc)) from exc
    updates = {KEY_SETTINGS[body.provider]: key}
    if body.provider == "openai_api":
        updates["OPENAI_BASE_URL"] = base_url
    update_env(updates)
    llm_dep.cache_clear()
    return {"models": models}


class OllamaIn(BaseModel):
    base_url: str = ""


@router.post("/api/llm/ollama")
def save_ollama(body: OllamaIn) -> dict:
    base_url = body.base_url.strip().rstrip("/")
    if base_url and not re.match(r"https?://", base_url):
        raise HTTPException(400, "網址要以 http:// 或 https:// 開頭。")
    try:
        models = ollama.list_models(base_url)
    except LLMError as exc:
        raise HTTPException(400, str(exc)) from exc
    update_env({"OLLAMA_BASE_URL": base_url})
    llm_dep.cache_clear()
    return {"models": models}


class ForgetIn(BaseModel):
    provider: Literal["anthropic_api", "openai_api"]


@router.post("/api/llm/forget")
def forget_key(body: ForgetIn) -> dict:
    """Remove a saved key; if that provider was in use, go back to Claude Code."""
    update_env({KEY_SETTINGS[body.provider]: ""})
    if get_settings().llm_provider == body.provider:
        return _select("claude_cli", "")
    llm_dep.cache_clear()
    return catalog.current(get_settings())


class SelectIn(BaseModel):
    provider: Provider
    model: str = ""


@router.post("/api/llm/select")
async def select(body: SelectIn) -> dict:
    model = body.model.strip()
    if body.provider == "claude_cli":
        if not CLI_MODEL.fullmatch(model):
            raise HTTPException(400, "模型名稱只能包含英文字母、數字和 - . _。")
    else:
        try:
            offered = {m["id"] for m in await _models(body.provider)}
        except LLMError as exc:
            raise HTTPException(400, str(exc)) from exc
        if model not in offered:
            raise HTTPException(400, f"{catalog.LABELS[body.provider]} 沒有提供模型 {model or '（空白）'}。")
    return _select(body.provider, model)


class TestIn(BaseModel):
    provider: Provider | None = None  # default: the model in use
    model: str | None = None


@router.post("/api/llm/test")
async def test(body: TestIn) -> dict:
    """Ask the model one short question, so the user sees it really answers (and which model it is)."""
    provider = get_provider(get_settings(), body.provider, body.model)
    try:
        result = await provider.generate(TEST_SYSTEM, TEST_PROMPT)
    except LLMError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"text": result.text.strip(), "provider": result.provider, "model": result.model,
            "latency_ms": result.latency_ms}
