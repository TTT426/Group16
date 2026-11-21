"""Connector tests against mocked HTTP APIs (httpx.MockTransport) — no network, no tokens."""

import base64
import json

import httpx
import pytest

from app.connectors.base import ConnectorError
from app.connectors.discord import DiscordConnector
from app.connectors.github import GitHubConnector
from app.connectors.notion import NotionConnector, block_to_text
from app.connectors.scenario import ScenarioConnector


def mock_client(routes: dict, base_url: str, calls: list | None = None) -> httpx.Client:
    """routes: {(METHOD, path): response | callable(request) -> response}; response = (status, json[, headers])."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        key = (request.method, request.url.path)
        if key not in routes:
            return httpx.Response(404, json={"message": f"no route {key}"})
        route = routes[key]
        result = route(request) if callable(route) else route
        status, body, *headers = result
        return httpx.Response(status, json=body, headers=headers[0] if headers else None)

    return httpx.Client(transport=httpx.MockTransport(handler), base_url=base_url)


# ---------------------------------------------------------------- GitHub

def _github_routes():
    repo = "/repos/acme/shop"

    def issues(request):
        if request.url.params.get("page") == "2":
            return 200, [{
                "number": 2, "title": "Fix checkout", "body": "Fixes #1", "state": "closed",
                "html_url": "https://github.com/acme/shop/pull/2", "user": {"login": "kevin"},
                "labels": [], "comments": 0, "created_at": "2026-10-02T00:00:00Z",
                "pull_request": {"merged_at": "2026-10-03T00:00:00Z"},
            }]
        next_link = f'<https://api.github.com{repo}/issues?state=all&per_page=100&page=2>; rel="next"'
        return 200, [{
            "number": 1, "title": "Payment fails", "body": "PAYMENT_DUPLICATE on retry", "state": "open",
            "html_url": "https://github.com/acme/shop/issues/1", "user": {"login": "amy"},
            "labels": [{"name": "bug"}], "comments": 1, "created_at": "2026-10-01T00:00:00Z",
        }], {"Link": next_link}

    return {
        ("GET", f"{repo}/issues"): issues,
        ("GET", f"{repo}/issues/1/comments"): (200, [
            {"user": {"login": "lisa"}, "created_at": "2026-10-01T05:00:00Z", "body": "See Discord thread"}]),
        ("GET", f"{repo}/pulls/2/comments"): (200, [
            {"user": {"login": "lisa"}, "created_at": "2026-10-02T05:00:00Z", "body": "Keep the retry",
             "path": "checkout.py"}]),
        ("GET", repo): (200, {"default_branch": "main"}),
        ("GET", f"{repo}/git/trees/main"): (200, {"tree": [
            {"path": "README.md", "type": "blob"}, {"path": "src/app.py", "type": "blob"},
            {"path": "docs/huge.md", "type": "blob"}, {"path": "docs", "type": "tree"}]}),
        ("GET", f"{repo}/contents/README.md"): (200, {
            "content": base64.b64encode("# ShopLite\n部署說明".encode()).decode(), "encoding": "base64",
            "html_url": "https://github.com/acme/shop/blob/main/README.md"}),
        # Files over 1 MB: no content, encoding "none" -> skipped.
        ("GET", f"{repo}/contents/docs/huge.md"): (200, {"content": "", "encoding": "none"}),
    }


def test_github_fetches_issues_prs_comments_and_markdown():
    calls: list = []
    client = mock_client(_github_routes(), "https://api.github.com", calls)
    docs = list(GitHubConnector("acme/shop", "tok", client=client).fetch())

    by_id = {d.external_id: d for d in docs}
    assert set(by_id) == {"issue:1", "pr:2", "file:README.md"}
    issue, pr, readme = by_id["issue:1"], by_id["pr:2"], by_id["file:README.md"]
    assert issue.url == "https://github.com/acme/shop/issues/1"
    assert "PAYMENT_DUPLICATE" in issue.text and "See Discord thread" in issue.text and "Labels: bug" in issue.text
    assert "State: merged" in pr.text and "[review on checkout.py] Keep the retry" in pr.text
    assert "部署說明" in readme.text
    assert calls[0].headers["Authorization"] == "Bearer tok"


def test_github_retries_rate_limit_then_succeeds():
    attempts = {"n": 0}
    routes = _github_routes()
    original = routes[("GET", "/repos/acme/shop/issues")]

    def flaky(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return 429, {"message": "rate limited"}, {"Retry-After": "7"}
        return original(request)

    routes[("GET", "/repos/acme/shop/issues")] = flaky
    sleeps: list = []
    connector = GitHubConnector("acme/shop", client=mock_client(routes, "https://api.github.com"),
                                include_markdown=False, sleep=sleeps.append)
    docs = list(connector.fetch())
    assert len(docs) == 2 and sleeps == [7.0]


def test_github_bad_token_raises_connector_error():
    client = mock_client({("GET", "/repos/acme/shop/issues"): (401, {"message": "Bad credentials"})},
                         "https://api.github.com")
    with pytest.raises(ConnectorError, match="access denied"):
        list(GitHubConnector("acme/shop", "bad", client=client).fetch())


def test_github_repo_format_validated():
    with pytest.raises(ValueError):
        GitHubConnector("not-a-repo")


# ---------------------------------------------------------------- Notion

def _rt(text):
    return [{"plain_text": text}]


def _notion_routes():
    def search(request):
        body = json.loads(request.content)
        if body.get("start_cursor") == "c2":
            return 200, {"results": [{"id": "archived", "archived": True}], "has_more": False}
        return 200, {"results": [{
            "id": "11111111-2222-3333-4444-555555555555",
            "url": "https://www.notion.so/Spec-11111111222233334444555555555555",
            "created_time": "2026-09-01T00:00:00.000Z", "created_by": {"id": "u1"},
            "properties": {"Name": {"type": "title", "title": _rt("金流整合規格")}},
        }], "has_more": True, "next_cursor": "c2"}

    page = "/v1/blocks/11111111-2222-3333-4444-555555555555/children"
    return {
        ("POST", "/v1/search"): search,
        ("GET", page): (200, {"results": [
            {"id": "b1", "type": "heading_2", "heading_2": {"rich_text": _rt("Idempotency 規則")},
             "has_children": False},
            {"id": "b2", "type": "bulleted_list_item",
             "bulleted_list_item": {"rich_text": _rt("Key 必須由 server 端產生")}, "has_children": True},
            {"id": "b3", "type": "child_page", "child_page": {"title": "Sub"}, "has_children": True},
        ], "has_more": False}),
        ("GET", "/v1/blocks/b2/children"): (200, {"results": [
            {"id": "b4", "type": "paragraph", "paragraph": {"rich_text": _rt("保留 24 小時")}, "has_children": False},
        ], "has_more": False}),
        ("GET", "/v1/users/u1"): (200, {"name": "Lisa"}),
    }


def test_notion_fetches_shared_pages_with_nested_blocks():
    calls: list = []
    client = mock_client(_notion_routes(), "https://api.notion.com/v1", calls)
    docs = list(NotionConnector("secret", client=client).fetch())
    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "金流整合規格" and doc.author == "Lisa"
    assert doc.external_id == "11111111-2222-3333-4444-555555555555"
    assert "## Idempotency 規則" in doc.text
    assert "- Key 必須由 server 端產生\n  保留 24 小時" in doc.text
    assert "(Sub-page: Sub)" in doc.text
    assert not any(c.url.path == "/v1/blocks/b3/children" for c in calls)  # child pages are not inlined
    assert calls[0].headers["Notion-Version"]


def test_notion_block_formatting():
    assert block_to_text({"type": "to_do", "to_do": {"rich_text": _rt("x"), "checked": True}}) == "[x] x"
    assert block_to_text({"type": "code", "code": {"rich_text": _rt("print()"), "language": "python"}}) == \
        "```python\nprint()\n```"
    assert block_to_text({"type": "unsupported"}) == ""


def test_notion_requires_token():
    with pytest.raises(ConnectorError):
        NotionConnector("")


# ---------------------------------------------------------------- Discord

def _msg(mid, author, content, ts, **extra):
    return {"id": mid, "author": {"username": author}, "content": content, "timestamp": ts, **extra}


def _discord_routes():
    def channel_messages(request):
        if request.url.params.get("before"):
            return 200, []
        # newest first, as Discord returns them
        return 200, [
            _msg("13", "amy", "週五部署 staging？", "2026-10-05T09:00:00+00:00"),
            _msg("12", "lisa", "可以", "2026-10-01T10:00:00+00:00"),
            _msg("11", "kevin", "早安", "2026-10-01T09:00:00+00:00"),
        ]

    return {
        ("GET", "/api/v10/guilds/g1/channels"): (200, [
            {"id": "c1", "name": "backend", "type": 0},
            {"id": "v1", "name": "voice", "type": 2},
        ]),
        ("GET", "/api/v10/guilds/g1/threads/active"): (200, {"threads": [
            {"id": "t1", "name": "PAYMENT_DUPLICATE 調查", "parent_id": "c1"}]}),
        ("GET", "/api/v10/channels/c1/threads/archived/public"): (200, {"threads": [
            {"id": "t2", "name": "舊討論", "parent_id": "c1",
             "thread_metadata": {"archive_timestamp": "2026-09-01T00:00:00+00:00"}}], "has_more": False}),
        ("GET", "/api/v10/channels/t1/messages"): (200, [
            _msg("103", "lisa", "見 https://github.com/acme/shop/pull/2", "2026-10-01T12:02:00+00:00"),
            _msg("102", "kevin", "找到原因了：idempotency key 每次都不同", "2026-10-01T12:01:00+00:00"),
            _msg("101", "tom", "", "2026-10-01T12:00:00+00:00", type=21,
                 referenced_message={"content": "v1.4 加了 axios-retry"}),
        ]),
        ("GET", "/api/v10/channels/t2/messages"): (200, []),
        ("GET", "/api/v10/channels/c1/messages"): channel_messages,
    }


def test_discord_threads_and_channel_windows():
    calls: list = []
    client = mock_client(_discord_routes(), "https://discord.com/api/v10", calls)
    docs = list(DiscordConnector("bot-token", "g1", client=client).fetch())
    by_id = {d.external_id: d for d in docs}

    thread = by_id["thread:t1"]
    assert thread.url == "https://discord.com/channels/g1/t1"
    assert thread.title == "#backend › PAYMENT_DUPLICATE 調查"
    lines = thread.text.splitlines()[2:]
    assert lines[0].startswith("tom") and "axios-retry" in lines[0]  # thread starter resolved, oldest first
    assert "pull/2" in lines[-1]
    assert "thread:t2" not in by_id  # empty archived thread skipped

    # Channel messages: 10-01 09:00 & 10:00 in one window, 10-05 in another.
    windows = sorted(k for k in by_id if k.startswith("channel:"))
    assert windows == ["channel:c1:11", "channel:c1:13"]
    assert "早安" in by_id["channel:c1:11"].text and "可以" in by_id["channel:c1:11"].text
    assert by_id["channel:c1:11"].url == "https://discord.com/channels/g1/c1/11"
    assert calls[0].headers["Authorization"] == "Bot bot-token"


def test_discord_requires_credentials():
    with pytest.raises(ConnectorError):
        DiscordConnector("", "g1")


# ---------------------------------------------------------------- Scenario

def test_scenario_connector_resolves_cross_links(scenario_paths):
    connector = ScenarioConnector(scenario_paths)
    docs = list(connector.fetch())
    urls = {d.url for d in docs}
    assert {d.source for d in docs} == {"github", "notion", "discord"}
    assert len({(d.source, d.external_id) for d in docs}) == len(docs)  # ids unique across scenarios
    for doc in docs:
        assert "{{" not in doc.text
    # Every resolved placeholder points at a document that exists.
    assert set(connector.urls.values()) <= urls
    pr = next(d for d in docs if d.source == "github" and "idempotency key" in d.title)
    assert connector.urls["discord.thread.payment-fail"] in pr.text
