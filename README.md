# Group16 — Context Engine

跨工具 AI 整合層：新人可以一次問遍 GitHub / Notion / Discord 裡的專案資訊，AI 回答時**每一句都附原始來源連結**；確認過的結論會存成 Decision log。

- 規劃與里程碑：[docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md)
- 決策紀錄：[DECISIONS.md](DECISIONS.md)
- AI 使用規範與互動紀錄：[AI_GUIDELINES.md](AI_GUIDELINES.md)、[docs/prompts/](docs/prompts/)

## 一鍵啟動

唯一需要事先安裝的是 **Python 3.11 以上**（[下載](https://www.python.org/downloads/)；Windows 安裝時請勾選「Add python.exe to PATH」）。
不需要 Docker，也不需要另外安裝資料庫。

| 系統 | 啟動方式 |
|---|---|
| Windows | 雙擊 `start.bat` |
| macOS / Linux | 終端機執行 `./start.sh`（或 `sh start.sh`） |

腳本會自動：建立虛擬環境 → 安裝套件 → 建立 `.env` → 建立資料庫並匯入兩個評估情境 → 啟動 API → 開啟瀏覽器到 `/docs`。
第一次需要網路，會花幾分鐘（套件加上約 90 MB 的 embedding 模型）；之後再啟動只要幾秒。

在 `/docs` 頁面試 `GET /search`，例如輸入「付款失敗的原因是什麼」，就會看到跨三個工具的搜尋結果與原始連結。按 `Ctrl+C` 停止。

常用選項（Windows 寫成 `start.bat --port 9000`，macOS / Linux 寫成 `./start.sh --port 9000`）：

| 選項 | 用途 |
|---|---|
| `--port 9000` | 指定 port（預設 8001；被佔用時會自動換下一個） |
| `--dev` | 同時安裝 pytest、ruff 等開發工具；可與 `--minimal` 搭配 |
| `--minimal` | 最精簡安裝：不下載 embedding 模型，搜尋只比對字詞 |
| `--reset` | 刪除本機資料庫，重新匯入情境 |
| `--no-browser` | 不自動開啟瀏覽器 |
| `--reload` | 改程式碼時自動重啟（開發用） |

### 相容性設計
- **資料庫**：只用 SQLite（Python 內建），整個資料庫就是 `data/group16.db` 一個檔案；要搬資料或重來，複製或刪除這個檔案即可
- **Embedding**：預設用 fastembed（ONNX，不需要 torch）。如果這台電腦裝不起來，或下載模型時沒有網路，會自動退回不需要任何套件的 hashing 模式，程式照樣能跑
- **LLM**：`LLM_PROVIDER=auto`。有裝 Claude Code CLI 就用它（訂閱額度），有 `ANTHROPIC_API_KEY` 就用 API，否則用離線的 fake
- 換電腦、換模型都不用手動處理：資料庫會記錄每個向量是哪個模型算的，模型不同時啟動腳本會自動重新計算

## 開發

macOS / Linux 可直接準備開發環境並啟動：

```bash
./start.sh --dev
# 不需要語意模型時：./start.sh --dev --minimal
```

一般啟動不安裝測試工具。執行上方命令後，可在另一個終端機執行：

```bash
.venv/bin/python -m pytest -q -rs
.venv/bin/python -m ruff check .
# 包含真實 embedding 模型的測試（需安裝 embeddings 並可取得模型）
GROUP16_TEST_EMBEDDER=fastembed .venv/bin/python -m pytest -q -rs
```

`--dev` 也支援 Windows 的 `start.bat`。切換安裝選項會更新套件；它不會移除先前已安裝的選用套件。

手動安裝方式：

```bash
# 啟動腳本會建立 .venv；之後可以直接用它
.venv\Scripts\activate              # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,embeddings]"

pytest                              # 測試（用暫存的 SQLite 檔，不需要任何服務）
ruff check .                        # lint（合併前必須通過）
```

選用的測試：
- `GROUP16_TEST_EMBEDDER=fastembed pytest -k real_embedder`：用真實的 embedding 模型測檢索

### 匯入資料
```bash
# 離線：把模擬工作區情境匯入（啟動腳本第一次會自動做）
python scripts/ingest.py --init-db --scenario "scripts/seed_workspace/scenario_*.yaml"

# 真實工具（先在 .env 填好 token，設定方式見 .env.example 的註解）
python scripts/ingest.py github notion discord
```

### API
- `GET /search?q=...`：跨工具整合搜尋，不經過 AI（評估時的對照組）
- `POST /ingest {"sources": ["github", "notion", "discord"]}`：從真實工具匯入
- `GET /health`：目前使用的 LLM provider 與 embedding 模型

### LLM provider（用 `LLM_PROVIDER` 切換）

| 值 | 計費方式 | 需要什麼 |
|---|---|---|
| `auto`（預設） | 依序嘗試下面三種 | — |
| `claude_cli` | Claude Pro/Max 訂閱額度 | 安裝 Claude Code 並執行 `claude` 登入一次 |
| `anthropic_api` | API 按量計費 | `ANTHROPIC_API_KEY`，並 `pip install -e ".[anthropic]"` |
| `fake` | 免費 | 不需要，離線開發 / 測試用 |

測試目前的 provider：`python -m app.llm "用一句話說明什麼是 Decision log"`

> `claude_cli` 預設會在子程序中移除 `ANTHROPIC_API_KEY`，確保走訂閱額度。訂閱有用量上限，也以個人使用為主；正式評估如果量比較大，請改用 `anthropic_api`。

## 模擬工作區
評估用的兩個情境放在 [scripts/seed_workspace/](scripts/seed_workspace/)：付款失敗、確認信重複寄送。正確答案刻意分散在三個工具。
