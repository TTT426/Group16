"""Discord connector (REST API, bot token).

- Each thread (incl. forum posts, active and archived) becomes one document.
- Channel messages outside threads are grouped into time windows, one document per window.

The bot must be in the server, have "Read Message History", and the
"Message Content" privileged intent must be enabled in the developer portal,
otherwise message text comes back empty.
"""

import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta

import httpx

from .base import ConnectorError, NormalizedDocument, parse_datetime
from .http import request

API_URL = "https://discord.com/api/v10"

TEXT_CHANNEL, ANNOUNCEMENT_CHANNEL, FORUM_CHANNEL = 0, 5, 15
MESSAGE_CHANNELS = {TEXT_CHANNEL, ANNOUNCEMENT_CHANNEL}
THREAD_PARENTS = {TEXT_CHANNEL, ANNOUNCEMENT_CHANNEL, FORUM_CHANNEL}
THREAD_STARTER_MESSAGE = 21


def format_messages(messages: list[tuple[str, str, str]]) -> str:
    """`messages` = [(author, iso_timestamp, content)] in chronological order."""
    return "\n".join(f"{author} ({ts[:16].replace('T', ' ')}): {content}" for author, ts, content in messages)


def _author(message: dict) -> str:
    user = message.get("author") or {}
    return user.get("global_name") or user.get("username") or "unknown"


def _content(message: dict) -> str:
    if message.get("type") == THREAD_STARTER_MESSAGE and message.get("referenced_message"):
        message = message["referenced_message"]
    parts = [message.get("content") or ""]
    parts += [f"[attachment: {a.get('filename', '')}]" for a in message.get("attachments", [])]
    return " ".join(p for p in parts if p).strip()


class DiscordConnector:
    source = "discord"

    def __init__(
        self,
        token: str,
        guild_id: str,
        *,
        window: timedelta = timedelta(hours=24),
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not token or not guild_id:
            raise ConnectorError("discord: DISCORD_BOT_TOKEN and DISCORD_GUILD_ID must be set.")
        self.guild_id = guild_id
        self.window = window
        self._client = client or httpx.Client(base_url=API_URL, timeout=30.0)
        self._client.headers.update({"Authorization": f"Bot {token}"})
        self._sleep = sleep

    def fetch(self) -> Iterator[NormalizedDocument]:
        channels = self._get(f"/guilds/{self.guild_id}/channels")
        names = {c["id"]: c.get("name", "") for c in channels}

        for thread in self._threads(channels):
            doc = self._thread_document(thread, names.get(thread.get("parent_id", ""), ""))
            if doc:
                yield doc
        for channel in channels:
            if channel.get("type") in MESSAGE_CHANNELS:
                yield from self._channel_documents(channel)

    # -- helpers -----------------------------------------------------------------

    def _get(self, url: str, params: dict | None = None):
        return request(self._client, "GET", url, source=self.source, params=params, sleep=self._sleep).json()

    def _threads(self, channels: list[dict]) -> list[dict]:
        threads = {t["id"]: t for t in self._get(f"/guilds/{self.guild_id}/threads/active").get("threads", [])}
        for channel in channels:
            if channel.get("type") not in THREAD_PARENTS:
                continue
            params: dict = {"limit": 100}
            while True:
                try:
                    data = self._get(f"/channels/{channel['id']}/threads/archived/public", params)
                except ConnectorError:
                    break  # no permission on this channel
                batch = data.get("threads", [])
                threads.update({t["id"]: t for t in batch})
                if not data.get("has_more") or not batch:
                    break
                params["before"] = batch[-1]["thread_metadata"]["archive_timestamp"]
        return list(threads.values())

    def _messages(self, channel_id: str) -> list[dict]:
        """All messages of a channel / thread, oldest first."""
        messages: list[dict] = []
        params: dict = {"limit": 100}
        while True:
            batch = self._get(f"/channels/{channel_id}/messages", params)
            messages.extend(batch)
            if len(batch) < 100:
                break
            params["before"] = batch[-1]["id"]
        messages.reverse()
        return messages

    def _thread_document(self, thread: dict, parent_name: str) -> NormalizedDocument | None:
        messages = [m for m in self._messages(thread["id"]) if _content(m)]
        if not messages:
            return None
        title = f"#{parent_name} › {thread.get('name', '')}" if parent_name else thread.get("name", "")
        lines = [(_author(m), m["timestamp"], _content(m)) for m in messages]
        return NormalizedDocument(
            source="discord",
            external_id=f"thread:{thread['id']}",
            url=f"https://discord.com/channels/{self.guild_id}/{thread['id']}",
            title=title,
            author=lines[0][0],
            created_at=parse_datetime(messages[0]["timestamp"]),
            text=f"{title}\n\n{format_messages(lines)}",
            raw={"thread_id": thread["id"], "parent_id": thread.get("parent_id")},
        )

    def _channel_documents(self, channel: dict) -> Iterator[NormalizedDocument]:
        messages = [m for m in self._messages(channel["id"]) if _content(m)]
        window: list[dict] = []
        window_start: datetime | None = None
        for message in messages:
            ts = parse_datetime(message["timestamp"])
            if window and window_start and ts - window_start > self.window:
                yield self._window_document(channel, window)
                window = []
            if not window:
                window_start = ts
            window.append(message)
        if window:
            yield self._window_document(channel, window)

    def _window_document(self, channel: dict, messages: list[dict]) -> NormalizedDocument:
        first = messages[0]
        title = f"#{channel.get('name', '')} {first['timestamp'][:10]}"
        lines = [(_author(m), m["timestamp"], _content(m)) for m in messages]
        return NormalizedDocument(
            source="discord",
            external_id=f"channel:{channel['id']}:{first['id']}",
            url=f"https://discord.com/channels/{self.guild_id}/{channel['id']}/{first['id']}",
            title=title,
            author=lines[0][0],
            created_at=parse_datetime(first["timestamp"]),
            text=f"{title}\n\n{format_messages(lines)}",
            raw={"channel_id": channel["id"], "message_ids": [m["id"] for m in messages]},
        )
