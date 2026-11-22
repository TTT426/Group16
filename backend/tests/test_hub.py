"""/connect pages: .env editing, GitHub sign-in and repo choice (mocked HTTP), and the local-only guard."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app import github_account as gh
from app.api import hub
from app.config import Settings
from app.envfile import update_env
from app.main import app


def mock_client(routes: dict[tuple[str, str], tuple[int, object]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = routes.get((request.method, request.url.path), (404, {"message": "not found"}))
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------- .env editing


def test_update_env_keeps_comments_order_and_crlf(tmp_path):
    env = tmp_path / ".env"
    env.write_bytes(b"# comment\r\nGITHUB_TOKEN=\r\nGITHUB_REPO=owner/repo\r\nOTHER=1\r\n")
    update_env({"GITHUB_REPO": "a/b", "NOTION_TOKEN": "ntn_x"}, env)
    assert env.read_bytes() == b"# comment\r\nGITHUB_TOKEN=\r\nGITHUB_REPO=a/b\r\nOTHER=1\r\nNOTION_TOKEN=ntn_x\r\n"


def test_update_env_quotes_and_rejects_newlines(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\n")
    update_env({"A": 'has space "q"'}, env)
    assert env.read_text() == 'A="has space \\"q\\""\n'
    with pytest.raises(ValueError):
        update_env({"A": "x\ny"}, env)


# ---------------------------------------------------------------- GitHub account


@pytest.mark.parametrize("text, repo", [
    ("acme/shop", "acme/shop"),
    ("git@github.com:acme/shop.git", "acme/shop"),
    ("https://github.com/acme/shop", "acme/shop"),
    ("https://github.com/acme/shop.git/", "acme/shop"),
    ("https://github.com/acme/shop/issues?q=1", ""),
    ("https://gitlab.com/a/b", ""),
    ("not a repo", ""),
])
def test_parse_repo(text, repo):
    assert gh.parse_repo(text) == repo


def test_current_token_uses_gh_cli_only_when_chosen(monkeypatch):
    monkeypatch.setattr(gh, "gh_cli_token", lambda: "gho_cli")
    assert gh.current_token(Settings(_env_file=None)) == ("", "none")  # never picked up silently
    assert gh.current_token(Settings(_env_file=None, github_use_gh_cli=True)) == ("gho_cli", "gh")
    both = Settings(_env_file=None, github_token="ghp_x", github_use_gh_cli=True)
    assert gh.current_token(both) == ("ghp_x", "token")


def test_check_repo_messages():
    ok = gh.check_repo("a/b", "", mock_client({("GET", "/repos/a/b"): (200, {"full_name": "a/b", "html_url": "u"})}))
    assert ok["full_name"] == "a/b"
    with pytest.raises(gh.GitHubError) as anonymous:
        gh.check_repo("a/b", "", mock_client({}))
    assert str(anonymous.value) == gh.MSG_REPO_NEEDS_LOGIN.format(repo="a/b")  # private repo: suggest signing in
    with pytest.raises(gh.GitHubError) as signed_in:
        gh.check_repo("a/b", "tok", mock_client({}))
    assert str(signed_in.value) == gh.MSG_REPO_NO_ACCESS.format(repo="a/b")


def test_list_repos_paginates():
    seen: list = []
    page = [{"full_name": f"o/r{i}", "private": i == 0, "description": None, "pushed_at": "2026-11-01"}
            for i in range(100)]

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=page if request.url.params["page"] == "1" else page[:3])

    repos = gh.list_repos("tok", httpx.Client(transport=httpx.MockTransport(handler)))
    assert len(repos) == 103 and repos[0] == {"full_name": "o/r0", "private": True, "description": "",
                                              "updated_at": "2026-11-01"}
    assert seen[0].headers["Authorization"] == "Bearer tok"


def test_device_flow():
    code = gh.start_device_flow("cid", mock_client({("POST", "/login/device/code"): (200, {
        "device_code": "dc", "user_code": "ABCD-1234", "verification_uri": "https://github.com/login/device",
        "expires_in": 900, "interval": 5})}))
    assert code.user_code == "ABCD-1234"

    def poll(body):
        return gh.poll_device_flow("cid", "dc", mock_client({("POST", "/login/oauth/access_token"): (200, body)}))

    assert poll({"error": "authorization_pending"}) == ("pending", "")
    assert poll({"error": "slow_down", "interval": 10}) == ("slow_down", "")
    assert poll({"error": "expired_token"}) == ("expired", "")
    assert poll({"error": "access_denied"}) == ("denied", "")
    assert poll({"access_token": "gho_new", "token_type": "bearer"}) == ("ok", "gho_new")
    with pytest.raises(gh.GitHubError):
        poll({"error": "device_flow_disabled", "error_description": "Device Flow must be enabled"})


# ---------------------------------------------------------------- hub routes


@pytest.fixture
def saved(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(hub, "update_env", calls.append)
    return calls


def test_pages_and_local_only_guard():
    client = TestClient(app)
    assert 'id="gh-chip"' in client.get("/connect").text
    assert 'id="step-login"' in client.get("/connect/github").text
    assert client.get("/connect", headers={"host": "evil.example"}).status_code == 403
    cross = client.post("/api/github/logout", headers={"origin": "https://evil.example"})
    assert cross.status_code == 403


def test_token_login_saves_valid_token_and_never_echoes_it(monkeypatch, saved):
    def fake_user(token, client=None):
        if token != "good":
            raise gh.GitHubError("bad")
        return {"login": "me", "name": "Me", "avatar_url": ""}

    monkeypatch.setattr(gh, "get_user", fake_user)
    client = TestClient(app)
    assert client.post("/api/github/login/token", json={"token": "bad"}).status_code == 400
    assert saved == []
    response = client.post("/api/github/login/token", json={"token": " good "})
    assert response.json()["account"]["login"] == "me" and "good" not in response.text
    assert saved == [{"GITHUB_TOKEN": "good", "GITHUB_USE_GH_CLI": "false"}]


def test_device_login_poll_saves_token(monkeypatch, saved):
    monkeypatch.setattr(hub, "get_settings", lambda: Settings(_env_file=None, github_client_id="cid"))
    monkeypatch.setattr(gh, "start_device_flow", lambda cid: gh.DeviceCode("dc", "ABCD-1234", "https://x", 900, 5))
    results = iter([("pending", ""), ("ok", "gho_new")])
    monkeypatch.setattr(gh, "poll_device_flow", lambda cid, dc: next(results))
    monkeypatch.setattr(hub, "_account", lambda: {"login": "me"})
    client = TestClient(app)
    flow = client.post("/api/github/login/start").json()
    assert flow["user_code"] == "ABCD-1234" and "dc" not in flow.values()  # device code stays on the server
    assert client.post("/api/github/login/poll", json={"flow_id": flow["flow_id"]}).json() == {"status": "pending"}
    assert client.post("/api/github/login/poll", json={"flow_id": flow["flow_id"]}).json()["status"] == "ok"
    assert saved == [{"GITHUB_TOKEN": "gho_new", "GITHUB_USE_GH_CLI": "false"}]
    assert client.post("/api/github/login/poll", json={"flow_id": flow["flow_id"]}).json() == {"status": "expired"}


def test_device_login_needs_client_id(monkeypatch):
    monkeypatch.setattr(hub, "get_settings", lambda: Settings(_env_file=None))
    assert TestClient(app).post("/api/github/login/start").status_code == 400


def test_choose_repo_validates_and_saves_canonical_name(monkeypatch, saved):
    monkeypatch.setattr(hub, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(gh, "check_repo", lambda repo, token: {"full_name": "Acme/Shop", "private": False, "url": ""})
    client = TestClient(app)
    assert client.post("/api/github/repo", json={"repo": "nonsense"}).status_code == 422
    assert client.post("/api/github/repo", json={"repo": "https://github.com/acme/shop"}).status_code == 200
    assert saved == [{"GITHUB_REPO": "Acme/Shop"}]
