# 2026-11-22 — Connect tools page: Notion, and a separate seed connection

Recorded per [AI_GUIDELINES.md](../../AI_GUIDELINES.md) §2. Builds on [2026-11-21-connect-github.md](2026-11-21-connect-github.md).

## Tool / Model
- Claude Opus 5.5 (`claude-opus-5-5`), through Claude Code (CLI)

## Prompts (summaries)
1. Finish the Notion and Discord connections on top of the GitHub connect page. First check whether the connectors already exist; if so, only a good-looking GUI is needed, otherwise discuss.
   - The AI found both readers already implemented (mock-tested only) and that seeding writes into the same Notion connection / Discord server the app reads, and asked how to handle that and how to split the work.
2. Decisions: separate `SEED_*` settings for Notion and Discord (same pattern as `SEED_GITHUB_REPO`), and two stacked PRs (Notion first, Discord on top).
3. While testing, the user found that Notion now creates "connections" in its Developer portal (`app.notion.com/developers/connections`) instead of integrations, with a different flow; update the page to match.
   - The AI checked Notion's official developer docs and rewrote the steps, labels and illustrations (Developer connections → New connection → Authentication method: API token; token on the Configuration tab; pages via Content access or ••• → Connections). Only workspace owners can create connections, so the page now says so.

## AI responses / recommendations (summary)
| Recommendation | Result |
|---|---|
| `/connect/notion` in three steps: create an internal connection and paste its API token, share pages (lists what the connection can see, re-checks when the tab regains focus), import; illustrations of Notion's Developer portal | Pending review |
| A valid token is saved even before any page is shared, so the user can come back after sharing | Pending review |
| Overview cards and the step pages share helpers (`connect-common.js`, card helpers in `connect.html`) so Discord can reuse them | Pending review |
| Seeding uses `SEED_NOTION_TOKEN` (a separate connection) and refuses to run when it equals `NOTION_TOKEN` | Accepted (user's choice) |
| Rename `ingest.py --seed-repo` to `--seed-workspace`, which swaps in every configured seed setting | Pending review |

## Verification (done by the AI)
- `pytest`: 111 passed, 1 skipped; `ruff check .`: passed
- Steps and labels checked against Notion's developer docs (internal connections, personal access tokens, authorization)
- Headless Chrome screenshots of `/connect` and each `/connect/notion` step, plus `/connect/github` after the helper refactor; no console errors
- The real Notion API rejects an invalid token and the page shows the friendly message
- Real account (done by @gdpps1028 through the page): created an internal connection, shared a page, imported it. The AI then checked the result: connected, 1 page visible, 1 document imported with its full text and an `app.notion.com` link, and search finds it
- **Not yet verified:** running on Windows
