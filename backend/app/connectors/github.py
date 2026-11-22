"""GitHub connector: issues, pull requests (with comments) and markdown files of one repo, via the REST API."""

import base64
import time
from collections.abc import Callable, Iterator

import httpx

from .base import NormalizedDocument, github_external_id, parse_datetime
from .http import request

API_URL = "https://api.github.com"


def format_issue_text(
    *,
    kind: str,
    number: int,
    title: str,
    author: str | None,
    state: str,
    labels: list[str],
    body: str,
    comments: list[tuple[str | None, str, str]],
) -> str:
    """Render an issue / PR and its comments as plain text. `comments` = [(author, created_at, body)]."""
    lines = [f"{kind} #{number}: {title}", f"Author: {author or 'unknown'}", f"State: {state}"]
    if labels:
        lines.append(f"Labels: {', '.join(labels)}")
    lines += ["", (body or "").strip()]
    for c_author, c_created, c_body in comments:
        lines += ["", f"Comment by {c_author or 'unknown'} ({c_created[:10]}):", (c_body or "").strip()]
    return "\n".join(lines).strip()


class GitHubConnector:
    source = "github"

    def __init__(
        self,
        repo: str,
        token: str = "",
        *,
        include_markdown: bool = True,
        max_markdown_files: int = 200,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if "/" not in repo:
            raise ValueError(f"GITHUB_REPO must look like 'owner/repo', got {repo!r}")
        self.repo = repo
        self.include_markdown = include_markdown
        self.max_markdown_files = max_markdown_files
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = client or httpx.Client(base_url=API_URL, timeout=30.0)
        self._client.headers.update(headers)
        self._sleep = sleep

    def fetch(self) -> Iterator[NormalizedDocument]:
        for item in self._paginate(f"/repos/{self.repo}/issues", {"state": "all", "per_page": 100}):
            yield self._issue_document(item)
        if self.include_markdown:
            yield from self._markdown_documents()

    # -- helpers -----------------------------------------------------------------

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        return request(self._client, "GET", url, source=self.source, params=params, sleep=self._sleep)

    def _paginate(self, url: str, params: dict | None = None) -> Iterator[dict]:
        next_url: str | None = url
        while next_url:
            response = self._get(next_url, params)
            yield from response.json()
            next_url = response.links.get("next", {}).get("url")
            params = None  # the "next" link already carries the query string

    def _issue_document(self, item: dict) -> NormalizedDocument:
        number = item["number"]
        is_pr = "pull_request" in item
        comments: list[tuple[str | None, str, str]] = []
        if item.get("comments"):
            for c in self._paginate(f"/repos/{self.repo}/issues/{number}/comments", {"per_page": 100}):
                comments.append(((c.get("user") or {}).get("login"), c.get("created_at", ""), c.get("body") or ""))
        if is_pr:
            for c in self._paginate(f"/repos/{self.repo}/pulls/{number}/comments", {"per_page": 100}):
                body = f"[review on {c.get('path', '')}] {c.get('body') or ''}"
                comments.append(((c.get("user") or {}).get("login"), c.get("created_at", ""), body))
            comments.sort(key=lambda c: c[1])

        state = item.get("state", "")
        if is_pr and (item.get("pull_request") or {}).get("merged_at"):
            state = "merged"
        author = (item.get("user") or {}).get("login")
        kind = "Pull request" if is_pr else "Issue"
        return NormalizedDocument(
            source="github",
            external_id=github_external_id(self.repo, f"{'pr' if is_pr else 'issue'}:{number}"),
            url=item["html_url"],
            title=f"{kind} #{number}: {item.get('title', '')}",
            author=author,
            created_at=parse_datetime(item.get("created_at")),
            text=format_issue_text(
                kind=kind,
                number=number,
                title=item.get("title", ""),
                author=author,
                state=state,
                labels=[label["name"] for label in item.get("labels", [])],
                body=item.get("body") or "",
                comments=comments,
            ),
            raw={"number": number, "is_pr": is_pr, "state": state},
        )

    def _markdown_documents(self) -> Iterator[NormalizedDocument]:
        branch = self._get(f"/repos/{self.repo}").json()["default_branch"]
        tree = self._get(f"/repos/{self.repo}/git/trees/{branch}", {"recursive": "1"}).json()
        paths = [
            t["path"] for t in tree.get("tree", []) if t.get("type") == "blob" and t["path"].lower().endswith(".md")
        ]
        for path in paths[: self.max_markdown_files]:
            content = self._get(f"/repos/{self.repo}/contents/{path}", {"ref": branch}).json()
            raw_content = content.get("content") or ""
            if content.get("encoding") == "base64":
                text = base64.b64decode(raw_content).decode("utf-8", errors="replace")
            else:
                text = raw_content  # files over 1 MB come back with encoding "none" and no content
            if not text.strip():
                continue
            yield NormalizedDocument(
                source="github",
                external_id=github_external_id(self.repo, f"file:{path}"),
                url=content.get("html_url") or f"https://github.com/{self.repo}/blob/{branch}/{path}",
                title=f"File: {path}",
                text=f"File: {path}\n\n{text}".strip(),
                raw={"path": path, "branch": branch},
            )
