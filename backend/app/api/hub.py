"""/connect: the connect pages, the shared local-only guard, and GitHub sign-in / repo choice / import.

Choices are saved to `.env` (still the single source of configuration) and take effect immediately.
These routes handle tokens, so they only answer requests addressed to this machine (127.0.0.1 /
localhost) and refuse cross-site requests. Tokens are never sent back to the browser.
"""

import secrets
import time
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import github_account as gh
from ..config import get_settings
from ..connectors.base import ConnectorError
from ..connectors.factory import build_connector
from ..db.models import Document
from ..db.session import get_session
from ..embeddings.base import Embedder
from ..envfile import update_env
from ..ingest.pipeline import ingest_documents
from .deps import embedder_dep

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}  # testserver = FastAPI TestClient


def local_only(request: Request) -> None:
    # Host check blocks DNS rebinding; Origin check blocks other websites posting to localhost.
    if request.url.hostname not in LOCAL_HOSTS:
        raise HTTPException(403, "This page is only available on this computer (127.0.0.1).")
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "Cross-site request refused.")


router = APIRouter(dependencies=[Depends(local_only)], tags=["connect"])
SessionDep = Annotated[Session, Depends(get_session)]


def page(name: str) -> FileResponse:
    return FileResponse(WEB_DIR / name, headers={"Cache-Control": "no-cache"})


def _login(token: str = "", use_gh_cli: bool = False) -> dict[str, str]:
    """The .env values for a GitHub login (both empty / false = signed out)."""
    return {"GITHUB_TOKEN": token, "GITHUB_USE_GH_CLI": "true" if use_gh_cli else "false"}


def _account() -> dict | None:
    """The signed-in GitHub user, {'error': ...} if the saved login no longer works, or None."""
    token, how = gh.current_token(get_settings())
    if not token:
        return None
    try:
        return {**gh.get_user(token), "via": how}
    except gh.GitHubError as exc:
        return {"error": str(exc), "via": how}


@router.get("/connect", include_in_schema=False)
def connect_page() -> FileResponse:
    return page("connect.html")


@router.get("/connect/github", include_in_schema=False)
def github_page() -> FileResponse:
    return page("connect-github.html")


@router.get("/api/connections")
def connections(session: SessionDep) -> dict:
    repo = gh.configured_repo(get_settings())
    documents = 0
    if repo:
        documents = session.scalar(select(func.count()).select_from(Document).where(
            Document.source == "github", Document.external_id.startswith(f"{repo.lower()}#"))) or 0
    return {"github": {"account": _account(), "repo": repo, "documents": documents}}


# ------------------------------------------------------------------------------------------------ sign in


@router.get("/api/github/login-options")
def login_options() -> dict:
    cli_user = None
    token = gh.gh_cli_token()
    if token:
        try:
            cli_user = gh.get_user(token)["login"]
        except gh.GitHubError:
            pass
    return {"device_flow": bool(get_settings().github_client_id), "gh_cli_user": cli_user, "account": _account()}


# Pending "Sign in with GitHub" attempts: flow id -> (device code, expiry). One local user, so only the latest
# attempt is kept; the device code itself never leaves the server.
_flows: dict[str, tuple[gh.DeviceCode, float]] = {}


@router.post("/api/github/login/start")
def login_start() -> dict:
    client_id = get_settings().github_client_id
    if not client_id:
        raise HTTPException(400, gh.MSG_NO_CLIENT_ID)
    try:
        code = gh.start_device_flow(client_id)
    except gh.GitHubError as exc:
        raise HTTPException(502, str(exc)) from exc
    flow_id = secrets.token_urlsafe(16)
    _flows.clear()
    _flows[flow_id] = (code, time.monotonic() + code.expires_in)
    return {"flow_id": flow_id, "user_code": code.user_code, "verification_uri": code.verification_uri,
            "interval": code.interval, "expires_in": code.expires_in}


class PollIn(BaseModel):
    flow_id: str


@router.post("/api/github/login/poll")
def login_poll(body: PollIn) -> dict:
    code, expires_at = _flows.get(body.flow_id, (None, 0.0))
    if code is None or time.monotonic() > expires_at:
        _flows.pop(body.flow_id, None)
        return {"status": "expired"}
    try:
        status, token = gh.poll_device_flow(get_settings().github_client_id, code.device_code)
    except gh.GitHubError as exc:
        raise HTTPException(502, str(exc)) from exc
    if status in ("pending", "slow_down"):
        return {"status": status}
    _flows.pop(body.flow_id, None)  # finished: signed in, expired or denied
    if status != "ok":
        return {"status": status}
    update_env(_login(token=token))
    return {"status": "ok", "account": _account()}


class TokenIn(BaseModel):
    token: str


@router.post("/api/github/login/token")
def login_token(body: TokenIn) -> dict:
    token = body.token.strip()
    try:
        user = gh.get_user(token)
    except gh.GitHubError as exc:
        raise HTTPException(400, str(exc)) from exc
    update_env(_login(token=token))
    return {"account": {**user, "via": "token"}}


@router.post("/api/github/login/gh-cli")
def login_gh_cli() -> dict:
    token = gh.gh_cli_token()
    if not token:
        raise HTTPException(400, gh.MSG_GH_CLI_LOGGED_OUT)
    try:
        user = gh.get_user(token)
    except gh.GitHubError as exc:
        raise HTTPException(400, str(exc)) from exc
    update_env(_login(use_gh_cli=True))  # the gh token is read when needed, never copied into .env
    return {"account": {**user, "via": "gh"}}


@router.post("/api/github/logout")
def logout() -> dict:
    update_env(_login())
    return {"ok": True}


# ------------------------------------------------------------------------------------------------ repo and import


@router.get("/api/github/repos")
def repos() -> dict:
    token, _ = gh.current_token(get_settings())
    if not token:
        return {"repos": []}
    try:
        return {"repos": gh.list_repos(token)}
    except gh.GitHubError as exc:
        raise HTTPException(400, str(exc)) from exc


class RepoIn(BaseModel):
    repo: str


@router.post("/api/github/repo")
def choose_repo(body: RepoIn) -> dict:
    repo = gh.parse_repo(body.repo)
    if not repo:
        raise HTTPException(422, gh.MSG_BAD_REPO_INPUT)
    token, _ = gh.current_token(get_settings())
    try:
        info = gh.check_repo(repo, token)
    except gh.GitHubError as exc:
        raise HTTPException(400, str(exc)) from exc
    update_env({"GITHUB_REPO": info["full_name"]})
    return {"repo": info}


@router.post("/api/github/disconnect")
def disconnect() -> dict:
    update_env({"GITHUB_REPO": "", **_login()})
    return {"ok": True}


@router.post("/api/github/import")
def import_github(session: SessionDep, embedder: Annotated[Embedder, Depends(embedder_dep)]) -> dict:
    try:
        stats = ingest_documents(session, build_connector("github", get_settings()).fetch(), embedder)
    except ConnectorError as exc:
        session.rollback()
        raise HTTPException(502, str(exc)) from exc
    return {"imported": stats.as_dict()}
