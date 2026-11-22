"""Discord connection check for the /connect pages.

Discord has no sign-in a local app can use without a server-side secret, so the team creates one bot, the
user pastes its token, and invites it to the team's server. The check confirms the token and works out
everything else: the invite link, whether the Message Content intent is on, and which servers the bot is in.
"""

from urllib.parse import urlencode

import httpx

from .connectors.discord import API_URL

# What the bot needs to read history: View Channels (1 << 10) + Read Message History (1 << 16).
BOT_PERMISSIONS = (1 << 10) | (1 << 16)
# Application flags meaning the Message Content intent is enabled (GATEWAY_MESSAGE_CONTENT and its _LIMITED form).
MESSAGE_CONTENT_FLAGS = (1 << 18) | (1 << 19)

# User-facing messages (shown as-is in the /connect pages, so they are in the UI language).
MSG_NETWORK = "連不到 Discord，請檢查網路連線。"
MSG_BAD_TOKEN = "Discord bot token 無效。請到 Bot 頁面按「Reset Token」重新複製。"
MSG_BAD_STATUS = "Discord 回應錯誤（{status}）。"
MSG_EMPTY_TOKEN = "請貼上 bot token。"
MSG_NOT_IN_SERVER = "Bot 不在這個伺服器裡，請先邀請它，或選擇其他伺服器。"


class DiscordError(Exception):
    """An error whose message can be shown to the user as-is."""


def invite_url(application_id: str) -> str:
    query = urlencode({"client_id": application_id, "scope": "bot", "permissions": BOT_PERMISSIONS})
    return f"https://discord.com/oauth2/authorize?{query}"


def check(token: str, client: httpx.Client | None = None) -> dict:
    """The bot's name, invite link, whether Message Content is enabled, and the servers it has joined."""
    if not token:
        raise DiscordError(MSG_EMPTY_TOKEN)
    headers = {"Authorization": f"Bot {token}"}
    own_client = client is None
    http = client or httpx.Client(timeout=20.0)
    try:
        me = http.get(f"{API_URL}/users/@me", headers=headers)
        if me.status_code == 401:
            raise DiscordError(MSG_BAD_TOKEN)
        if me.status_code != 200:
            raise DiscordError(MSG_BAD_STATUS.format(status=me.status_code))
        app = http.get(f"{API_URL}/applications/@me", headers=headers)
        guilds = http.get(f"{API_URL}/users/@me/guilds", headers=headers)
        if app.status_code != 200 or guilds.status_code != 200:
            raise DiscordError(MSG_BAD_STATUS.format(status=app.status_code if app.status_code != 200
                                                     else guilds.status_code))
    except httpx.HTTPError as exc:
        raise DiscordError(MSG_NETWORK) from exc
    finally:
        if own_client:
            http.close()
    application = app.json()
    application_id = application.get("id") or me.json().get("id", "")
    return {
        "bot": me.json().get("username", ""),
        "invite_url": invite_url(application_id),
        "portal_url": f"https://discord.com/developers/applications/{application_id}/bot",
        "message_content": bool(application.get("flags", 0) & MESSAGE_CONTENT_FLAGS),
        "guilds": [{"id": g["id"], "name": g.get("name", "")} for g in guilds.json()],
    }
