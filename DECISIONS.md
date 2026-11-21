# Decisions Log

## 2026-09-21 — Initial code steward
**What:** Nathan is the initial code steward for the team.
**Why:** Volunteered for this part.

## 2026-11-21 — MVP 技術選型（提案，待組內確認）
**What:** 後端用 Python + FastAPI；資料庫用 PostgreSQL 16 + pgvector + pg_trgm；embedding 預設用本地的 `BAAI/bge-m3`；前端用 Jinja2 + HTMX。
**Why:** 全組只需要會 Python；一個資料庫就能放文件、向量、決策和評估紀錄；bge-m3 支援中英文、免費，而且訂閱制 LLM 本來就不提供 embedding。
**Status:** 提案。依 Team Charter 由組內討論並投票確認。詳見 `docs/PROJECT_PLAN.md`。

## 2026-11-21 — LLM 介面抽象化、可以切換（提案，待組內確認）
**What:** 所有 LLM 呼叫都透過 `LLMProvider` 介面，用 `LLM_PROVIDER` 環境變數切換：`claude_cli`（Claude 訂閱）、`anthropic_api`（API 按量計費）、`fake`（離線開發 / 測試）；`openai_api`、`ollama`、`codex_cli` 留到 M5。
**Why:** 開發和 demo 可以用訂閱額度省錢；正式評估如果有額度或使用條款上的疑慮，可以直接改用 API，程式不用改。
**Status:** 提案。

## 2026-11-21 — M2 檢索與連接器實作方式（提案，待組內確認）
**What:** 關鍵字搜尋改用 Python 內的 BM25（中文用單字＋雙字詞切分），不用 `pg_trgm`；Discord 改用 REST API，不用 `discord.py`；加入 `ruff` 當 linter；DB 測試用 `pgserver` 內嵌 Postgres。
**Why:** `pg_trgm` 對中文不可靠；只讀歷史訊息不需要 gateway 連線；AI_GUIDELINES 要求通過 linter 才能合併，但原本沒有 linter；組員不一定有 Docker。
**Status:** 提案。細節見 `docs/PROJECT_PLAN.md` §9。

## 2026-11-21 — 降低外部依賴：SQLite、fastembed、一鍵啟動（提案，待組內確認）
**What:** 資料庫只用 SQLite 檔案（不保留 PostgreSQL 選項，不再需要 pgvector / Docker）；embedding 改成 fastembed + `BAAI/bge-small-zh-v1.5`（不需要 torch，裝不起來時自動退回 hashing），移除 sentence-transformers；`LLM_PROVIDER` 預設 `auto`；新增 `start.bat` / `start.sh` 一鍵啟動。這筆取代前面「PostgreSQL + pgvector、bge-m3」的提案內容。
**Why:** 組員的電腦環境不同（沒有 Docker、Windows 中文路徑、Mac / Linux），原本的依賴容易裝不起來；在兩個評估情境的檢索測試中，小模型（命中 21/24）比 bge-m3（17/24）好，而且快約 10 倍。
**Status:** 提案。細節見 `docs/PROJECT_PLAN.md` §10。
