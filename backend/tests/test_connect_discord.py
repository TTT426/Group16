"""/connect/discord: the bot check (mocked HTTP) and the routes."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app import discord_account as discord
from app.api import connect_discord
from app.config import Settings
from app.connectors.base import NormalizedDocument
from app.connectors.scenario import DISCORD_GUILD_ID as SCENARIO_GUILD_ID
from app.embeddings.hashing import HashingEmbedder
from app.ingest.pipeline import ingest_documents
from app.main import app


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


def check_result(message_content: bool = True, guilds: list[dict] | None = None) -> dict:
    return {"bot": "group16-bot", "invite_url": "https://x", "portal_url": "https://y",
            "message_content": message_content, "guilds": guilds or []}


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


# ---------------------------------------------------------------- routes


@pytest.fixture
def saved(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(connect_discord, "update_env", calls.append)
    monkeypatch.setattr(connect_discord, "get_settings", lambda: Settings(_env_file=None))
    return calls


def test_save_token_picks_the_only_server_and_never_echoes_the_token(monkeypatch, saved):
    def fake_check(token, client=None):
        if token != "good":
            raise discord.DiscordError(discord.MSG_BAD_TOKEN)
        return check_result(guilds=[{"id": "7", "name": "Team"}])

    monkeypatch.setattr(discord, "check", fake_check)
    client = TestClient(app)
    assert client.post("/api/discord/token", json={"token": "bad"}).status_code == 400
    assert saved == []
    response = client.post("/api/discord/token", json={"token": " good "})
    assert response.status_code == 200 and "good" not in response.text
    assert saved == [{"DISCORD_BOT_TOKEN": "good", "DISCORD_GUILD_ID": "7"}]


def test_save_token_leaves_the_server_open_when_the_bot_is_in_several(monkeypatch, saved):
    monkeypatch.setattr(discord, "check", lambda token, client=None: check_result(
        guilds=[{"id": "7", "name": "A"}, {"id": "8", "name": "B"}]))
    TestClient(app).post("/api/discord/token", json={"token": "good"})
    assert saved == [{"DISCORD_BOT_TOKEN": "good", "DISCORD_GUILD_ID": ""}]


def test_choose_server_must_be_one_the_bot_joined(monkeypatch, saved):
    monkeypatch.setattr(discord, "check", lambda token, client=None: check_result(guilds=[{"id": "7", "name": "A"}]))
    client = TestClient(app)
    assert client.post("/api/discord/guild", json={"guild_id": "8"}).status_code == 400
    assert client.post("/api/discord/guild", json={"guild_id": "7"}).status_code == 200
    assert saved == [{"DISCORD_GUILD_ID": "7"}]


def test_status_counts_only_the_chosen_server(monkeypatch, db_session):
    monkeypatch.setattr(connect_discord, "get_settings",
                        lambda: Settings(_env_file=None, discord_bot_token="t", discord_guild_id="555"))
    monkeypatch.setattr(discord, "check", lambda token: check_result(guilds=[{"id": "555", "name": "Team"}]))
    ingest_documents(db_session, [
        NormalizedDocument(source="discord", external_id="thread:1", url="https://discord.com/channels/555/1",
                           title="real", text="真的討論"),
        NormalizedDocument(source="discord", external_id="thread:2",
                           url=f"https://discord.com/channels/{SCENARIO_GUILD_ID}/2", title="practice", text="示範"),
    ], HashingEmbedder())
    result = connect_discord._status(db_session)
    assert result["connected"] and result["guild_id"] == "555" and result["documents"] == 1
