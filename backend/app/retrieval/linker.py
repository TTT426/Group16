"""Find cross-tool references inside a text and resolve them to stored documents.

Example: a Discord thread that pastes a PR link pulls that PR into the results,
even if the PR itself did not match the query. This is where "integration"
adds value beyond searching each tool separately.
"""

import re
from dataclasses import dataclass

GITHUB_ITEM = re.compile(r"https?://github\.com/([\w.-]+/[\w.-]+)/(?:issues|pull)/(\d+)")
NOTION_URL = re.compile(r"https?://(?:www\.)?notion\.(?:so|site)/\S*?([0-9a-f]{32})\b")
DISCORD_URL = re.compile(r"https?://(?:\w+\.)?discord(?:app)?\.com/channels/\d+/(\d+)(?:/(\d+))?")
HASH_REF = re.compile(r"(?<![\w&/#])#(\d{1,6})\b")


@dataclass(frozen=True)
class DocRef:
    """A resolvable reference: either an exact (source, external_id) or a GitHub number in a repo."""

    source: str
    external_ids: tuple[str, ...]
    repo: str | None = None  # GitHub only; None = same repo as the citing document


def find_references(text: str, *, source: str) -> list[DocRef]:
    refs: list[DocRef] = []
    for repo, number in GITHUB_ITEM.findall(text):
        refs.append(DocRef("github", (f"issue:{number}", f"pr:{number}"), repo.lower()))
    for page_hex in NOTION_URL.findall(text):
        page_id = f"{page_hex[:8]}-{page_hex[8:12]}-{page_hex[12:16]}-{page_hex[16:20]}-{page_hex[20:]}"
        refs.append(DocRef("notion", (page_id,)))
    for channel_or_thread, message in DISCORD_URL.findall(text):
        ids = [f"thread:{channel_or_thread}"]
        if message:
            ids.append(f"channel:{channel_or_thread}:{message}")
        refs.append(DocRef("discord", tuple(ids)))
    if source == "github":
        # "#12" only means an issue / PR when written inside GitHub; elsewhere it is ambiguous.
        stripped = GITHUB_ITEM.sub("", text)
        for number in HASH_REF.findall(stripped):
            refs.append(DocRef("github", (f"issue:{number}", f"pr:{number}")))
    return refs


def github_repo_of(url: str) -> str | None:
    match = re.match(r"https?://github\.com/([\w.-]+/[\w.-]+)/", url or "")
    return match.group(1).lower() if match else None
