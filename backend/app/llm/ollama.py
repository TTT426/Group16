"""Ollama provider: open models running locally (free, nothing leaves this computer).

Calls the Ollama server's `POST /api/chat` with httpx. A JSON schema is passed as `format`,
which Ollama enforces while generating. Ollama's default context window is small and silently
cuts long prompts, so `num_ctx` is raised to OLLAMA_NUM_CTX tokens.
"""

import time
from pathlib import Path

import httpx

from .base import LLMError, LLMResult

DEFAULT_BASE_URL = "http://localhost:11434"

MSG_NOT_RUNNING = "連不上 Ollama。請確認 Ollama 已安裝並開啟（ollama.com）。"


def _base(base_url: str) -> str:
    return (base_url or DEFAULT_BASE_URL).rstrip("/")


def list_models(base_url: str = "", timeout_s: float = 5.0, client: httpx.Client | None = None) -> list[dict]:
    """Models already downloaded (`ollama pull`): [{'id', 'label'}]. Also how the server is checked."""
    url = f"{_base(base_url)}/api/tags"
    try:
        if client is not None:
            response = client.get(url)
        else:
            response = httpx.get(url, timeout=timeout_s)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMError(MSG_NOT_RUNNING, retryable=False) from exc
    models = []
    for m in response.json().get("models", []):
        details = m.get("details") or {}
        size = " ".join(x for x in (details.get("parameter_size"), details.get("quantization_level")) if x)
        models.append({"id": m["name"], "label": f"{m['name']}（{size}）" if size else m["name"]})
    return models


class OllamaProvider:
    name = "ollama"
    supports_workspace = False

    def __init__(self, model: str, *, base_url: str = "", num_ctx: int = 16384, timeout_s: float = 180.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.model = model
        self.base_url = _base(base_url)
        self.num_ctx = num_ctx
        self.timeout_s = timeout_s
        self._transport = transport  # tests

    async def generate(
        self, system: str, user: str, *, max_tokens: int = 4000, workspace: Path | None = None,
        json_schema: dict | None = None,
    ) -> LLMResult:
        if not self.model:
            raise LLMError("還沒有選擇 Ollama 模型。", retryable=False)
        body: dict = {"model": self.model, "stream": False,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.num_ctx:
            body["options"] = {"num_ctx": self.num_ctx}
        if json_schema is not None:
            body["format"] = json_schema

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, transport=self._transport) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=body)
        except httpx.TimeoutException as exc:
            raise LLMError(f"Ollama 超過 {self.timeout_s:.0f} 秒沒有回應（本機模型第一次載入比較慢）。",
                           retryable=False) from exc
        except httpx.HTTPError as exc:
            raise LLMError(MSG_NOT_RUNNING, retryable=False) from exc
        latency_ms = int((time.perf_counter() - start) * 1000)
        if response.status_code == 404:
            raise LLMError(f"Ollama 找不到模型 {self.model}，請先執行 ollama pull {self.model}。", retryable=False)
        if response.status_code >= 400:
            raise LLMError(f"Ollama 錯誤（{response.status_code}）：{response.text[:300]}")

        data = response.json()
        text = (data.get("message") or {}).get("content") or ""
        if not text.strip():
            raise LLMError("Ollama 回傳了空白的回答。")
        return LLMResult(text=text, provider=self.name, model=data.get("model") or self.model,
                         input_tokens=data.get("prompt_eval_count"), output_tokens=data.get("eval_count"),
                         latency_ms=latency_ms)
