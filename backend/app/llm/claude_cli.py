"""Claude Code CLI provider — uses the logged-in Claude Pro/Max subscription instead of API billing.

Runs `claude -p --output-format json` as a subprocess, the system prompt passed
as an argument and the user prompt on stdin. Built-in tools are disabled, except
when a `workspace` folder is given: then only the read-only Read / Grep / Glob
tools are available, inside that folder, so Claude can search the files itself.

Notes:
- Subscription usage has rate limits and is meant for personal use.
- `ANTHROPIC_API_KEY` is removed from the child environment by default, so the
  CLI does not silently switch to pay-as-you-go API billing.
- `max_tokens` is not supported by the CLI and is ignored.
- On Windows `claude` is an npm `.cmd` shim, and cmd.exe mangles non-ASCII command-line arguments.
  The (Chinese) system prompt is therefore passed as a UTF-8 file, the user prompt on stdin, and the
  JSON schema ASCII-escaped, so no non-ASCII text ever goes through the command line.
"""

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from .base import LLMError, LLMResult


class ClaudeCLIProvider:
    name = "claude_cli"
    supports_workspace = True

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

    READ_ONLY_TOOLS = "Read,Grep,Glob"

    def build_args(self, system: str, *, workspace: Path | None = None, json_schema: dict | None = None) -> list[str]:
        exe = shutil.which(self.executable) or self.executable
        args = [exe, "-p", "--output-format", "json", "--no-session-persistence",
                "--system-prompt-file", str(self._system_prompt_file(system))]
        if workspace is None:
            args += ["--tools", ""]
        else:
            # Only read-only search tools; anything else is denied without prompting.
            args += ["--tools", self.READ_ONLY_TOOLS, "--allowedTools", self.READ_ONLY_TOOLS,
                     "--permission-mode", "dontAsk"]
        if json_schema is not None:
            # The CLI validates the final answer against the schema and returns it as `structured_output`.
            args += ["--json-schema", json.dumps(json_schema, ensure_ascii=True)]
        if self.model:
            args += ["--model", self.model]
        return args

    def _system_prompt_file(self, system: str) -> Path:
        digest = hashlib.sha256(system.encode("utf-8")).hexdigest()[:16]
        path = Path(self._workdir) / f"system-{digest}.txt"
        if not path.exists():
            path.write_bytes(system.encode("utf-8"))
        return path

    def build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.strip_api_key:
            env.pop("ANTHROPIC_API_KEY", None)
        return env

    async def generate(
        self, system: str, user: str, *, max_tokens: int = 4000, workspace: Path | None = None,
        json_schema: dict | None = None,
    ) -> LLMResult:
        async with self._semaphore:
            start = time.perf_counter()
            args = self.build_args(system, workspace=workspace, json_schema=json_schema)
            stdout, stderr, returncode = await self._run(args, user, cwd=workspace or self._workdir)
            latency_ms = int((time.perf_counter() - start) * 1000)
        return self.parse_output(stdout, stderr, returncode, latency_ms)

    async def _run(self, args: list[str], stdin_text: str, cwd: Path | str | None = None) -> tuple[bytes, bytes, int]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd or self._workdir),
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
        structured = data.get("structured_output")
        text = json.dumps(structured, ensure_ascii=False) if structured is not None else (data.get("result") or "")
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
