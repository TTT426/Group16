"""Application settings, loaded from environment variables / `.env`."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://group16:group16@localhost:5432/group16"

    # LLM
    llm_provider: str = "claude_cli"
    llm_model: str = ""  # empty -> provider default
    llm_effort: str = "medium"  # anthropic_api only; empty -> not sent
    llm_timeout_s: float = 180.0
    llm_max_concurrency: int = 2

    # claude_cli provider
    claude_cli_path: str = "claude"
    claude_cli_strip_api_key: bool = True

    # Embeddings: bge (sentence-transformers, local) | hashing (offline / tests, lexical only)
    embedding_provider: str = "bge"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # Connectors
    github_token: str = ""
    github_repo: str = ""  # owner/repo
    github_include_markdown: bool = True
    notion_token: str = ""  # the integration only sees pages explicitly shared with it
    discord_bot_token: str = ""  # bot needs the Message Content intent
    discord_guild_id: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
