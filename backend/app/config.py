"""Application settings, loaded from environment variables / `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "group16.db"


class Settings(BaseSettings):
    # `.env` is read from the repo root, so commands work from any working directory.
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    # SQLite database file (built into Python, no database server). Relative paths are relative to the repo root.
    database_path: Path = DEFAULT_DB_PATH

    # LLM: claude_cli (Claude Code CLI, subscription) | fake (tests / offline development only)
    llm_provider: str = "claude_cli"
    llm_model: str = ""  # empty -> the CLI's current default model
    llm_timeout_s: float = 180.0
    llm_max_concurrency: int = 2
    claude_cli_path: str = "claude"
    claude_cli_strip_api_key: bool = True

    # AI question answering: rag | full | agent (see qa/service.py and docs/EVAL_MODES.md)
    qa_mode: str = "rag"
    qa_top_k: int = 8  # passages given to the model in rag mode
    qa_full_context_chars: int = 200_000  # above this, full mode falls back to rag
    workspace_dir: Path = REPO_ROOT / "data" / "workspace"  # markdown export searched in agent mode

    # Embeddings: auto | fastembed | hashing
    embedding_provider: str = "auto"
    embedding_model: str = ""  # empty -> provider default

    # Connectors
    github_token: str = ""
    github_repo: str = ""  # owner/repo
    github_use_gh_cli: bool = False  # use the GitHub CLI login (`gh auth login`) when no token is saved
    # OAuth App client id for "Sign in with GitHub" (device flow). Public value, no secret needed.
    github_client_id: str = ""
    github_include_markdown: bool = True
    # Seeding only: a throwaway repo the evaluation scenarios are WRITTEN into. Never the team's real repo
    # (GITHUB_REPO, which is only read); scripts/seed_workspace/seed.py refuses to run if the two are the same.
    seed_github_repo: str = ""
    notion_token: str = ""  # the integration only sees pages explicitly shared with it
    notion_parent_page_id: str = ""  # seeding only: page under which the scenario pages are created
    # Seeding only: API token of a SEPARATE connection for the test workspace. Never NOTION_TOKEN, because every page
    # the app's connection can see is imported; seed.py refuses to run if the two are the same.
    seed_notion_token: str = ""
    discord_bot_token: str = ""  # bot needs the Message Content intent
    discord_guild_id: str = ""
    # Seeding only: a SEPARATE test server the scenarios are posted into (the same bot may be in both). Never
    # DISCORD_GUILD_ID: seeding creates channels and threads and would reuse real channels with matching names.
    seed_discord_guild_id: str = ""

    @field_validator("llm_provider")
    @classmethod
    def _legacy_llm_provider(cls, value: str) -> str:
        # .env files created by earlier versions say LLM_PROVIDER=auto; the project now uses only the Claude CLI.
        return "claude_cli" if value.strip().lower() == "auto" else value

    @property
    def db_file(self) -> Path:
        path = Path(self.database_path).expanduser()
        return path if path.is_absolute() else REPO_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
