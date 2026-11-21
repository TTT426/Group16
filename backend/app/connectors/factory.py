"""Build connectors from settings."""

from ..config import Settings
from .base import Connector, ConnectorError

SOURCES = ("github", "notion", "discord")


def build_connector(name: str, settings: Settings) -> Connector:
    if name == "github":
        from .github import GitHubConnector

        if not settings.github_repo:
            raise ConnectorError("github: GITHUB_REPO is not set (expected 'owner/repo').")
        return GitHubConnector(
            settings.github_repo, settings.github_token, include_markdown=settings.github_include_markdown
        )
    if name == "notion":
        from .notion import NotionConnector

        return NotionConnector(settings.notion_token)
    if name == "discord":
        from .discord import DiscordConnector

        return DiscordConnector(settings.discord_bot_token, settings.discord_guild_id)
    raise ValueError(f"Unknown source {name!r}. Use one of: {', '.join(SOURCES)}.")
