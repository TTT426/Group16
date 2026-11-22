# 2026-11-22 — Connect tools page: Discord, and a separate seed server

Recorded per [AI_GUIDELINES.md](../../AI_GUIDELINES.md) §2. Builds on [2026-11-22-connect-notion.md](2026-11-22-connect-notion.md).

## Tool / Model
- Claude Opus 5.5 (`claude-opus-5-5`), through Claude Code (CLI)

## Prompts (summaries)
1. Finish the Notion and Discord connections on top of the GitHub connect page; only a good-looking GUI is needed if the connectors already exist. Decisions after the AI's check: separate `SEED_*` settings, and two stacked PRs (this is the Discord one, on top of the Notion PR).

## AI responses / recommendations (summary)
| Recommendation | Result |
|---|---|
| `/connect/discord` in three steps: create the bot (one per team; teammates share the token privately) and switch on Message Content Intent, add it to the server, import; illustrations of the Developer Portal and the invite page | Pending review |
| After the token is pasted, the page works out the rest: whether Message Content Intent is on (with a direct link to the bot settings), the invite link, and the server (picked automatically when the bot is in only one) | Pending review |
| The invite link asks only for View Channels and Read Message History | Pending review |
| Seeding posts into `SEED_DISCORD_GUILD_ID` (a separate test server; the same bot may be in both) and refuses to run when it equals `DISCORD_GUILD_ID` | Accepted (user's choice) |

## Verification (done by the AI)
- `pytest`: 119 passed, 1 skipped; `ruff check .`: passed
- Headless Chrome screenshots of `/connect` with all three cards and each `/connect/discord` state (setup, Message Content off, choosing among several servers); no console errors
- The real Discord API rejects an invalid token and the page shows the friendly message
- Real account (done by @gdpps1028 through the page): created a bot, invited it to a server, imported it. The AI then checked the result: 48 documents from one server, every one with its message text (so Message Content Intent was on), and search finds them
- **Not yet verified:** a server with threads (the test server had channel messages only); running on Windows
