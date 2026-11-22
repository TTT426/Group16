"""Notion connection check (mocked HTTP)."""

import httpx
import pytest

from app import notion_account as notion


def mock_client(routes: dict[tuple[str, str], tuple[int, object]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = routes.get((request.method, request.url.path), (404, {}))
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def page(title: str, **extra) -> dict:
    return {"url": f"https://www.notion.so/{title}", "properties": {"Name": {"type": "title", "title": [
        {"plain_text": title}]}}, **extra}


# ---------------------------------------------------------------- check


def test_check_lists_visible_pages_and_skips_trashed_ones():
    result = notion.check("ntn_x", mock_client({
        ("GET", "/v1/users/me"): (200, {"name": "Group16", "bot": {"workspace_name": "Team"}}),
        ("POST", "/v1/search"): (200, {"results": [page("Spec"), page("Old", in_trash=True)], "has_more": True}),
    }))
    assert result == {"connection": "Group16", "workspace": "Team",
                      "pages": [{"title": "Spec", "url": "https://www.notion.so/Spec"}], "more_pages": True}


def test_check_errors():
    with pytest.raises(notion.NotionError) as empty:
        notion.check("")
    assert str(empty.value) == notion.MSG_EMPTY_TOKEN
    with pytest.raises(notion.NotionError) as bad:
        notion.check("bad", mock_client({("GET", "/v1/users/me"): (401, {})}))
    assert str(bad.value) == notion.MSG_BAD_TOKEN
