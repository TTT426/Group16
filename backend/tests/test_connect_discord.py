"""Discord bot check (mocked HTTP)."""

import httpx
import pytest

from app import discord_account as discord


def mock_client(flags: int, guilds: list[dict], me_status: int = 200) -> httpx.Client:
    routes = {
        "/api/v10/users/@me": (me_status, {"id": "99", "username": "group16-bot"}),
        "/api/v10/applications/@me": (200, {"id": "42", "flags": flags}),
        "/api/v10/users/@me/guilds": (200, guilds),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        status, body = routes.get(request.url.path, (404, {}))
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------- check


def test_check_reports_bot_invite_intent_and_servers():
    result = discord.check("tok", mock_client(1 << 19, [{"id": "1", "name": "Team"}]))
    assert result["bot"] == "group16-bot" and result["message_content"] is True
    assert result["invite_url"].startswith("https://discord.com/oauth2/authorize?client_id=42")
    assert "permissions=66560" in result["invite_url"]  # View Channels + Read Message History only
    assert result["portal_url"].endswith("/applications/42/bot")
    assert result["guilds"] == [{"id": "1", "name": "Team"}]
    assert discord.check("tok", mock_client(0, []))["message_content"] is False


def test_check_errors():
    with pytest.raises(discord.DiscordError) as empty:
        discord.check("")
    assert str(empty.value) == discord.MSG_EMPTY_TOKEN
    with pytest.raises(discord.DiscordError) as bad:
        discord.check("bad", mock_client(0, [], me_status=401))
    assert str(bad.value) == discord.MSG_BAD_TOKEN
