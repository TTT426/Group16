"""Notion connector: every page shared with the integration, converted to markdown-like text."""

import time
from collections.abc import Callable, Iterator

import httpx

from .base import ConnectorError, NormalizedDocument, parse_datetime
from .http import request

API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

_PREFIX = {
    "heading_1": "# ",
    "heading_2": "## ",
    "heading_3": "### ",
    "bulleted_list_item": "- ",
    "numbered_list_item": "1. ",
    "quote": "> ",
    "callout": "> ",
}
# Child pages / databases are separate documents (the search API returns them on their own).
_NO_RECURSE = {"child_page", "child_database"}


def rich_text(items: list[dict]) -> str:
    return "".join(item.get("plain_text", "") for item in items or [])


def block_to_text(block: dict) -> str:
    kind = block.get("type", "")
    data = block.get(kind) or {}
    text = rich_text(data.get("rich_text", []))
    if kind in _PREFIX:
        return _PREFIX[kind] + text
    if kind == "to_do":
        return ("[x] " if data.get("checked") else "[ ] ") + text
    if kind == "code":
        return f"```{data.get('language', '')}\n{text}\n```"
    if kind == "divider":
        return "---"
    if kind == "child_page":
        return f"(Sub-page: {data.get('title', '')})"
    if kind == "child_database":
        return f"(Database: {data.get('title', '')})"
    return text


def page_title(page: dict) -> str:
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return rich_text(prop.get("title", []))
    return ""


class NotionConnector:
    source = "notion"

    def __init__(
        self,
        token: str,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_depth: int = 5,
    ) -> None:
        if not token:
            raise ConnectorError("notion: NOTION_TOKEN is not set.")
        self._client = client or httpx.Client(base_url=API_URL, timeout=30.0)
        self._client.headers.update({"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION})
        self._sleep = sleep
        self._max_depth = max_depth
        self._user_names: dict[str, str] = {}

    def fetch(self) -> Iterator[NormalizedDocument]:
        for page in self._search_pages():
            if page.get("archived") or page.get("in_trash"):
                continue
            title = page_title(page) or "Untitled"
            body = "\n".join(line for line in self._block_lines(page["id"], depth=0) if line.strip())
            yield NormalizedDocument(
                source="notion",
                external_id=page["id"],
                url=page["url"],
                title=title,
                author=self._user_name((page.get("created_by") or {}).get("id")),
                created_at=parse_datetime(page.get("created_time")),
                text=f"{title}\n\n{body}".strip(),
                raw={"last_edited_time": page.get("last_edited_time")},
            )

    def _call(self, method: str, url: str, **kwargs) -> dict:
        return request(self._client, method, url, source=self.source, sleep=self._sleep, **kwargs).json()

    def _search_pages(self) -> Iterator[dict]:
        payload: dict = {"filter": {"property": "object", "value": "page"}, "page_size": 100}
        while True:
            data = self._call("POST", "/search", json=payload)
            yield from data.get("results", [])
            if not data.get("has_more"):
                return
            payload["start_cursor"] = data["next_cursor"]

    def _children(self, block_id: str) -> Iterator[dict]:
        params: dict = {"page_size": 100}
        while True:
            data = self._call("GET", f"/blocks/{block_id}/children", params=params)
            yield from data.get("results", [])
            if not data.get("has_more"):
                return
            params["start_cursor"] = data["next_cursor"]

    def _block_lines(self, block_id: str, depth: int) -> Iterator[str]:
        for block in self._children(block_id):
            yield "  " * depth + block_to_text(block)
            if block.get("has_children") and block.get("type") not in _NO_RECURSE and depth < self._max_depth:
                yield from self._block_lines(block["id"], depth + 1)

    def _user_name(self, user_id: str | None) -> str | None:
        if not user_id:
            return None
        if user_id not in self._user_names:
            try:
                self._user_names[user_id] = self._call("GET", f"/users/{user_id}").get("name") or user_id
            except ConnectorError:
                self._user_names[user_id] = user_id  # integration may lack user-info capability
        return self._user_names[user_id]
