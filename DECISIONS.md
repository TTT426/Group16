# Decisions Log

## 2026-09-21 — Initial code steward
**What:** Nathan is the initial code steward for the team.
**Why:** Volunteered for this part.

## 2026-11-21 — MVP 技術選型（提案，待組內確認）
**What:** 後端用 Python + FastAPI；資料庫用 PostgreSQL 16 + pgvector + pg_trgm；embedding 預設用本地的 `BAAI/bge-m3`；前端用 Jinja2 + HTMX。
**Why:** 全組只需要會 Python；一個資料庫就能放文件、向量、決策和評估紀錄；bge-m3 支援中英文、免費，而且訂閱制 LLM 本來就不提供 embedding。
**Status:** 已確認（見下方〈2026-11-21 小組討論結果〉）。之後資料庫、embedding 的部分被〈降低外部依賴〉取代，pg_trgm 被〈M2 檢索與連接器〉取代，前端改為純 HTML + JavaScript（〈完整版〉提案）。

## 2026-11-21 — LLM 介面抽象化、可以切換（提案，待組內確認）
**What:** 所有 LLM 呼叫都透過 `LLMProvider` 介面，用 `LLM_PROVIDER` 環境變數切換：`claude_cli`（Claude 訂閱）、`anthropic_api`（API 按量計費）、`fake`（離線開發 / 測試）；`openai_api`、`ollama`、`codex_cli` 留到 M5。
**Why:** 開發和 demo 可以用訂閱額度省錢；正式評估如果有額度或使用條款上的疑慮，可以直接改用 API，程式不用改。
**Status:** 已確認（見下方〈2026-11-21 小組討論結果〉）。`LLMProvider` 介面保留；〈完整版〉提案改為只使用 Claude CLI（待確認）。

## 2026-11-21 — M2 檢索與連接器實作方式（提案，待組內確認）
**What:** 關鍵字搜尋改用 Python 內的 BM25（中文用單字＋雙字詞切分），不用 `pg_trgm`；Discord 改用 REST API，不用 `discord.py`；加入 `ruff` 當 linter；DB 測試用 `pgserver` 內嵌 Postgres。
**Why:** `pg_trgm` 對中文不可靠；只讀歷史訊息不需要 gateway 連線；AI_GUIDELINES 要求通過 linter 才能合併，但原本沒有 linter；組員不一定有 Docker。
**Status:** 提案（小組討論尚未表決這筆）。「DB 測試用 pgserver」已被〈降低外部依賴〉取代（改用暫存 SQLite）。細節見 `docs/PROJECT_PLAN.md` §9。

## 2026-11-21 — 降低外部依賴：SQLite、fastembed、一鍵啟動（提案，待組內確認）
**What:** 資料庫只用 SQLite 檔案（不保留 PostgreSQL 選項，不再需要 pgvector / Docker）；embedding 改成 fastembed + `BAAI/bge-small-zh-v1.5`（不需要 torch，裝不起來時自動退回 hashing），移除 sentence-transformers；`LLM_PROVIDER` 預設 `auto`；新增 `start.bat` / `start.sh` 一鍵啟動。這筆取代前面「PostgreSQL + pgvector、bge-m3」的提案內容。
**Why:** 組員的電腦環境不同（沒有 Docker、Windows 中文路徑、Mac / Linux），原本的依賴容易裝不起來；在兩個評估情境的檢索測試中，小模型（命中 21/24）比 bge-m3（17/24）好，而且快約 10 倍。
**Status:** 已確認（見下方〈2026-11-21 小組討論結果〉；Code steward 已核准 PR #10）。`LLM_PROVIDER` 預設 `auto` 由〈完整版〉提案改為只用 Claude CLI（待確認）。細節見 `docs/PROJECT_PLAN.md` §10。

## 2026-11-21 — Code steward 審閱：PR #10
**What:** Nathan 以 code steward 身分審閱 [#10](https://github.com/TTT426/Group16/pull/10)
**Outcome**：approved
**What the mainly change/improve** : 降低外部依賴：SQLite、fastembed、一鍵啟動
**Led by:** @boanhsu1213

## 2026-11-21 小組討論結果
MVP 技術選型 -> 可執行並實作
LLM 介面抽象化、可以切換 -> 可執行並實作
降低外部依賴：SQLite、fastembed、一鍵啟動 -> 可執行並實作:
Mac 環境上的部署由 @hojinpongcs09-lab 完成並測試

## 2026-11-21 — 完整版 MVP：PR #11（提案，待組內確認）
**What:** 提案 [#11](https://github.com/TTT426/Group16/pull/11)：LLM 只用 Claude Code CLI（移除 `anthropic_api`）；AI 問答預設 `rag`（rag / full / agent 三種模式在評估情境上準確度幾乎相同，98% / 98% / 100%，rag 最快，見 `docs/EVAL_MODES.md`）；網頁介面用純 HTML + JavaScript（不用 Jinja2 / HTMX）；決策紀錄要所有參與者確認後才存檔；資料庫新欄位在啟動時自動補上。
**What the mainly change/improve** : 完整版 MVP：AI 問答、評估工具、決策紀錄、seed 腳本
**Led by:** @boanhsu1213

## 2026-11-21 — Code steward 審閱：PR #11
**What:** TTT426 以 code steward 身分審閱 [#11](https://github.com/TTT426/Group16/pull/11)
**Outcome**：approved
**What the mainly change/improve** : 完整版 MVP 功能串接、修關於 System Prompt 的穩定性問題
**More comment** : should use PR templatement and avoid plug in too much infomation in a same  
**Led by:** @boanhsu1213

## 2026-11-21 — Connect tools from the browser; separate seed repo (proposal, pending team confirmation)
**What:** New "Connect tools" page (`/connect`). GitHub is set up in three steps (sign in → choose a repo → import), and the page writes the settings to `.env`, so nobody edits it by hand. Sign-in options: OAuth device flow (needs one GitHub OAuth App registered by the team; `GITHUB_CLIENT_ID` is public), the existing `gh` CLI login, or a fine-grained token. These routes only accept localhost requests, refuse cross-site requests, and never send tokens to the browser. GitHub document ids now include the repo (`owner/repo#issue:1`). The seed script writes to a new `SEED_GITHUB_REPO`; `GITHUB_REPO` is only read, and seeding refuses to run when the two are the same.
**Why:** Connecting real tools meant editing `.env` and working out token permissions by hand, which is too hard for new members. `GITHUB_REPO` meant both "the repo to read" and "the empty test repo the seed script writes into", so after connecting the team's real repo, seeding would have written fake content into it (including commits to main). GitHub items from different repos with the same number overwrote each other.
**What the mainly change/improve** : Connect tools page (GitHub), separate seed repo
**Led by:** @gdpps1028

## 2026-11-22 — Code steward 審閱：PR #13

**What:** TTT426 以 code steward 身分審閱 [#13](https://github.com/TTT426/Group16/pull/13) 

**Outcome:** approved 

**What the mainly change/improve:** 
1. Add more readable GUI interface 
2. Connect GitHub from the browser

**Led by:** @gdpps1028 

## 2026-11-22 — Follow-up to the PR #11 steward review

**What:** Correction and follow-up to the 2026-11-21 entry. TTT426 reviewed #11 as code steward and merged it. The feedback was first left as a comment; the formal GitHub approval was submitted afterwards, on 2026-11-22. After the merge, @hojinpongcs09-lab reported that `test_config_lists_modes_and_scenarios` fails on a clean checkout (`/api/config` uses `get_session_factory()` instead of the injected session). \
**Follow-up:** : Just record this bug now. \
**Process note (proposal, pending team confirmation):** Submit reviews as formal GitHub reviews before merging, and run the tests on a clean checkout before approving. \
**Led by:** @TTT426
