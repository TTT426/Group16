"""Claude Code CLI provider — uses the logged-in Claude Pro/Max subscription instead of API billing.

Runs `claude -p --output-format json` as a subprocess with all built-in tools
disabled, the system prompt passed as an argument and the user prompt on stdin.

Notes:
- Subscription usage has rate limits and is meant for personal use. Good for
  development and demos; switch to `anthropic_api` for heavier or shared use.
- `ANTHROPIC_API_KEY` is removed from the child environment by default, so the
  CLI does not silently switch to pay-as-you-go API billing.
- `max_tokens` is not supported by the CLI and is ignored.
"""

import asyncio
import json
import os
import shutil
import tempfile
import time

from .base import LLMError, LLMResult


class ClaudeCLIProvider:
    name = "claude_cli"

    def __init__(
        self,
        model: str = "",
        *,
        executable: str = "claude",
        timeout_s: float = 180.0,
        max_concurrency: int = 2,
        strip_api_key: bool = True,
    ) -> None:
        self.model = model
        self.executable = executable
        self.timeout_s = timeout_s
        self.strip_api_key = strip_api_key
        self._semaphore = asyncio.Semaphore(max_concurrency)
        # Run outside the repo so the CLI does not pick up project instructions / settings.
        self._workdir = tempfile.mkdtemp(prefix="group16-claude-cli-")

    def build_args(self, system: str) -> list[str]:
        exe = shutil.which(self.executable) or self.executable
        args = [
            exe,
            "-p",
            "--output-format", "json",
            "--tools", "",
            "--no-session-persistence",
            "--system-prompt", system,
        ]
        if self.model:
            args += ["--model", self.model]
        return args

    def build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.strip_api_key:
            env.pop("ANTHROPIC_API_KEY", None)
        return env

    async def generate(self, system: str, user: str, *, max_tokens: int = 4000) -> LLMResult:
        async with self._semaphore:
            start = time.perf_counter()
            stdout, stderr, returncode = await self._run(self.build_args(system), user)
            latency_ms = int((time.perf_counter() - start) * 1000)
        return self.parse_output(stdout, stderr, returncode, latency_ms)

    async def _run(self, args: list[str], stdin_text: str) -> tuple[bytes, bytes, int]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._workdir,
                env=self.build_env(),
            )
        except FileNotFoundError as exc:
            raise LLMError(
                f"Claude CLI not found ({self.executable!r}). Install Claude Code and run `claude` once to log in."
            ) from exc
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(stdin_text.encode("utf-8")), timeout=self.timeout_s
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise LLMError(f"Claude CLI timed out after {self.timeout_s}s") from exc
        return stdout, stderr, proc.returncode

    def parse_output(self, stdout: bytes, stderr: bytes, returncode: int, latency_ms: int) -> LLMResult:
        raw = stdout.decode("utf-8", errors="replace").strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise LLMError(f"Claude CLI returned non-JSON output (exit {returncode}): {err or raw[:500]}") from exc

        if data.get("is_error") or returncode != 0:
            raise LLMError(f"Claude CLI error (exit {returncode}): {data.get('result') or data}")
        text = data.get("result") or ""
        if not text.strip():
            raise LLMError("Claude CLI returned an empty result.")

        usage = data.get("usage") or {}
        # The CLI may also run a small background model; report the one that wrote the most output.
        model_usage = data.get("modelUsage") or {}
        model = self.model or "claude-cli-default"
        if model_usage:
            key, info = max(model_usage.items(), key=lambda kv: (kv[1] or {}).get("outputTokens", 0))
            model = (info or {}).get("canonicalModel") or key.split("[", 1)[0]  # "claude-opus-5-5[1m]"

        return LLMResult(
            text=text,
            provider=self.name,
            model=model,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            latency_ms=latency_ms,
        )
