"""Read / update the repo's `.env` in place, keeping comments, order and line endings."""

import os
import re
from pathlib import Path

from .config import REPO_ROOT, get_settings

ENV_FILE = REPO_ROOT / ".env"
EXAMPLE_FILE = REPO_ROOT / ".env.example"
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _format(value: str) -> str:
    """Quote a value only when it contains characters a .env parser could misread."""
    if value == "" or re.fullmatch(r"[A-Za-z0-9_./:@+-]+", value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def update_env(updates: dict[str, str], path: Path = ENV_FILE) -> None:
    """Set KEY=value for each entry. Existing keys are replaced in place, new ones appended.

    The file is created from `.env.example` if missing, and readable only by the owner on POSIX.
    Clears the cached Settings so the running server picks up the new values immediately.
    """
    for key, value in updates.items():
        if "\n" in value or "\r" in value:
            raise ValueError(f"{key}: value must be a single line")
    if not path.exists() and path == ENV_FILE and EXAMPLE_FILE.exists():
        path.write_bytes(EXAMPLE_FILE.read_bytes())
    text = path.read_bytes().decode("utf-8") if path.exists() else ""  # bytes: keep \r\n line endings as-is
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    remaining = dict(updates)
    for i, line in enumerate(lines):
        m = _LINE.match(line)
        if m and m.group(1) in remaining:
            key = m.group(1)
            lines[i] = f"{key}={_format(remaining.pop(key))}"
    lines += [f"{key}={_format(value)}" for key, value in remaining.items()]
    path.write_text(newline.join(lines) + newline, encoding="utf-8", newline="")
    if os.name == "posix":
        path.chmod(0o600)
    get_settings.cache_clear()
