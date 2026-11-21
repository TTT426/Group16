# Group16 專案建構規劃（課程 MVP）

## Context
CP1 定義的產品是一個「AI 整合層」：把散落在 GitHub / Notion / Discord（商用情境是 Slack / Trac）的專案資訊收集起來，讓新人提問。AI 負責檢索、摘要並**附上原始來源連結**；新人與資深工程師都確認後，結論才會存成 **Decision log**，並回頭成為 AI 的資料來源。
目前 repo 只有文件，沒有程式碼。這份規劃的目標是：**在 Week 13–14 評估開始前，做出能跑完 PDF 評估流程的 MVP**。
已確定的選擇：
- 後端用 **Python + FastAPI**
- **LLM 介面要抽象化、可以切換**，而且要能走**訂閱制額度**（不一定要用 API key 按量計費）
- 範圍**只做課程 MVP**

---

## 1. MVP 功能範圍（直接對應 PDF）
| # | 功能 | 對應 PDF 的哪一段 | 優先級 |
|---|---|---|---|
| F1 | 連接器：GitHub（issues / PRs / PR 留言 / markdown）、Notion（頁面）、Discord（頻道與討論串） | 模擬工作區把資訊分散在三個工具 | P0 |
| F2 | 整合檢索（關鍵字＋語意的混合搜尋） | AI 整合層的 Retrieve | P0 |
| F3 | AI 問答：摘要＋每一句都附來源連結；找不到就明講，並建議該問哪位成員 | Human-AI boundary | P0 |
| F4 | **純搜尋模式**（只有整合搜尋、不用 AI），用開關切換 | 「關鍵字搜尋 vs AI 問答」的對照實驗 | P0 |
| F5 | 評估紀錄：計時、提問紀錄、來源連結點擊、匯出 CSV | 量測時間、是否點來源連結 | P0 |
| F6 | Decision log：從答案產生決策草稿 → 參與者雙方確認 → 存檔並重新索引 | Decision log / Feeds back | P1 |
| F7 | 模擬工作區的資料種子腳本（兩個難度相近的情境，例如「付款失敗 bug」） | 模擬專案工作區 | P0 |

不在 MVP 範圍內：Slack / Trac 連接器、多租戶、SSO、依原系統權限過濾。連接器介面會預留，之後要加不必改架構。

## 2. 系統架構
```
 GitHub API ─┐
 Notion API ─┼─> connectors ─> normalize ─> chunk ─> embed ─> SQLite（單一檔案）
 Discord Bot ┘                                               (documents / chunks / decisions / events)
                                                                     │
 Browser (Jinja2 + HTMX) ─> FastAPI ─> retrieval(hybrid + 連結展開) ─┘
                                 │
                                 └─> qa service ─> LLMProvider（可切換）
                                         └─> citation 驗證 ─> 回傳答案＋來源
```

**技術選型**
- **DB**：只用 SQLite 檔案（Python 內建，不需要安裝；預設 `data/group16.db`）。向量用 float32 bytes 存，在記憶體內計算相似度，不需要 pgvector。用 SQLAlchemy 2 管理 schema（schema 穩定後再導入 Alembic）
- **Embedding**：同樣抽象化，預設用 fastembed（ONNX，不需要 torch）+ `BAAI/bge-small-zh-v1.5`（約 90 MB、支援中英）；也可以換成 sentence-transformers 的大模型；什麼都沒裝時退回 hashing。訂閱制 LLM 本來就沒有 embedding 可用
- **前端**：FastAPI + Jinja2 + HTMX，不用另外建前端 build，全組都寫 Python 就好
- **其他**：`httpx`（GitHub / Notion / Discord 都用 REST API）、`pydantic-settings`（設定）、`pytest`、`ruff`（lint）

## 3. LLM 抽象層（重點）
`backend/app/llm/base.py`
```python
class LLMResult(BaseModel):
    text: str; provider: str; model: str
    input_tokens: int | None; output_tokens: int | None; latency_ms: int

class LLMProvider(Protocol):
    name: str
    async def generate(self, system: str, user: str, *, max_tokens: int = 4000) -> LLMResult: ...
```
`factory.get_provider(settings)` 依環境變數 `LLM_PROVIDER` 決定用哪一種實作：

| provider | 計費方式 | 實作方式 |
|---|---|---|
| `anthropic_api` | API 按量計費 | 官方 `anthropic` SDK，模型預設 `claude-opus-5-5`（用 `LLM_MODEL` 可以改） |
| `openai_api` | API 按量計費 | 官方 `openai` SDK |
| `ollama` | 免費 / 本地 | 用 HTTP 呼叫本機 Ollama |
| `claude_cli` | **Claude Pro/Max 訂閱** | 用 subprocess 執行已登入的 Claude Code CLI：`claude -p --output-format json`，prompt 從 stdin 傳入，並關掉內建工具 |
| `codex_cli` | **ChatGPT 訂閱** | 用 subprocess 執行已登入的 `codex exec` |

CLI 類 provider 的共同處理：設定逾時、限制同時執行數（`asyncio.Semaphore`）、讀不到 JSON 就重試一次、記錄延遲。
⚠️ **注意**：訂閱制額度有用量上限，使用條款也是以個人使用為主。適合開發和組內 demo；正式評估時如果擔心額度或條款問題，用同一個介面切換成 API 即可，程式不用改。

**問答怎麼產生答案（`qa/service.py`）**
1. 檢索 top-k 段落，編號成 `[S1]…[Sn]`，每段附上來源、標題、作者、時間
2. Prompt 要求模型輸出 JSON：`{"sections":[{"text":…,"sources":["S1","S3"]}],"unanswerable":bool,"confidence":"high|med|low"}`
   - 不依賴各家的 structured output 功能，CLI provider 也能用；拿到後用 pydantic 驗證
3. `qa/citations.py` 檢查：引用的 S 編號必須真的在檢索結果裡 → 轉成原始 URL；沒有引用的段落標示「未經來源支持」
4. 如果 `unanswerable`：從檢索結果裡最常出現的作者推薦「建議詢問誰」（AI 只給建議，要不要問由人決定）

## 4. 檢索設計（`retrieval/`）
- **混合搜尋**：BM25 關鍵字分數（中文用單字＋雙字詞切分，在 Python 記憶體內計算）+ embedding cosine 相似度（記憶體內計算，有 numpy 時用 numpy），用 RRF 合併；每個有候選結果的來源至少保留 1 筆，避免結果全部來自同一個工具
- **跨工具連結展開（`linker.py`）**：抓出文字中的 `#123`、GitHub URL、Notion URL，把被引用的文件也帶進來。例如 Discord 討論串貼了 PR 連結 → PR 會一起被檢索到。這是「整合」最有價值的地方
- **切塊**：Discord 依討論串或時間窗合併成一塊；GitHub PR = 描述＋留言；Notion 依標題分段

## 5. 資料模型（重點欄位）
- `documents(id, source, external_id, url, title, author, created_at, parent_id, raw_json)`
- `chunks(id, document_id, ordinal, text, embedding（float32 bytes）, embedding_model)`
- `answers(id, session_id, question, mode, provider, model, sections_json, latency_ms)`
- `decisions(id, title, context, decision, rationale, source_urls, status[pending|confirmed], created_by)` + `decision_confirmations(decision_id, participant)`
- `eval_sessions(id, pair_id, participant, role, round[baseline|tool], mode[ai|search], started_at, ended_at, senior_questions, score)`
- `events(id, session_id, type[query|answer|source_click|…], payload, ts)`：來源連結都經過 `/go/{citation_id}` 轉址，順便記錄點擊

## 6. 專案結構
```
backend/
  app/
    main.py  config.py
    connectors/  base.py github.py notion.py discord.py
    ingest/      normalize.py chunker.py pipeline.py
    embeddings/  base.py bge.py
    retrieval/   hybrid.py linker.py
    llm/         base.py factory.py anthropic_api.py openai_api.py ollama.py claude_cli.py codex_cli.py
    qa/          prompt.py service.py citations.py
    decisions/   service.py
    eval/        events.py export.py
    api/         ask.py search.py decisions.py ingest.py eval.py
    db/          models.py session.py
    web/templates/
  alembic/
  tests/
scripts/
  seed_workspace/   scenario_payment.yaml scenario_email.yaml seed_github.py seed_notion.py seed_discord.py
  run_golden.py     # 跑標準題組＋答案 key，比較各 provider
  label_citations.py # 人工標註「來源是否真的支持答案」，計算是否達 ≥80%
start.bat  start.sh  scripts/dev.py（一鍵啟動）  .env.example  pyproject.toml
```

## 7. 里程碑（以 Week 13 開始評估倒推；P0 優先，P1 有時間再做）
- **M1 骨架與資料**：DB schema、`LLMProvider` + `claude_cli` 與 `anthropic_api` 兩種實作、寫好情境 YAML 並 seed 到 GitHub / Notion / Discord
- **M2 匯入與檢索**：三個連接器 → 匯入 pipeline → 混合搜尋＋連結展開；`/search` 純搜尋模式能用
- **M3 問答**：`/ask` 帶引用的答案、引用驗證、「建議詢問誰」；前端問答頁＋來源轉址記錄；`run_golden.py`
- **M4 評估工具**：觀察者介面（開始 / 結束計時、記錄詢問資深工程師的次數、評分）、匯出 CSV；**找組內成員先試跑一次評估流程**
- **M5（P1）**：Decision log 雙方確認＋重新索引、其他 provider（openai / ollama / codex_cli）

每個里程碑都照 Team Charter 的 Definition of Done：開 PR、至少一位組員 review、測試通過、文件更新。技術選型要寫進 `DECISIONS.md`。

## 8. 驗證方式
- **單元測試（pytest）**：連接器用錄好的 API 回應 fixture 測試；citation 驗證（亂編的 S 編號要被擋下）；連結展開的 regex；用假的 `FakeProvider` 測試 provider 介面與 JSON 解析失敗後的重試
- **整合測試**：暫存 SQLite 檔 → seed 小型 fixture → `/ask` 回傳的每個來源 URL 都要真的存在於 documents 表
- **品質測試**：`python scripts/run_golden.py --provider claude_cli`，對照答案 key 計算正確率與引用支持率（目標 ≥80%）；切換 `--provider anthropic_api` 確認兩種 provider 都能跑通
- **端到端**：組內兩人照 PDF 流程跑一次 baseline 與工具兩輪，確認 CSV 裡有時間、詢問次數、來源點擊、分數


## 9. 實作時與原規劃不同的地方（M2）
| 原規劃 | 實際做法 | 原因 |
|---|---|---|
| 關鍵字搜尋用 `pg_trgm` | Python 內的 BM25，中文用單字＋雙字詞切分 | `pg_trgm` 是否把中文當成文字取決於資料庫的 locale（C locale 下會直接忽略中文），而且三字一組不適合中文詞；MVP 資料量只有幾百段，記憶體內計算就夠快，而且不依賴資料庫擴充 |
| Discord 用 `discord.py` | 直接呼叫 Discord REST API（httpx） | 只需要讀歷史訊息，不需要常駐的 gateway 連線；三個連接器用同一套 HTTP 與重試邏輯，也比較好用 mock 測試 |
| 測試需要 docker-compose 的 DB | 測試用暫存 SQLite 檔 | 組員不一定有 Docker（見 §10） |
| 先寫 seed 腳本再測連接器 | 新增 `ScenarioConnector`，直接把情境 YAML 當成文件匯入 | 沒有任何 token 也能跑完整的匯入→搜尋流程；seed 腳本（寫到真的平台）仍待完成 |

## 10. 降低外部依賴、提高跨裝置相容性
目標：任何一台有 Python 3.11+ 的電腦（Windows / macOS / Linux），雙擊 `start.bat` 或執行 `./start.sh` 就能跑起來。

| 原本 | 改成 | 原因 |
|---|---|---|
| PostgreSQL + pgvector（需要 Docker 或 pgserver） | 只用 SQLite 檔案，不保留 PostgreSQL 選項 | 不用安裝資料庫；pgserver 在 Windows 中文路徑會初始化失敗；MVP 資料量只有幾百段，記憶體內計算向量相似度就夠快 |
| sentence-transformers + bge-m3（torch 約 1 GB 以上、模型 2.2 GB） | fastembed + `BAAI/bge-small-zh-v1.5`（約 90 MB，不需要 torch）；移除 sentence-transformers | 安裝小很多、速度快約 10 倍；在兩個評估情境的 24 題檢索測試（只用向量、取前 5 名）中，答案來源命中 21/24，bge-m3 是 17/24 |
| 核心依賴含 anthropic、psycopg、pgvector、jinja2 | 核心只剩 fastapi、uvicorn、pydantic、pydantic-settings、sqlalchemy、httpx、pyyaml；extras 只剩 `embeddings`（fastembed）、`anthropic`、`dev` | 每個套件都是一個可能裝不起來的點 |
| `LLM_PROVIDER` 預設 `claude_cli` | 預設 `auto`（CLI → API key → fake） | 沒裝 Claude Code 的組員也能啟動 |
| 手動執行好幾個指令 | `start.bat` / `start.sh` + `scripts/dev.py`（只用標準函式庫） | 自動建 venv、安裝、建 `.env`、匯入情境、找空的 port、開瀏覽器；embedding 裝不起來或沒有網路時，自動退回 hashing |

刪除的檔案：`docker-compose.yml`（不再使用 PostgreSQL）、`scripts/init_db.py`（`ingest.py --init-db` 與 API 啟動時都會自動建表）、`backend/app/embeddings/st_model.py`（sentence-transformers）。

其他細節：每個向量都記錄是哪個模型算的（`chunks.embedding_model`），換模型時只會重新計算不一致的部分，不會把不同模型的向量混在一起比；`.gitattributes` 確保 `.bat` 是 CRLF、`.sh` 是 LF，在任何系統 clone 下來都能執行。

## 11. 完整版（M3–M5）實作狀態
| 里程碑 | 狀態 | 內容 |
|---|---|---|
| M1 骨架 | 完成 | 設定、資料庫、LLM 介面、評估情境 |
| M2 匯入與檢索 | 完成 | 三個連接器、混合搜尋、跨工具連結展開、`/search` |
| M3 AI 問答 | 完成 | `/ask` 三種模式（rag / full / agent）、引用檢查、「建議詢問誰」、網頁介面 `/` |
| M4 評估工具 | 完成 | 觀察者頁面 `/observer`：場次、計時、資深成員詢問次數、自動記錄查詢與來源點擊、引用標註（80% 門檻）、匯出 CSV |
| M5 決策紀錄 | 完成 | AI 起草 → 修改 → 所有參與者確認 → 存成文件並重新索引；匯出 DECISIONS.md 格式 |
| Seed 腳本 | 完成（只用 mock 測試） | `scripts/seed_workspace/seed.py`：兩階段寫入 GitHub / Notion / Discord，可中斷重跑 |

與原規劃不同的地方：
| 原規劃 | 實際做法 | 原因 |
|---|---|---|
| LLM 可切換：Claude CLI、Anthropic API、OpenAI、Ollama、Codex CLI | **只用 Claude CLI**（另有只給測試用的 `fake`） | 使用者決定只用目前的 Claude CLI，不保留其他選項 |
| 前端用 Jinja2 + HTMX | 純 HTML + JavaScript（ES modules），由 FastAPI 提供靜態檔 | 不增加任何依賴，也不需要 Node.js |
| Agent 模式自己寫工具迴圈 | 把專案匯出成 markdown 資料夾，讓 Claude Code 用唯讀的 Grep / Glob / Read 自己搜尋 | 一次 CLI 呼叫就能多步搜尋，不用自己維護工具協定；權限限制在唯讀工具與該資料夾 |
| `run_golden.py` | `scripts/eval_modes.py`：同時比較三種模式，Claude 依答案 key 評分 | 回答「完整記憶 / 直接搜尋 / RAG 哪個準」這個問題；結果在 `docs/EVAL_MODES.md` |
| `label_citations.py` | 引用標註做在觀察者頁面 | 評估時同一個畫面就能完成 |
| Alembic migration | 啟動時自動補上新欄位（`add_missing_columns`） | 只有 SQLite、欄位都是新增，夠用且不增加依賴 |
