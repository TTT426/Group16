"""Write the evaluation scenarios to real GitHub / Notion / Discord (the simulated project workspace).

Two phases, because items link to each other and links need real URLs:
  1. create the "containers" (issues, pull requests, Notion pages, Discord threads) and record their URLs
  2. fill in the content, replacing every {{tool.type.key}} placeholder with the recorded URL

Progress is saved to a state file after every item, so a run can be resumed and never creates duplicates.
Authors in the scenarios are fictional: GitHub items start with "原作者：…", Discord messages are posted through
a webhook with the author as display name (the bot cannot post as other users).
"""

import base64
import json
import re
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from .config import Settings
from .connectors.base import ConnectorError
from .connectors.http import request
from .connectors.notion import NOTION_VERSION
from .github_account import current_token

PLACEHOLDER = re.compile(r"\{\{\s*([a-z]+\.[a-z]+\.[\w-]+)\s*\}\}")


class SeedState:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        for key in ("urls", "github", "notion", "discord", "filled"):
            self.data.setdefault(key, {})

    @property
    def urls(self) -> dict:
        return self.data["urls"]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(json.dumps(self.data, ensure_ascii=False, indent=1).encode("utf-8"))

    def is_filled(self, ref: str) -> bool:
        return bool(self.data["filled"].get(ref))

    def mark_filled(self, ref: str) -> None:
        self.data["filled"][ref] = True
        self.save()

    def resolve(self, text: str) -> str:
        return PLACEHOLDER.sub(lambda m: self.urls.get(m.group(1), f"（尚未建立：{m.group(1)}）"), text or "")


class _Seeder:
    source = ""

    def __init__(self, client: httpx.Client, sleep: Callable[[float], None]) -> None:
        self.client = client
        self.sleep = sleep

    def _call(self, method: str, url: str, **kwargs) -> dict:
        response = request(self.client, method, url, source=self.source, sleep=self.sleep, **kwargs)
        return response.json() if response.content else {}


def github_seed_target(settings: Settings) -> tuple[str, str]:
    """(repo, token) to seed into. The seed repo must be set and must not be the repo the app reads from."""
    repo = settings.seed_github_repo.strip()
    if "/" not in repo:
        raise ConnectorError("github: set SEED_GITHUB_REPO in .env to an empty test repo (owner/repo). "
                             "Seeding creates issues, merges pull requests and commits files there.")
    if repo.lower() == settings.github_repo.strip().lower():
        raise ConnectorError(f"github: SEED_GITHUB_REPO is the same as GITHUB_REPO ({repo}), the team's real repo. "
                             "Seeding would write fake content into it; use a separate empty test repo.")
    token, _ = current_token(settings)  # the login chosen on the connect page (token or gh CLI)
    if not token:
        raise ConnectorError("github: no GitHub login. Sign in on the /connect page or set GITHUB_TOKEN.")
    return repo, token


def notion_seed_target(settings: Settings) -> tuple[str, str]:
    """(token, parent page id) to seed into: a separate connection, never the one the app imports with."""
    token = settings.seed_notion_token.strip()
    if not token:
        raise ConnectorError("notion: set SEED_NOTION_TOKEN in .env to the API token of a separate connection for "
                             "the test workspace. Every page the app's connection can see is imported.")
    if token == settings.notion_token.strip():
        raise ConnectorError("notion: SEED_NOTION_TOKEN is the same as NOTION_TOKEN, the connection the app imports "
                             "with. Seeded pages would show up next to the team's real pages; use a separate one.")
    if not settings.notion_parent_page_id.strip():
        raise ConnectorError("notion: set NOTION_PARENT_PAGE_ID to a page shared with the seed connection.")
    return token, settings.notion_parent_page_id.strip()


def discord_seed_target(settings: Settings) -> tuple[str, str]:
    """(bot token, server id) to seed into: a separate test server, never the one the app reads."""
    guild_id = settings.seed_discord_guild_id.strip()
    if not guild_id:
        raise ConnectorError("discord: set SEED_DISCORD_GUILD_ID in .env to a separate test server. Seeding creates "
                             "channels and threads and posts messages there.")
    if guild_id == settings.discord_guild_id.strip():
        raise ConnectorError("discord: SEED_DISCORD_GUILD_ID is the same as DISCORD_GUILD_ID, the team's server. "
                             "Seeding would post fake threads into it, even into existing channels; "
                             "use a separate test server.")
    if not settings.discord_bot_token.strip():
        raise ConnectorError("discord: no bot token. Connect Discord on the /connect page "
                             "or set DISCORD_BOT_TOKEN.")
    return settings.discord_bot_token.strip(), guild_id


# Read setting -> seed setting, per source: what `ingest.py --seed-workspace` swaps in.
SEED_SETTINGS = {
    "github": ("github_repo", "seed_github_repo"),
    "notion": ("notion_token", "seed_notion_token"),
    "discord": ("discord_guild_id", "seed_discord_guild_id"),
}


def seed_workspace_settings(settings: Settings, sources: list[str]) -> Settings:
    """Settings that read the seeded test workspace instead of the team's real tools, for the given sources."""
    updates = {}
    for source in sources:
        read, seed = SEED_SETTINGS[source]
        if not getattr(settings, seed):
            raise ConnectorError(f"{source}: {seed.upper()} is not set, so there is no seeded workspace to read.")
        updates[read] = getattr(settings, seed)
    return settings.model_copy(update=updates)


class GitHubSeeder(_Seeder):
    source = "github"

    def __init__(self, repo: str, token: str, *, merge: bool = True, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if "/" not in repo or not token:
            raise ConnectorError("github: SEED_GITHUB_REPO (owner/repo) and a GitHub login are required for seeding.")
        client = client or httpx.Client(base_url="https://api.github.com", timeout=30.0)
        client.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})
        super().__init__(client, sleep)
        self.repo, self.merge = repo, merge
        self._base: str | None = None

    def base_branch(self) -> str:
        if self._base is None:
            self._base = self._call("GET", f"/repos/{self.repo}")["default_branch"]
        return self._base

    def create(self, scenario: dict, state: SeedState) -> None:
        gh = scenario["github"]
        for issue in gh.get("issues", []):
            ref = f"github.issue.{issue['key']}"
            if ref in state.urls:
                continue
            data = self._call("POST", f"/repos/{self.repo}/issues",
                              json={"title": issue["title"], "body": "（建立中）"})
            state.data["github"][ref] = {"number": data["number"], "kind": "issue"}
            state.urls[ref] = data["html_url"]
            state.save()
        for pull in gh.get("pulls", []):
            ref = f"github.pull.{pull['key']}"
            if ref in state.urls:
                continue
            branch = f"seed/{pull['key']}"
            sha = self._call("GET", f"/repos/{self.repo}/git/ref/heads/{self.base_branch()}")["object"]["sha"]
            try:
                self._call("POST", f"/repos/{self.repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha})
            except ConnectorError:
                pass  # branch left over from an interrupted run
            note = f"# {pull['title']}\n\nSeeded change for the evaluation scenario.\n"
            self._call("PUT", f"/repos/{self.repo}/contents/seed/{pull['key']}.md",
                       json={"message": pull["title"], "content": _b64(note), "branch": branch})
            data = self._call("POST", f"/repos/{self.repo}/pulls", json={
                "title": pull["title"], "head": branch, "base": self.base_branch(), "body": "（建立中）"})
            state.data["github"][ref] = {"number": data["number"], "kind": "pull"}
            state.urls[ref] = data["html_url"]
            state.save()

    def fill(self, scenario: dict, state: SeedState) -> None:
        gh = scenario["github"]
        items = [("issue", i) for i in gh.get("issues", [])] + [("pull", p) for p in gh.get("pulls", [])]
        for kind, item in items:
            ref = f"github.{kind}.{item['key']}"
            if state.is_filled(ref) or ref not in state.data["github"]:
                continue
            number = state.data["github"][ref]["number"]
            header = f"> 原作者：{item.get('author', 'unknown')}"
            if item.get("labels"):
                header += f"　標籤：{', '.join(item['labels'])}"
            body = f"{header}\n\n{state.resolve(item.get('body', ''))}"
            endpoint = "pulls" if kind == "pull" else "issues"  # a PR body is updated through the pulls API
            self._call("PATCH", f"/repos/{self.repo}/{endpoint}/{number}", json={"body": body})
            for comment in item.get("comments", []):
                self._call("POST", f"/repos/{self.repo}/issues/{number}/comments",
                           json={"body": f"**{comment['author']}**：\n\n{state.resolve(comment['body'])}"})
            if kind == "pull" and self.merge:
                self._call("PUT", f"/repos/{self.repo}/pulls/{number}/merge", json={"merge_method": "squash"})
            state.mark_filled(ref)
        for f in gh.get("files", []):
            ref = f"github.file.{f['path']}"
            if state.is_filled(ref):
                continue
            payload = {"message": f"Add {f['path']}", "content": _b64(state.resolve(f["content"]))}
            try:
                payload["sha"] = self._call("GET", f"/repos/{self.repo}/contents/{f['path']}")["sha"]
            except ConnectorError:
                pass  # new file
            self._call("PUT", f"/repos/{self.repo}/contents/{f['path']}", json=payload)
            state.mark_filled(ref)


class NotionSeeder(_Seeder):
    source = "notion"

    def __init__(self, token: str, parent_page_id: str, *, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not token or not parent_page_id:
            raise ConnectorError("notion: NOTION_TOKEN and NOTION_PARENT_PAGE_ID are required for seeding.")
        client = client or httpx.Client(base_url="https://api.notion.com/v1", timeout=30.0)
        client.headers.update({"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION})
        super().__init__(client, sleep)
        self.parent = parent_page_id

    def create(self, scenario: dict, state: SeedState) -> None:
        for page in scenario["notion"]["pages"]:
            ref = f"notion.page.{page['key']}"
            if ref in state.urls:
                continue
            data = self._call("POST", "/pages", json={
                "parent": {"page_id": self.parent},
                "properties": {"title": {"title": [{"text": {"content": page["title"]}}]}},
            })
            state.data["notion"][ref] = data["id"]
            state.urls[ref] = data["url"]
            state.save()

    def fill(self, scenario: dict, state: SeedState) -> None:
        for page in scenario["notion"]["pages"]:
            ref = f"notion.page.{page['key']}"
            if state.is_filled(ref) or ref not in state.data["notion"]:
                continue
            blocks = markdown_to_blocks(state.resolve(page["content"]), skip_title=page["title"])
            for start in range(0, len(blocks), 100):  # API limit: 100 blocks per request
                self._call("PATCH", f"/blocks/{state.data['notion'][ref]}/children",
                           json={"children": blocks[start:start + 100]})
            state.mark_filled(ref)


class DiscordSeeder(_Seeder):
    source = "discord"

    def __init__(self, token: str, guild_id: str, *, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not token or not guild_id:
            raise ConnectorError("discord: DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required for seeding.")
        client = client or httpx.Client(base_url="https://discord.com/api/v10", timeout=30.0)
        client.headers.update({"Authorization": f"Bot {token}"})
        super().__init__(client, sleep)
        self.guild = guild_id

    def _channel_id(self, name: str, state: SeedState) -> str:
        channels = state.data["discord"].setdefault("channels", {})
        if name not in channels:
            existing = [c for c in self._call("GET", f"/guilds/{self.guild}/channels")
                        if c.get("type") == 0 and c.get("name") == name]
            channel = existing[0] if existing else self._call(
                "POST", f"/guilds/{self.guild}/channels", json={"name": name, "type": 0})
            channels[name] = channel["id"]
            state.save()
        return channels[name]

    def create(self, scenario: dict, state: SeedState) -> None:
        threads = state.data["discord"].setdefault("threads", {})
        for channel in scenario["discord"]["channels"]:
            channel_id = self._channel_id(channel["name"], state)
            for thread in channel["threads"]:
                ref = f"discord.thread.{thread['key']}"
                if ref in state.urls:
                    continue
                # type 11 = public thread; without it Discord creates a private thread.
                data = self._call("POST", f"/channels/{channel_id}/threads",
                                  json={"name": thread["title"][:100], "type": 11, "auto_archive_duration": 10080})
                threads[ref] = {"id": data["id"], "channel_id": channel_id}
                state.urls[ref] = f"https://discord.com/channels/{self.guild}/{data['id']}"
                state.save()

    def _webhook(self, channel_id: str, state: SeedState) -> dict:
        hooks = state.data["discord"].setdefault("webhooks", {})
        if channel_id not in hooks:
            data = self._call("POST", f"/channels/{channel_id}/webhooks", json={"name": "group16-seed"})
            hooks[channel_id] = {"id": data["id"], "token": data["token"]}
            state.save()
        return hooks[channel_id]

    def fill(self, scenario: dict, state: SeedState) -> None:
        threads = state.data["discord"].get("threads", {})
        for channel in scenario["discord"]["channels"]:
            for thread in channel["threads"]:
                ref = f"discord.thread.{thread['key']}"
                if state.is_filled(ref) or ref not in threads:
                    continue
                info = threads[ref]
                hook = self._webhook(info["channel_id"], state)
                for message in thread["messages"]:
                    self._call("POST", f"/webhooks/{hook['id']}/{hook['token']}",
                               params={"wait": "true", "thread_id": info["id"]},
                               json={"content": state.resolve(message["content"])[:2000],
                                     "username": message["author"][:80]})
                state.mark_filled(ref)


def markdown_to_blocks(markdown: str, skip_title: str = "") -> list[dict]:
    blocks = []
    for line in markdown.splitlines():
        text = line.strip()
        if not text or text == f"# {skip_title}":
            continue
        kind = "paragraph"
        for prefix, block_type in (("### ", "heading_3"), ("## ", "heading_2"), ("# ", "heading_1"),
                                   ("- ", "bulleted_list_item")):
            if text.startswith(prefix):
                kind, text = block_type, text[len(prefix):]
                break
        else:
            numbered = re.match(r"^\d+\.\s+(.*)$", text)
            if numbered:
                kind, text = "numbered_list_item", numbered.group(1)
        text = text.replace("**", "")[:2000]  # Notion caps rich text content at 2000 characters
        blocks.append({"object": "block", "type": kind,
                       kind: {"rich_text": [{"type": "text", "text": {"content": text}}]}})
    return blocks


def seed(scenarios: list[dict], seeders: list[_Seeder], state: SeedState) -> dict:
    for seeder in seeders:  # phase 1: containers on every platform first, so all URLs are known
        for scenario in scenarios:
            seeder.create(scenario, state)
    for seeder in seeders:  # phase 2: content with resolved links
        for scenario in scenarios:
            seeder.fill(scenario, state)
    return {"items": len(state.urls), "filled": sum(1 for v in state.data["filled"].values() if v)}


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")
