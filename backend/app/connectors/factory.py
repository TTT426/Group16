"""Build connectors from settings."""

from ..config import Settings
from .base import Connector, ConnectorError

SOURCES = ("github", "notion", "discord")


def build_connector(name: str, settings: Settings) -> Connector:
    if name == "github":
        from ..github_account import configured_repo, current_token
        from .github import GitHubConnector

        repo = configured_repo(settings)
        if not repo:
            raise ConnectorError("github: no repo chosen yet. Connect one on the /connect page.")
        token, _ = current_token(settings)  # saved token, or the gh CLI login if the user chose it
        return GitHubConnector(repo, token, include_markdown=settings.github_include_markdown)
    if name == "notion":
        from .notion import NotionConnector

        return NotionConnector(settings.notion_token)
    if name == "discord":
        from .discord import DiscordConnector

        return DiscordConnector(settings.discord_bot_token, settings.discord_guild_id)
    raise ValueError(f"Unknown source {name!r}. Use one of: {', '.join(SOURCES)}.")
