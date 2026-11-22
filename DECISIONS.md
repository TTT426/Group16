# Decisions Log

## 2026-09-21 — Initial code steward

**What:** Nathan is the initial code steward for the team. \
**Why:** Volunteered for this part.

## 2026-11-21 — MVP 技術選型（提案，待組內確認）

**What:** 後端用 Python + FastAPI；資料庫用 PostgreSQL 16 + pgvector + pg_trgm；embedding 預設用本地的 `BAAI/bge-m3`；前端用 Jinja2 + HTMX。 \
**Why:** 全組只需要會 Python；一個資料庫就能放文件、向量、決策和評估紀錄；bge-m3 支援中英文、免費，而且訂閱制 LLM 本來就不提供 embedding。 \
**Status:** 已確認（見下方〈2026-11-21 小組討論結果〉）。之後資料庫、embedding 的部分被〈降低外部依賴〉取代，pg_trgm 被〈M2 檢索與連接器〉取代，前端改為純 HTML + JavaScript（〈完整版〉提案）。

## 2026-11-21 — LLM 介面抽象化、可以切換（提案，待組內確認）

**What:** 所有 LLM 呼叫都透過 `LLMProvider` 介面，用 `LLM_PROVIDER` 環境變數切換：`claude_cli`（Claude 訂閱）、`anthropic_api`（API 按量計費）、`fake`（離線開發 / 測試）；`openai_api`、`ollama`、`codex_cli` 留到 M5。 \
**Why:** 開發和 demo 可以用訂閱額度省錢；正式評估如果有額度或使用條款上的疑慮，可以直接改用 API，程式不用改。 \
**Status:** 已確認（見下方〈2026-11-21 小組討論結果〉）。`LLMProvider` 介面保留；〈完整版〉提案改為只使用 Claude CLI（待確認）。 

## 2026-11-21 — M2 檢索與連接器實作方式（提案，待組內確認）

**What:** 關鍵字搜尋改用 Python 內的 BM25（中文用單字＋雙字詞切分），不用 `pg_trgm`；Discord 改用 REST API，不用 `discord.py`；加入 `ruff` 當 linter；DB 測試用 `pgserver` 內嵌 Postgres。 \
**Why:** `pg_trgm` 對中文不可靠；只讀歷史訊息不需要 gateway 連線；AI_GUIDELINES 要求通過 linter 才能合併，但原本沒有 linter；組員不一定有 Docker。 \
**Status:** 提案（小組討論尚未表決這筆）。「DB 測試用 pgserver」已被〈降低外部依賴〉取代（改用暫存 SQLite）。細節見 `docs/PROJECT_PLAN.md` §9。 

## 2026-11-21 — 降低外部依賴：SQLite、fastembed、一鍵啟動（提案，待組內確認）

**What:** 資料庫只用 SQLite 檔案（不保留 PostgreSQL 選項，不再需要 pgvector / Docker）；embedding 改成 fastembed + `BAAI/bge-small-zh-v1.5`（不需要 torch，裝不起來時自動退回 hashing），移除 sentence-transformers；`LLM_PROVIDER` 預設 `auto`；新增 `start.bat` / `start.sh` 一鍵啟動。這筆取代前面「PostgreSQL + pgvector、bge-m3」的提案內容。 \
**Why:** 組員的電腦環境不同（沒有 Docker、Windows 中文路徑、Mac / Linux），原本的依賴容易裝不起來；在兩個評估情境的檢索測試中，小模型（命中 21/24）比 bge-m3（17/24）好，而且快約 10 倍。 \
**Status:** 已確認（見下方〈2026-11-21 小組討論結果〉；Code steward 已核准 PR #10）。`LLM_PROVIDER` 預設 `auto` 由〈完整版〉提案改為只用 Claude CLI（待確認）。細節見 `docs/PROJECT_PLAN.md` §10。

## 2026-11-21 — Code steward 審閱：PR #10

**What:** Nathan 以 code steward 身分審閱 [#10](https://github.com/TTT426/Group16/pull/10) \
**Outcome**：approved \
**What the mainly change/improve** : 降低外部依賴：SQLite、fastembed、一鍵啟動 \
**Led by:** @boanhsu1213

## 2026-11-21 小組討論結果

MVP 技術選型 -> 可執行並實作 \
LLM 介面抽象化、可以切換 -> 可執行並實作 \
降低外部依賴：SQLite、fastembed、一鍵啟動 -> 可執行並實作: \
Mac 環境上的部署由 @hojinpongcs09-lab 完成並測試

## 2026-11-21 — 完整版 MVP：PR #11（提案，待組內確認）

**What:** 提案 [#11](https://github.com/TTT426/Group16/pull/11)：LLM 只用 Claude Code CLI（移除 `anthropic_api`）；AI 問答預設 `rag`（rag / full / agent 三種模式在評估情境上準確度幾乎相同，98% / 98% / 100%，rag 最快，見 `docs/EVAL_MODES.md`）；網頁介面用純 HTML + JavaScript（不用 Jinja2 / HTMX）；決策紀錄要所有參與者確認後才存檔；資料庫新欄位在啟動時自動補上。 \
**What the mainly change/improve** : 完整版 MVP：AI 問答、評估工具、決策紀錄、seed 腳本 \
**Led by:** @boanhsu1213

## 2026-11-21 — Code steward 審閱：PR #11

**What:** TTT426 以 code steward 身分審閱 [#11](https://github.com/TTT426/Group16/pull/11) \
**Outcome**：approved \
**What the mainly change/improve** : 完整版 MVP 功能串接、修關於 System Prompt 的穩定性問題 \
**More comment** : should use PR templatement and avoid plug in too much infomation in a same \  
**Led by:** @boanhsu1213

## 2026-11-21 — Connect tools from the browser; separate seed repo (proposal, pending team confirmation)

**What:** New "Connect tools" page (`/connect`). GitHub is set up in three steps (sign in → choose a repo → import), and the page writes the settings to `.env`, so nobody edits it by hand. Sign-in options: OAuth device flow (needs one GitHub OAuth App registered by the team; `GITHUB_CLIENT_ID` is public), the existing `gh` CLI login, or a fine-grained token. These routes only accept localhost requests, refuse cross-site requests, and never send tokens to the browser. GitHub document ids now include the repo (`owner/repo#issue:1`). The seed script writes to a new `SEED_GITHUB_REPO`; `GITHUB_REPO` is only read, and seeding refuses to run when the two are the same. \ 
**Why:** Connecting real tools meant editing `.env` and working out token permissions by hand, which is too hard for new members. `GITHUB_REPO` meant both "the repo to read" and "the empty test repo the seed script writes into", so after connecting the team's real repo, seeding would have written fake content into it (including commits to main). GitHub items from different repos with the same number overwrote each other. \
**What the mainly change/improve** : Connect tools page (GitHub), separate seed repo \
**Led by:** @gdpps1028

## 2026-11-22 — Connect Notion from the browser; separate seed connection (proposal, pending team confirmation)

**What:** "Connect tools" gets a Notion flow (`/connect/notion`): a workspace owner creates an internal connection in Notion's Developer portal, the user pastes its API token, shares pages, and imports. The seed script writes Notion pages with a separate connection (`SEED_NOTION_TOKEN`) and refuses to run when it equals `NOTION_TOKEN`. `ingest.py --seed-repo` is renamed `--seed-workspace` and reads every configured seed setting. \
**Why:** The app imports every page its connection can see, so seeding with the same connection would mix fake scenario pages into the team's real workspace. Notion has no sign-in a local app can use without a server-side secret, so a guided "paste the API token" flow is the simplest option. \
**What the mainly change/improve** : Connect tools page (Notion), separate seed connection \
**Led by:** @gdpps1028

## 2026-11-22 — Connect Discord from the browser; separate seed server (proposal, pending team confirmation)

**What:** "Connect tools" gets a Discord flow (`/connect/discord`): create one bot for the team, switch on Message Content Intent, paste its token, invite it with read-only permissions (View Channels, Read Message History), choose the server, import. The seed script posts into a separate test server (`SEED_DISCORD_GUILD_ID`) and refuses to run when it equals `DISCORD_GUILD_ID`. \
**Why:** Seeding creates channels and threads in its server and reuses existing channels with matching names, so seeding into the team's server would post fake threads into real channels. Discord has no sign-in a local app can use without a server-side secret, so a guided "paste the bot token" flow is the simplest option; the page derives everything else from the token. \
**What the mainly change/improve** : Connect tools page (Discord), separate seed server \
**Led by:** @gdpps1028 

## 2026-11-22 — Code steward 審閱：PR #13

**What:** TTT426 以 code steward 身分審閱 [#13](https://github.com/TTT426/Group16/pull/13) \
**Outcome:** approved \
**What the mainly change/improve:** 
  1. Add more readable GUI interface 
  2. Connect GitHub from the browser 

**Led by:** @gdpps1028

## 2026-11-22 — Follow-up to the PR #11 steward review

**What:** Correction and follow-up to the 2026-11-21 entry. TTT426 reviewed #11 as code steward and merged it. The feedback was first left as a comment; the formal GitHub approval was submitted afterwards, on 2026-11-22. After the merge, @hojinpongcs09-lab reported that `test_config_lists_modes_and_scenarios` fails on a clean checkout (`/api/config` uses `get_session_factory()` instead of the injected session). \
**Follow-up:** : Just record this bug now. \
**Process note (proposal, pending team confirmation):** Submit reviews as formal GitHub reviews before merging, and run the tests on a clean checkout before approving. \
**Led by:** @TTT426


## 2026-11-22 — Code steward reviews: PR #14 and PR #15
**What:** At @hojinpongcs09-lab's request, Codex inspected both PRs, ran related tests on macOS, and submitted English substantive reviews with formal Approve under @hojinpongcs09-lab's account before merging. PR #14 (Notion) was merged first, then PR #15 (Discord), both into main rather than their old stacked base branches.
**Outcome:** Approved and merged. Notion: 33 related tests passed; Discord: 41 related tests passed; Ruff passed for both. DECISIONS.md conflicts were resolved by preserving both branches' records; no application code was changed during conflict resolution.
**Review comments:** Verified token validation and exclusion from responses, seed/real workspace separation, and Discord server membership checks and read-only invite permissions. Suggested additional import success and ConnectorError rollback/502 tests as non-blocking follow-up. Real-account validation was not repeated by this reviewer; Discord thread imports remain unverified.
**Evidence:** [PR #14](https://github.com/TTT426/Group16/pull/14), merge a51518f; [PR #15](https://github.com/TTT426/Group16/pull/15), merge 5d39fe8. Formal reviews and comments are recorded in GitHub.
**Led by:** @hojinpongcs09-lab (AI-assisted; authorized review and merge).

## 2026-11-22 — Sync PR #12 after Notion and Discord merges
**What:** Updated the original [PR #12](https://github.com/TTT426/Group16/pull/12) branch hjp-macos-setup with main at 5d39fe8. Retained --dev installation, minimal-mode compatibility, install-stamp behavior and fallback preserving development tools, alongside the new Notion and Discord connection flows.
**Why:** Keep the macOS development setup compatible with the current product without replacing teammates' connection features.
**Validation:** Apple Silicon macOS / Python 3.14: EMBEDDING_PROVIDER=hashing pytest: 126 passed, 1 skipped (opt-in real embedding test not enabled); Ruff and git diff --check passed. Existing environment/database were reused; this is not a clean-machine or real-account validation.
**Status:** Proposed update in PR #12; not yet merged. Detailed update log: docs/updates/2026-11-22-pr12-sync.md.
**Led by:** @hojinpongcs09-lab (Codex-assisted).

## 2026-11-22 — PR 處理順序：先審閱、記錄，再合併（提案，待組內確認）

**What:** 在 [AI_GUIDELINES.md](AI_GUIDELINES.md) 新增 Section 4〈Pull Request Order〉：從最新 main 開分支、一個 PR 一個主題、不堆疊 PR；作者在乾淨環境跑 pytest + ruff；由作者以外的組員擔任 code steward，在乾淨環境重跑測試並送出正式 review；AI 只能起草 review，核准與合併要 steward 針對該 PR 下指示；steward 審閱紀錄要在最後 Approve 前 commit 進同一個 PR；先 Approve 再合併；所有改動（包含 DECISIONS.md）都不直接推 main；同步用原本的 PR，不開重複 PR。 \
**Why:** 回顧 #9–#17：#9 沒有 review 就合併；#11 合併後才收到 review；#14、#15、#12 都是 AI 準備的核准，並在一兩分鐘內就合併；steward 紀錄在合併後才直接推 main 或另開 PR（#17）；#16 是 #12 的重複 PR。main 已有分支保護，必須透過 PR，所以合併後才補紀錄會多一輪審閱。 \
**What the mainly change/improve** : 固定 PR 從開分支到合併的順序，讓審閱在合併前完成、紀錄跟著改動一起進 main \
**Led by:** @boanhsu1213
