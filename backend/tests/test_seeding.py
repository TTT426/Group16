"""Seeding the scenarios to GitHub / Notion / Discord, against mocked APIs (no network, no tokens)."""

import base64
import json
from pathlib import Path

import httpx
import pytest
import yaml

from app import github_account
from app.config import Settings
from app.connectors.base import ConnectorError
from app.seeding import (
    DiscordSeeder,
    GitHubSeeder,
    NotionSeeder,
    SeedState,
    github_seed_target,
    markdown_to_blocks,
    seed,
)

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "scripts" / "seed_workspace"
SCENARIOS = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(SCENARIO_DIR.glob("scenario_*.yaml"))]


class FakeAPIs:
    """Minimal stateful fakes of the three APIs; records every request."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []
        self.next_number = 0
        self.next_id = 1000

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        path, method = request.url.path, request.method
        self.calls.append((method, str(request.url), body))
        host = request.url.host
        if host == "api.github.com":
            if method == "GET" and path == "/repos/acme/demo":
                return httpx.Response(200, json={"default_branch": "main"})
            if method == "GET" and path.endswith("/git/ref/heads/main"):
                return httpx.Response(200, json={"object": {"sha": "abc"}})
            if method == "GET" and "/contents/" in path:
                return httpx.Response(404, json={"message": "Not Found"})
            if method == "POST" and path.endswith("/issues") or method == "POST" and path.endswith("/pulls"):
                self.next_number += 1
                kind = "pull" if path.endswith("/pulls") else "issues"
                return httpx.Response(201, json={"number": self.next_number,
                                                 "html_url": f"https://github.com/acme/demo/{kind}/{self.next_number}"})
            return httpx.Response(200, json={"sha": "x", "merged": True})
        if host == "api.notion.com":
            if method == "POST" and path == "/v1/pages":
                self.next_id += 1
                return httpx.Response(200, json={"id": f"page-{self.next_id}",
                                                 "url": f"https://www.notion.so/page-{self.next_id}"})
            return httpx.Response(200, json={"results": []})
        if host == "discord.com":
            if method == "GET" and path.endswith("/channels"):
                return httpx.Response(200, json=[{"id": "c-general", "name": "general", "type": 0}])
            self.next_id += 1
            if path.endswith("/webhooks"):
                return httpx.Response(200, json={"id": f"wh{self.next_id}", "token": "tok"})
            return httpx.Response(200, json={"id": f"id{self.next_id}"})
        return httpx.Response(404)


@pytest.fixture
def apis():
    return FakeAPIs()


def seeders(apis, merge=True):
    transport = httpx.MockTransport(apis.handler)
    no_sleep = lambda s: None  # noqa: E731
    return [
        GitHubSeeder("acme/demo", "t", merge=merge, sleep=no_sleep,
                     client=httpx.Client(transport=transport, base_url="https://api.github.com")),
        NotionSeeder("t", "parent", client=httpx.Client(transport=transport, base_url="https://api.notion.com/v1"),
                     sleep=no_sleep),
        DiscordSeeder("t", "g1", client=httpx.Client(transport=transport, base_url="https://discord.com/api/v10"),
                      sleep=no_sleep),
    ]


def test_seed_creates_everything_with_resolved_links(apis, tmp_path):
    state = SeedState(tmp_path / "state.json")
    result = seed(SCENARIOS, seeders(apis), state)
    expected_items = sum(
        len(s["github"].get("issues", [])) + len(s["github"].get("pulls", [])) + len(s["notion"]["pages"])
        + sum(len(c["threads"]) for c in s["discord"]["channels"]) for s in SCENARIOS)
    assert result["items"] == expected_items

    # No content was written before every container existed (phase 1 before phase 2).
    first_fill = next(i for i, c in enumerate(apis.calls) if c[0] == "PATCH" or "/webhooks/" in c[1])
    created = ("/issues", "/pulls", "/pages", "/threads")
    creates = [i for i, c in enumerate(apis.calls) if c[0] == "POST" and c[1].endswith(created)]
    assert max(creates) < first_fill

    texts = [json.dumps(c[2], ensure_ascii=False) for c in apis.calls]
    assert not any("{{" in t for t in texts)  # every placeholder replaced
    pr_body = next(c[2]["body"] for c in apis.calls if c[0] == "PATCH" and "/pulls/" in c[1])
    assert "https://discord.com/channels/g1/" in pr_body and "https://www.notion.so/page-" in pr_body
    assert pr_body.startswith("> 原作者：")

    threads = [c for c in apis.calls if c[1].endswith("/threads")]
    assert all(c[2]["type"] == 11 for c in threads)  # public threads
    assert any(c[1].endswith("/guilds/g1/channels") and c[0] == "POST" for c in apis.calls)  # #backend created
    hooks = [c for c in apis.calls if "/webhooks/" in c[1]]
    assert hooks and all("thread_id=" in c[1] and "wait=true" in c[1] and c[2]["username"] for c in hooks)
    assert any(c[0] == "PUT" and c[1].endswith("/merge") for c in apis.calls)
    readme = next(c for c in apis.calls if c[0] == "PUT" and c[1].endswith("/contents/docs/DEPLOY.md"))
    assert "部署流程" in base64.b64decode(readme[2]["content"]).decode()


def test_seed_is_resumable_without_duplicates(apis, tmp_path):
    state_path = tmp_path / "state.json"
    seed(SCENARIOS, seeders(apis), SeedState(state_path))
    count = len(apis.calls)
    seed(SCENARIOS, seeders(apis), SeedState(state_path))
    new_calls = apis.calls[count:]
    assert not any(c[0] in ("POST", "PATCH", "PUT") for c in new_calls)


def test_no_merge_leaves_prs_open(apis, tmp_path):
    seed(SCENARIOS, seeders(apis, merge=False), SeedState(tmp_path / "s.json"))
    assert not any(c[1].endswith("/merge") for c in apis.calls)


def test_unresolved_links_are_marked(tmp_path):
    state = SeedState(tmp_path / "s.json")
    assert state.resolve("see {{notion.page.x}}") == "see （尚未建立：notion.page.x）"


def test_markdown_to_blocks():
    blocks = markdown_to_blocks("# 標題\n## 規則\n- **Key** 固定\n1. 第一步\n一般段落", skip_title="標題")
    assert [b["type"] for b in blocks] == ["heading_2", "bulleted_list_item", "numbered_list_item", "paragraph"]
    assert blocks[1]["bulleted_list_item"]["rich_text"][0]["text"]["content"] == "Key 固定"


def test_missing_credentials_rejected():
    with pytest.raises(ConnectorError):
        GitHubSeeder("not-a-repo", "t")
    with pytest.raises(ConnectorError):
        NotionSeeder("t", "")
    with pytest.raises(ConnectorError):
        DiscordSeeder("", "g")


def test_seed_target_is_separate_from_the_repo_the_app_reads(monkeypatch):
    monkeypatch.setattr(github_account, "gh_cli_token", lambda: "gho_cli")

    def target(**kw):
        return github_seed_target(Settings(_env_file=None, **kw))

    with pytest.raises(ConnectorError, match="SEED_GITHUB_REPO"):
        target(github_repo="team/real", github_token="tok")  # GITHUB_REPO alone is never a seed target
    with pytest.raises(ConnectorError, match="same as GITHUB_REPO"):
        target(github_repo="Team/Real", seed_github_repo="team/real", github_token="tok")
    with pytest.raises(ConnectorError, match="no GitHub login"):
        target(seed_github_repo="me/seed-test")
    both = target(github_repo="team/real", seed_github_repo="me/seed-test", github_token="tok")
    assert both == ("me/seed-test", "tok")
    assert target(seed_github_repo="me/seed-test", github_use_gh_cli=True) == ("me/seed-test", "gho_cli")
