"""Scenario connector: loads the simulated workspace YAML files directly as documents.

Used for offline development, tests and golden-question runs without any API
tokens. Documents get realistic-looking URLs and the `{{tool.type.key}}`
cross-references are replaced by those URLs, mirroring what the seed scripts
produce on the real platforms. Texts are formatted with the same helpers as the
real connectors so retrieval behaves the same way.
"""

import hashlib
import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import yaml

from .base import NormalizedDocument
from .discord import format_messages
from .github import format_issue_text

GITHUB_REPO_URL = "https://github.com/example/shoplite"
DISCORD_GUILD_ID = "100000000000000000"
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z]+\.[a-z]+\.[\w-]+)\s*\}\}")
_FAKE_TS = "2026-10-01T09:00:00+00:00"


def _notion_id(key: str) -> str:
    return str(uuid.UUID(hashlib.md5(key.encode()).hexdigest()))


class ScenarioConnector:
    source = "scenario"

    def __init__(self, paths: list[str | Path]) -> None:
        self.scenarios = [yaml.safe_load(Path(p).read_text(encoding="utf-8")) for p in paths]
        self.urls = self._assign_urls()

    def _assign_urls(self) -> dict[str, str]:
        urls: dict[str, str] = {}
        number, thread_id = 0, 900000000000000000
        for s in self.scenarios:
            for issue in s["github"].get("issues", []):
                number += 1
                urls[f"github.issue.{issue['key']}"] = f"{GITHUB_REPO_URL}/issues/{number}"
            for pull in s["github"].get("pulls", []):
                number += 1
                urls[f"github.pull.{pull['key']}"] = f"{GITHUB_REPO_URL}/pull/{number}"
            for page in s["notion"]["pages"]:
                page_hex = _notion_id(page["key"]).replace("-", "")
                urls[f"notion.page.{page['key']}"] = f"https://www.notion.so/shoplite/{page['key']}-{page_hex}"
            for channel in s["discord"]["channels"]:
                for thread in channel["threads"]:
                    thread_id += 1
                    url = f"https://discord.com/channels/{DISCORD_GUILD_ID}/{thread_id}"
                    urls[f"discord.thread.{thread['key']}"] = url
        return urls

    def resolve(self, text: str) -> str:
        return _PLACEHOLDER.sub(lambda m: self.urls[m.group(1)], text or "")

    def fetch(self) -> Iterator[NormalizedDocument]:
        for s in self.scenarios:
            yield from self._github(s)
            yield from self._notion(s)
            yield from self._discord(s)

    def _github(self, s: dict) -> Iterator[NormalizedDocument]:
        gh = s["github"]
        items = [("issue", i) for i in gh.get("issues", [])] + [("pull", p) for p in gh.get("pulls", [])]
        for kind, item in items:
            url = self.urls[f"github.{kind}.{item['key']}"]
            number = int(url.rsplit("/", 1)[1])
            label = "Pull request" if kind == "pull" else "Issue"
            yield NormalizedDocument(
                source="github",
                external_id=f"{'pr' if kind == 'pull' else 'issue'}:{number}",
                url=url,
                title=f"{label} #{number}: {item['title']}",
                author=item.get("author"),
                text=format_issue_text(
                    kind=label,
                    number=number,
                    title=item["title"],
                    author=item.get("author"),
                    state="merged" if kind == "pull" else "open",
                    labels=item.get("labels", []),
                    body=self.resolve(item.get("body", "")),
                    comments=[(c["author"], _FAKE_TS, self.resolve(c["body"])) for c in item.get("comments", [])],
                ),
            )
        for f in s["github"].get("files", []):
            yield NormalizedDocument(
                source="github",
                external_id=f"file:{f['path']}",
                url=f"{GITHUB_REPO_URL}/blob/main/{f['path']}",
                title=f"File: {f['path']}",
                text=f"File: {f['path']}\n\n{self.resolve(f['content'])}".strip(),
            )

    def _notion(self, s: dict) -> Iterator[NormalizedDocument]:
        for page in s["notion"]["pages"]:
            yield NormalizedDocument(
                source="notion",
                external_id=_notion_id(page["key"]),
                url=self.urls[f"notion.page.{page['key']}"],
                title=page["title"],
                author=page.get("author"),
                text=f"{page['title']}\n\n{self.resolve(page['content'])}".strip(),
            )

    def _discord(self, s: dict) -> Iterator[NormalizedDocument]:
        for channel in s["discord"]["channels"]:
            for thread in channel["threads"]:
                url = self.urls[f"discord.thread.{thread['key']}"]
                title = f"#{channel['name']} › {thread['title']}"
                lines = [(m["author"], _FAKE_TS, self.resolve(m["content"])) for m in thread["messages"]]
                yield NormalizedDocument(
                    source="discord",
                    external_id=f"thread:{url.rsplit('/', 1)[1]}",
                    url=url,
                    title=title,
                    author=lines[0][0] if lines else None,
                    text=f"{title}\n\n{format_messages(lines)}",
                )
