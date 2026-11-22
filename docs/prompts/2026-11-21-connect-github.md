# 2026-11-21 — Connect tools page (GitHub) and a separate seed repo

Recorded per [AI_GUIDELINES.md](../../AI_GUIDELINES.md) §2.

## Tool / Model
- Claude Opus 5.5 (`claude-opus-5-5`), through Claude Code (CLI)

## Prompts (summaries)
1. Let users connect GitHub, Notion and Discord from the browser instead of editing `.env`: automatic where possible, otherwise explain each step as simply as possible.
   - The AI first built a `/setup` page with all three tools on one page.
2. Don't connect to this project's own repo (each user should choose theirs). Make the page a simple hub with a step-by-step flow that explains what to enter, ideally with reference images. Start with the hub and the GitHub connection only.
   - Rebuilt as a "Connect tools" overview plus three GitHub steps (sign in → choose a repo → import) with illustrations; no repo is preselected.
3. Update the work to fit `main` after PR #11 was merged, matching its UI.
   - The pages moved to `/connect` and use #11's `web/` styles and shared JS; the home page stays #11's ask page.
4. Give the seed script its own `SEED_GITHUB_REPO`, and keep `GITHUB_REPO` for the real repo the app reads.
5. Clean up the changes; code and the documentation we wrote in English only, except for UI text.

## AI responses / recommendations (summary)
| Recommendation | Result |
|---|---|
| Three GitHub sign-in options: "Sign in with GitHub" (OAuth device flow, needs only a public client id), the `gh` CLI login when the user chooses it, or a pasted fine-grained token; public repos work without signing in | Pending review (device flow needs an OAuth App first) |
| Settings stay in `.env`, written by the page (comments and line endings kept, permissions 600 on POSIX), applied immediately | Pending review |
| The connect routes only accept localhost (Host check) and refuse cross-site requests (Origin check); tokens are never sent to the browser | Pending review |
| GitHub `external_id` includes the repo (`owner/repo#issue:1`) so repos and the practice data never overwrite each other | Pending review (old databases need `--reset`) |
| Seeding writes to `SEED_GITHUB_REPO` and refuses to run when it equals `GITHUB_REPO`; `ingest.py --seed-repo` indexes the seeded workspace | Pending review |
| Initially: detect the repo of the current checkout and connect it automatically | **Rejected**: other users should choose their own repo |
| First version of `/setup` with all three tools on one page | **Rejected**: too complex; replaced by an overview plus step-by-step flow |

## Verification (done by the AI)
- `pytest`: 103 passed, 1 skipped; `ruff check .`: passed
- In a sandbox copy (its own `.env` and database): signed in with `gh` → listed the account's 22 repos → chose `TTT426/Group16` → imported 24 documents → search found PR #10 → disconnecting cleared `.env`
- Headless Chrome screenshots of `/`, `/connect`, every `/connect/github` step and #11's three pages; fixed `hidden` being overridden by `display` rules such as `.stack`
- Real GitHub API error cases (invalid token, missing repo) were exercised; the device flow was tested with mocks only
- **Not yet verified:** "Sign in with GitHub" needs a registered OAuth App and `GITHUB_CLIENT_ID`; not run on Windows
