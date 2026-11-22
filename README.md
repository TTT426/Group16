# Group16 — Context Engine

跨工具 AI 整合層：剛接手專案的工程師可以一次問遍 GitHub、Notion、Discord 裡的專案資訊。AI 回答的**每一段都附原始來源連結**，查證過的結論可以存成團隊的決策紀錄。

- 規劃與里程碑：[docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md)
- 問答模式比較（rag / full / agent）：[docs/EVAL_MODES.md](docs/EVAL_MODES.md)
- 決策紀錄：[DECISIONS.md](DECISIONS.md)
- AI 使用規範與互動紀錄：[AI_GUIDELINES.md](AI_GUIDELINES.md)、[docs/prompts/](docs/prompts/)

## 一鍵啟動

需要事先安裝：
- **Python 3.11 以上**（[下載](https://www.python.org/downloads/)；Windows 安裝時請勾選「Add python.exe to PATH」）
- **Claude Code CLI**，並執行一次 `claude` 登入（AI 回答使用你的 Claude 訂閱額度）。沒有安裝的話，整合搜尋還是能用

| 系統 | 啟動方式 |
|---|---|
| Windows | 雙擊 `start.bat` |
| macOS / Linux | 終端機執行 `./start.sh`（或 `sh start.sh`） |

腳本會自動：建立虛擬環境 → 安裝套件 → 建立 `.env` → 建立資料庫並匯入兩個評估情境 → 啟動 → 開啟瀏覽器。
第一次需要網路，大約幾分鐘（套件加上約 90 MB 的 embedding 模型）；之後再啟動只要幾秒。按 `Ctrl+C` 停止。

選項（Windows 寫成 `start.bat --port 9000`，macOS / Linux 寫成 `./start.sh --port 9000`）：

| 選項 | 用途 |
|---|---|
| `--port 9000` | 指定 port（預設 8001；被佔用時會自動換下一個） |
| `--minimal` | 最精簡安裝：不下載 embedding 模型，搜尋只比對字詞 |
| `--reset` | 刪除本機資料庫，重新匯入情境 |
| `--no-browser` | 不自動開啟瀏覽器 |
| `--reload` | 改程式碼時自動重啟（開發用） |

## 怎麼用

### 查詢（`/`）
- **AI 回答**：輸入問題，Claude 會整理答案，每一段後面的編號連到右側的來源卡片，點開就是原始的 GitHub、Notion 或 Discord 頁面。沒有來源支持的段落會被標出來；資料不足時會明講，並建議可以問誰
- **整合搜尋**：不經過 AI，直接列出三個工具裡的相關內容（評估時的對照組）

AI 回答有三種模式，用 `.env` 的 `QA_MODE` 設定，比較結果見 [docs/EVAL_MODES.md](docs/EVAL_MODES.md)：

| 模式 | 做法 |
|---|---|
| `rag` | 混合搜尋（關鍵字 + 語意）找出相關段落，再交給 Claude 整理 |
| `full` | 整個專案的內容都放進 Claude 的 context（專案太大時自動改用 rag） |
| `agent` | 專案匯出成 markdown 資料夾，Claude 用唯讀的 Grep / Glob / Read 自己搜尋 |

### 評估（`/observer`）
對應 CP1 的結構化觀察：
1. 每位受試者的每一輪各建立一個場次（對照輪，或工具輪的 AI 回答 / 整合搜尋）
2. 按「開始計時」，把頁面上的連結給受試者，他們的查詢和點開的來源會自動記錄
3. 受試者問資深成員時按「+1」；完成後按「結束」，依答案 key 給分
4. 在「標註 AI 引用」逐一確認來源是否真的支持回答（門檻：至少 80%）
5. 「下載 CSV」取得每個場次的時間、詢問次數、得分、是否點開來源、引用支持率

### 決策紀錄（`/decisions`）
在 AI 回答下方按「建立決策草稿」，Claude 會起草；所有參與者在決策紀錄頁按下確認後才會存檔，之後的查詢也搜得到它。草稿修改後，之前的確認會失效。可以匯出成 `DECISIONS.md` 的格式。

### Connect tools (`/connect`)
Connect the team's own tools so that search and AI answers use your real data (until then, they use the built-in practice scenario). No need to edit `.env` by hand; every step explains what is needed and shows illustrations.

**GitHub**
1. **Sign in to GitHub**: "Sign in with GitHub" (type a short code on github.com), the GitHub CLI login already on this computer (`gh`), or a personal access token. Public repos also work without signing in.
2. **Choose a repo**: pick one from your repo list, or paste the URL of any repo.
3. **Import**: reads issues, pull requests (with comments and reviews) and Markdown files. Press "re-import" later to update.

**Notion**
1. **Create a connection**: the page opens Notion's Developer portal; a workspace owner creates an internal connection (authentication method *API token*) and pastes its API token.
2. **Choose pages**: share the team's pages with the connection (its *Content access* tab, or *••• → Connections* on a page). The page lists what the connection can see.
3. **Import**: reads every shared page, including sub-pages and database entries.

Settings are saved to `.env` and apply immediately. Discord is coming soon.

> "Sign in with GitHub" needs the client id of a GitHub OAuth App (`GITHUB_CLIENT_ID`, public). Until it is set, that button is hidden and the other two sign-in options work as usual.

## 建立評估用的真實工作區
> The seed script **writes** the scenarios into a separate test workspace, never into the tools the app reads:
> - GitHub: `SEED_GITHUB_REPO`, an empty test repo (it creates issues, merges pull requests and commits files), not `GITHUB_REPO`.
> - Notion: `SEED_NOTION_TOKEN`, a separate connection that can see `NOTION_PARENT_PAGE_ID`, not `NOTION_TOKEN` (everything the app's connection can see is imported).
>
> Seeding refuses to run when a seed setting equals the one the app reads.

評估的對照輪需要受試者在真的 GitHub、Notion、Discord 上找資料。先在 `.env` 填好 token（設定方式見 `.env.example` 的註解），然後：

```bash
python scripts/seed_workspace/seed.py --dry-run               # 先看會建立什麼
python scripts/seed_workspace/seed.py github notion discord   # 建立（可中斷後重跑，不會重複）
python scripts/ingest.py --reset --seed-workspace github notion discord   # index the seeded test workspace
```

## 開發

```bash
.venv\Scripts\activate              # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,embeddings]"

pytest                              # 測試（暫存 SQLite 檔，LLM 用 fake，不需要任何服務）
ruff check .                        # lint（合併前必須通過）
```

- `GROUP16_TEST_EMBEDDER=fastembed pytest -k real_embedder`：用真實的 embedding 模型測檢索
- `python scripts/eval_modes.py`：用真的 Claude 比較三種問答模式，結果寫到 `docs/EVAL_MODES.md`（會用到訂閱額度）
- `python -m app.llm "你好"`：測試 Claude CLI 是否可用

### API
| 路徑 | 用途 |
|---|---|
| `POST /ask` | AI 回答（附來源） |
| `GET /search?q=` | 整合搜尋（不經過 AI） |
| `GET /go?url=` | 開啟來源並記錄點擊（只允許已索引的網址） |
| `/api/eval/...` | 評估場次、引用標註、`export.csv` |
| `/api/decisions/...` | 決策草稿、修改、確認、`export.md` |
| `POST /ingest` | 從真實工具匯入 |
| `/connect`, `/api/github/...`, `/api/notion/...` | Connect tools: sign-in, choices, import (localhost only) |
| `GET /api/config`、`GET /health` | 目前設定 |

完整說明在 `/docs`。

### 相容性設計
- 資料庫只用 SQLite（`data/group16.db` 一個檔案）；新版本增加的欄位會在啟動時自動補上
- Embedding 預設用 fastembed（不需要 torch）；裝不起來或沒有網路時，自動退回不需要任何套件的 hashing
- 網頁介面是純 HTML + JavaScript，不需要 Node.js 或任何前端套件
