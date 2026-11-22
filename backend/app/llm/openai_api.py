"""OpenAI API provider (or any OpenAI-compatible server, e.g. OpenRouter, LM Studio, vLLM).

Calls `POST {base_url}/chat/completions` with httpx (no extra dependency). Replies are
constrained with a strict `json_schema` response format when a JSON schema is given.
"""

import time
from pathlib import Path

import httpx

from .base import LLMError, LLMResult
from .json_utils import strict_schema

DEFAULT_BASE_URL = "https://api.openai.com/v1"
# On api.openai.com the model list also holds embedding, audio and image models; keep chat models only.
_CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt-")
_NOT_CHAT = ("embedding", "audio", "realtime", "transcribe", "tts", "image", "search", "moderation", "instruct")

MSG_NO_KEY = "還沒有設定 API key。"
MSG_BAD_KEY = "API key 無效，請重新建立一把。"
MSG_RATE_LIMIT = "API 使用量已達上限（或帳號額度不足），請稍後再試。"


def _base(base_url: str) -> str:
    return (base_url or DEFAULT_BASE_URL).rstrip("/")


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    if response.status_code == 401:
        raise LLMError(MSG_BAD_KEY)
    if response.status_code == 429:
        raise LLMError(MSG_RATE_LIMIT)
    try:
        detail = response.json().get("error", {}).get("message") or response.text
    except ValueError:
        detail = response.text
    raise LLMError(f"API 錯誤（{response.status_code}）：{str(detail)[:300]}")


def _request(method: str, url: str, api_key: str, timeout_s: float, client: httpx.Client | None = None,
             **kwargs) -> dict:
    """Synchronous request (used for the model list); `client` is for tests."""
    try:
        if client is not None:
            response = client.request(method, url, headers=_headers(api_key), **kwargs)
        else:
            with httpx.Client(timeout=timeout_s) as c:
                response = c.request(method, url, headers=_headers(api_key), **kwargs)
    except httpx.HTTPError as exc:
        raise LLMError(f"連不上 {url}，請檢查網址和網路。") from exc
    _raise_for_status(response)
    return response.json()


def list_models(api_key: str, base_url: str = "", timeout_s: float = 10.0,
                client: httpx.Client | None = None) -> list[dict]:
    """The models this key can use: [{'id', 'label'}]. Also how a key is checked."""
    if not api_key and _base(base_url) == DEFAULT_BASE_URL:
        raise LLMError(MSG_NO_KEY)
    data = _request("GET", f"{_base(base_url)}/models", api_key, timeout_s, client)
    ids = sorted(m["id"] for m in data.get("data", []) if m.get("id"))
    if _base(base_url) == DEFAULT_BASE_URL:
        ids = [i for i in ids if i.startswith(_CHAT_PREFIXES) and not any(x in i for x in _NOT_CHAT)]
    return [{"id": i, "label": i} for i in ids]


class OpenAIAPIProvider:
    name = "openai_api"
    supports_workspace = False

    def __init__(self, api_key: str, model: str, *, base_url: str = "", timeout_s: float = 180.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = _base(base_url)
        self.timeout_s = timeout_s
        self._transport = transport  # tests

    async def generate(
        self, system: str, user: str, *, max_tokens: int = 4000, workspace: Path | None = None,
        json_schema: dict | None = None,
    ) -> LLMResult:
        if not self.model:
            raise LLMError("還沒有選擇模型。")
        if not self.api_key and self.base_url == DEFAULT_BASE_URL:
            raise LLMError(MSG_NO_KEY)
        body: dict = {"model": self.model,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "reply", "strict": True, "schema": strict_schema(json_schema)}}

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, transport=self._transport) as client:
                response = await client.post(f"{self.base_url}/chat/completions", json=body,
                                             headers=_headers(self.api_key))
        except httpx.TimeoutException as exc:
            raise LLMError(f"模型超過 {self.timeout_s:.0f} 秒沒有回應。") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"連不上 {self.base_url}，請檢查網址和網路。") from exc
        latency_ms = int((time.perf_counter() - start) * 1000)
        _raise_for_status(response)

        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        if message.get("refusal"):
            raise LLMError(f"模型拒絕回答：{message['refusal']}")
        text = message.get("content") or ""
        if not text.strip():
            raise LLMError("模型回傳了空白的回答。")
        usage = data.get("usage") or {}
        return LLMResult(text=text, provider=self.name, model=data.get("model") or self.model,
                         input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
                         latency_ms=latency_ms)
