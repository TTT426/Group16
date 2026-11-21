"""Application settings, loaded from environment variables / `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "group16.db"


class Settings(BaseSettings):
    # `.env` is read from the repo root, so commands work from any working directory.
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    # SQLite database file (built into Python, no database server). Relative paths are relative to the repo root.
    database_path: Path = DEFAULT_DB_PATH

    # LLM: auto | claude_cli | anthropic_api | fake
    llm_provider: str = "auto"
    llm_model: str = ""  # empty -> provider default
    llm_effort: str = "medium"  # anthropic_api only; empty -> not sent
    llm_timeout_s: float = 180.0
    llm_max_concurrency: int = 2

    # claude_cli provider
    claude_cli_path: str = "claude"
    claude_cli_strip_api_key: bool = True

    # Embeddings: auto | fastembed | hashing
    embedding_provider: str = "auto"
    embedding_model: str = ""  # empty -> provider default

    # Connectors
    github_token: str = ""
    github_repo: str = ""  # owner/repo
    github_include_markdown: bool = True
    notion_token: str = ""  # the integration only sees pages explicitly shared with it
    discord_bot_token: str = ""  # bot needs the Message Content intent
    discord_guild_id: str = ""

    @property
    def db_file(self) -> Path:
        path = Path(self.database_path).expanduser()
        return path if path.is_absolute() else REPO_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
