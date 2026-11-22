"""GitHub sign-in and repo selection for the /connect pages.

Ways to sign in, in the order the page offers them:
  1. "Sign in with GitHub" (OAuth device flow): the user types a short code on github.com.
     Needs only the public client id of an OAuth App (GITHUB_CLIENT_ID), no secret, so it works locally.
  2. The GitHub CLI login already on this computer (`gh auth login`), if the user chooses it.
  3. A personal access token pasted by the user.
Public repos can also be imported without signing in.
"""

import re
import shutil
import subprocess
from dataclasses import dataclass

import httpx

from .config import Settings

API = "https://api.github.com"
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
SCOPE = "repo"  # needed to read private repos (GitHub has no read-only scope for OAuth Apps)
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
PLACEHOLDER_REPO = "owner/repo"  # the value in .env.example, i.e. "not chosen yet"

# User-facing messages (shown as-is in the /connect pages, so they are in the UI language).
MSG_NETWORK = "連不到 GitHub，請檢查網路連線。"
MSG_LOGIN_EXPIRED = "登入已失效或 token 無效，請重新登入。"
MSG_BAD_STATUS = "GitHub 回應錯誤（{status}）。"
MSG_REPO_LIST = "讀不到你的 repo 列表（{status}），請重新登入。"
MSG_REPO_NO_ACCESS = "找不到 {repo}，或你的帳號沒有權限讀取它。"
MSG_REPO_NEEDS_LOGIN = "找不到 {repo}。如果它是私人 repo，請先登入。"
MSG_DEVICE_START = "無法開始 GitHub 登入（{reason}）。"
MSG_DEVICE_FAILED = "GitHub 登入失敗（{reason}）。"
MSG_NO_CLIENT_ID = "「使用 GitHub 登入」尚未設定（缺少 GITHUB_CLIENT_ID），請改用其他登入方式。"
MSG_GH_CLI_LOGGED_OUT = "這台電腦的 GitHub CLI 沒有登入。請在終端機執行 gh auth login，或改用其他方式。"
MSG_BAD_REPO_INPUT = "請輸入 owner/repo，或貼上 GitHub 上 repo 的網址。"


class GitHubError(Exception):
    """An error whose message can be shown to the user as-is."""


def _request(method: str, url: str, client: httpx.Client | None, **kwargs) -> httpx.Response:
    """One request; a client passed in is reused and left open (the caller owns it)."""
    try:
        if client is not None:
            return client.request(method, url, **kwargs)
        with httpx.Client(timeout=20.0) as http:
            return http.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise GitHubError(MSG_NETWORK) from exc


def _api_get(path: str, token: str, client: httpx.Client | None = None, **params) -> httpx.Response:
    headers = {**HEADERS, **({"Authorization": f"Bearer {token}"} if token else {})}
    return _request("GET", f"{API}{path}", client, headers=headers, params=params or None)


# ------------------------------------------------------------------------------------------- settings


def configured_repo(settings: Settings) -> str:
    """The repo chosen to read from, or '' if none has been chosen yet."""
    repo = settings.github_repo.strip()
    return "" if repo == PLACEHOLDER_REPO else repo


def gh_cli_token() -> str:
    """Token of the logged-in GitHub CLI, or '' if gh is missing / logged out."""
    gh = shutil.which("gh")
    if not gh:
        return ""
    try:
        out = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def current_token(settings: Settings) -> tuple[str, str]:
    """(token, how): 'token' = saved token, 'gh' = GitHub CLI login (only if the user chose it), 'none'."""
    if settings.github_token:
        return settings.github_token, "token"
    if settings.github_use_gh_cli:
        token = gh_cli_token()
        if token:
            return token, "gh"
    return "", "none"


# ------------------------------------------------------------------------------------------- account and repos


def get_user(token: str, client: httpx.Client | None = None) -> dict:
    r = _api_get("/user", token, client)
    if r.status_code == 401:
        raise GitHubError(MSG_LOGIN_EXPIRED)
    if r.status_code != 200:
        raise GitHubError(MSG_BAD_STATUS.format(status=r.status_code))
    u = r.json()
    return {"login": u["login"], "name": u.get("name") or u["login"], "avatar_url": u.get("avatar_url", "")}


def list_repos(token: str, client: httpx.Client | None = None, max_pages: int = 3) -> list[dict]:
    """Repos the signed-in user can read (own, collaborator, organisations), most recently updated first."""
    repos: list[dict] = []
    for page in range(1, max_pages + 1):
        r = _api_get("/user/repos", token, client, per_page=100, page=page, sort="updated",
                     affiliation="owner,collaborator,organization_member")
        if r.status_code != 200:
            raise GitHubError(MSG_REPO_LIST.format(status=r.status_code))
        batch = r.json()
        repos += [{
            "full_name": x["full_name"], "private": x.get("private", False),
            "description": x.get("description") or "", "updated_at": x.get("pushed_at") or x.get("updated_at"),
        } for x in batch]
        if len(batch) < 100:
            break
    return repos


def parse_repo(text: str) -> str:
    """'owner/repo', 'https://github.com/owner/repo(.git)', 'git@github.com:owner/repo.git' -> 'owner/repo'."""
    text = text.strip()
    m = re.search(r"github\.com[:/]+([\w.-]+)/([\w.-]+?)(?:\.git)?/?(?:[?#].*)?$", text) or \
        re.fullmatch(r"([\w.-]+)/([\w.-]+?)(?:\.git)?", text)
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def check_repo(repo: str, token: str, client: httpx.Client | None = None) -> dict:
    """Confirm the repo is readable with this token (or anonymously); returns its canonical name."""
    r = _api_get(f"/repos/{repo}", token, client)
    if r.status_code == 401:
        raise GitHubError(MSG_LOGIN_EXPIRED)
    if r.status_code in (403, 404):
        raise GitHubError((MSG_REPO_NO_ACCESS if token else MSG_REPO_NEEDS_LOGIN).format(repo=repo))
    if r.status_code != 200:
        raise GitHubError(MSG_BAD_STATUS.format(status=r.status_code))
    x = r.json()
    return {"full_name": x["full_name"], "private": x.get("private", False), "url": x.get("html_url", "")}


# ------------------------------------------------------------------------------------------- device flow


@dataclass
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


def start_device_flow(client_id: str, client: httpx.Client | None = None) -> DeviceCode:
    r = _request("POST", DEVICE_CODE_URL, client, headers={"Accept": "application/json"},
                 data={"client_id": client_id, "scope": SCOPE})
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200 or "device_code" not in data:
        raise GitHubError(MSG_DEVICE_START.format(reason=data.get("error_description") or r.status_code))
    return DeviceCode(data["device_code"], data["user_code"], data["verification_uri"],
                      int(data.get("expires_in", 900)), int(data.get("interval", 5)))


def poll_device_flow(client_id: str, device_code: str, client: httpx.Client | None = None) -> tuple[str, str]:
    """('ok', token) | ('pending', '') | ('slow_down', '') | ('expired', '') | ('denied', '')."""
    try:
        r = _request("POST", ACCESS_TOKEN_URL, client, headers={"Accept": "application/json"}, data={
            "client_id": client_id, "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })
    except GitHubError:
        return "pending", ""  # network hiccup: try again on the next poll
    data = r.json() if r.status_code == 200 else {}
    if data.get("access_token"):
        return "ok", data["access_token"]
    status = {"authorization_pending": "pending", "slow_down": "slow_down",
              "expired_token": "expired", "access_denied": "denied"}.get(data.get("error", ""))
    if status:
        return status, ""
    raise GitHubError(MSG_DEVICE_FAILED.format(reason=data.get("error_description") or data.get("error")
                                               or r.status_code))
