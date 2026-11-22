"""Notion connection check for the /connect pages.

Notion has no sign-in a local app can use without a server-side secret, so a workspace owner creates an internal
connection (Developer portal, authentication method "API token"), the user pastes its API token, and pages are shared
with it. The check confirms the token and lists the pages the connection can see, so the page can tell the user what
is still missing.
"""

import httpx

from .connectors.notion import API_URL, NOTION_VERSION, page_title

PAGE_PREVIEW = 20  # pages listed on the connect page

# User-facing messages (shown as-is in the /connect pages, so they are in the UI language).
MSG_NETWORK = "連不到 Notion，請檢查網路連線。"
MSG_BAD_TOKEN = "Notion 的 API token 無效。請到 connection 的 Configuration 分頁重新複製 API token。"
MSG_BAD_STATUS = "Notion 回應錯誤（{status}）。"
MSG_EMPTY_TOKEN = "請貼上 connection 的 API token。"


class NotionError(Exception):
    """An error whose message can be shown to the user as-is."""


def check(token: str, client: httpx.Client | None = None) -> dict:
    """The connection's name and workspace, and which pages it can read (first PAGE_PREVIEW)."""
    if not token:
        raise NotionError(MSG_EMPTY_TOKEN)
    headers = {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}
    own_client = client is None
    http = client or httpx.Client(timeout=20.0)
    try:
        me = http.get(f"{API_URL}/users/me", headers=headers)
        if me.status_code == 401:
            raise NotionError(MSG_BAD_TOKEN)
        if me.status_code != 200:
            raise NotionError(MSG_BAD_STATUS.format(status=me.status_code))
        search = http.post(f"{API_URL}/search", headers=headers, json={
            "filter": {"property": "object", "value": "page"}, "page_size": PAGE_PREVIEW,
        })
        if search.status_code != 200:
            raise NotionError(MSG_BAD_STATUS.format(status=search.status_code))
    except httpx.HTTPError as exc:
        raise NotionError(MSG_NETWORK) from exc
    finally:
        if own_client:
            http.close()
    bot, data = me.json(), search.json()
    pages = [{"title": page_title(p) or "Untitled", "url": p.get("url", "")}
             for p in data.get("results", []) if not (p.get("archived") or p.get("in_trash"))]
    return {
        "connection": bot.get("name") or "",
        "workspace": (bot.get("bot") or {}).get("workspace_name") or "",
        "pages": pages,
        "more_pages": bool(data.get("has_more")),
    }
