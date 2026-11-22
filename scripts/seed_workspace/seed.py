"""Write the evaluation scenarios to the real GitHub / Notion / Discord used in the study's baseline round.

  python scripts/seed_workspace/seed.py --dry-run              # show what would be created
  python scripts/seed_workspace/seed.py github notion discord  # create everything (resumable)

Needs in .env: SEED_GITHUB_REPO (an empty test repo, never GITHUB_REPO) + a GitHub login (the connect page, or
GITHUB_TOKEN); SEED_NOTION_TOKEN (a separate connection, never NOTION_TOKEN) + NOTION_PARENT_PAGE_ID
(a page shared with the integration), DISCORD_BOT_TOKEN + DISCORD_GUILD_ID (bot with Manage Channels,
Create Public Threads and Manage Webhooks). Progress is kept in data/seed_state.json; delete it to seed again.
Afterwards index the seeded tools:  python scripts/ingest.py --reset --seed-workspace github notion discord
"""

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.config import REPO_ROOT, get_settings  # noqa: E402
from app.connectors.base import ConnectorError  # noqa: E402
from app.seeding import (  # noqa: E402
    DiscordSeeder,
    GitHubSeeder,
    NotionSeeder,
    SeedState,
    github_seed_target,
    notion_seed_target,
    seed,
)

PLATFORMS = ("github", "notion", "discord")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("platforms", nargs="*", choices=PLATFORMS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-merge", action="store_true", help="leave the scenario pull requests open")
    parser.add_argument("--state", default=str(REPO_ROOT / "data" / "seed_state.json"))
    args = parser.parse_args()

    scenarios = [yaml.safe_load(p.read_text(encoding="utf-8"))
                 for p in sorted(Path(__file__).parent.glob("scenario_*.yaml"))]
    if args.dry_run or not args.platforms:
        for s in scenarios:
            gh = s["github"]
            threads = sum(len(c["threads"]) for c in s["discord"]["channels"])
            print(f"{s['id']}: GitHub {len(gh.get('issues', []))} issues, {len(gh.get('pulls', []))} PRs, "
                  f"{len(gh.get('files', []))} files; Notion {len(s['notion']['pages'])} pages; "
                  f"Discord {threads} threads")
        if not args.platforms:
            print("\nChoose platforms to seed, e.g.: python scripts/seed_workspace/seed.py github notion discord")
        return

    settings = get_settings()
    builders = {
        "github": lambda: GitHubSeeder(*github_seed_target(settings), merge=not args.no_merge),
        "notion": lambda: NotionSeeder(*notion_seed_target(settings)),
        "discord": lambda: DiscordSeeder(settings.discord_bot_token, settings.discord_guild_id),
    }
    try:
        seeders = [builders[p]() for p in PLATFORMS if p in args.platforms]
        result = seed(scenarios, seeders, SeedState(Path(args.state)))
    except ConnectorError as exc:
        sys.exit(f"Seeding stopped: {exc}\nFix the problem and run the same command again; finished items are kept.")
    print(f"Done: {result['items']} items, {result['filled']} filled. State: {args.state}")
    missing = [p for p in PLATFORMS if p not in args.platforms]
    if missing:
        print(f"Note: links to {', '.join(missing)} stay as placeholders until you seed those platforms too.")


if __name__ == "__main__":
    main()
