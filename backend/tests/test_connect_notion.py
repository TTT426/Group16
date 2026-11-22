"""/connect/notion: the connection check (mocked HTTP) and the routes."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app import notion_account as notion
from app.api import connect_notion
from app.config import Settings
from app.connectors.base import NormalizedDocument
from app.connectors.scenario import NOTION_URL as SCENARIO_NOTION_URL
from app.embeddings.hashing import HashingEmbedder
from app.ingest.pipeline import ingest_documents
from app.main import app


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


# ---------------------------------------------------------------- routes


@pytest.fixture
def saved(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(connect_notion, "update_env", calls.append)
    return calls


def test_save_token_keeps_only_valid_tokens_and_never_echoes_them(monkeypatch, saved):
    def fake_check(token, client=None):
        if token != "ntn_good":
            raise notion.NotionError(notion.MSG_BAD_TOKEN)
        return {"connection": "Group16", "workspace": "", "pages": [], "more_pages": False}

    monkeypatch.setattr(notion, "check", fake_check)
    client = TestClient(app)
    assert client.post("/api/notion/token", json={"token": "bad"}).status_code == 400
    assert saved == []
    response = client.post("/api/notion/token", json={"token": " ntn_good "})  # valid even with no pages shared yet
    assert response.status_code == 200 and "ntn_good" not in response.text
    assert saved == [{"NOTION_TOKEN": "ntn_good"}]


def test_status_counts_imported_pages_but_not_the_practice_scenario(monkeypatch, db_session):
    monkeypatch.setattr(connect_notion, "get_settings", lambda: Settings(_env_file=None, notion_token="ntn_x"))
    monkeypatch.setattr(notion, "check", lambda token: {"connection": "G", "workspace": "", "pages": [],
                                                        "more_pages": False})
    ingest_documents(db_session, [
        NormalizedDocument(source="notion", external_id="real", url="https://www.notion.so/Spec-1", title="Spec",
                           text="規格內容"),
        NormalizedDocument(source="notion", external_id="practice", url=f"{SCENARIO_NOTION_URL}/spec-2",
                           title="Practice", text="示範內容"),
    ], HashingEmbedder())
    result = connect_notion._status(db_session)
    assert result["connected"] and result["documents"] == 1


def test_status_when_not_connected(monkeypatch, db_session):
    monkeypatch.setattr(connect_notion, "get_settings", lambda: Settings(_env_file=None))
    assert connect_notion._status(db_session) == {"connected": False, "check": None, "error": None, "documents": 0}
