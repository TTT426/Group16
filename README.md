# Group16 — Context Engine

跨工具 AI 整合層：新人可以一次問遍 GitHub / Notion / Discord 裡的專案資訊，AI 回答時**每一句都附原始來源連結**；確認過的結論會存成 Decision log。

- 規劃與里程碑：[docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md)
- 決策紀錄：[DECISIONS.md](DECISIONS.md)
- AI 使用規範與 prompt 紀錄：[AI_GUIDELINES.md](AI_GUIDELINES.md)、[docs/prompts/](docs/prompts/)

## 快速開始

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # 視需要修改

pytest                        # 執行測試（DB 測試會自動啟動內嵌 PostgreSQL，不需要 Docker）
ruff check .                  # lint（合併前必須通過）
```

真實語意搜尋需要 embedding 模型：`pip install -e ".[embeddings]"`（第一次使用會下載 bge-m3，約 2 GB）。
沒有安裝的話，可以在 `.env` 設 `EMBEDDING_PROVIDER=hashing`（只比對字詞）。

### 資料庫（需要 Docker）
```bash
docker compose up -d db
python scripts/init_db.py
```

### 匯入資料
```bash
# 離線：把模擬工作區情境直接匯入（不需要任何 token）
python scripts/ingest.py --init-db --scenario "scripts/seed_workspace/scenario_*.yaml"

# 真實工具（先在 .env 填好 token，設定方式見 .env.example 的註解）
python scripts/ingest.py github notion discord
```

### 啟動 API
```bash
uvicorn app.main:app --reload --app-dir backend
# http://127.0.0.1:8000/health
# http://127.0.0.1:8000/search?q=付款失敗的原因      ← 純搜尋模式（評估用的對照組）
# POST /ingest {"sources": ["github", "notion", "discord"]}
```

## LLM provider（用 `LLM_PROVIDER` 切換）

| 值 | 計費方式 | 需要什麼 |
|---|---|---|
| `claude_cli` | Claude Pro/Max 訂閱額度 | 安裝 Claude Code 並執行 `claude` 登入一次 |
| `anthropic_api` | API 按量計費 | `ANTHROPIC_API_KEY` |
| `fake` | 免費 | 不需要，離線開發 / 測試用 |

快速測試目前的 provider：
```bash
cd backend
python -m app.llm "用一句話說明什麼是 Decision log"
python -m app.llm "hello" --provider fake
```

> `claude_cli` 預設會在子程序中移除 `ANTHROPIC_API_KEY`，確保走訂閱額度。訂閱有用量上限，也以個人使用為主；正式評估如果量比較大，請改用 `anthropic_api`。

## 模擬工作區
評估用的兩個情境放在 [scripts/seed_workspace/](scripts/seed_workspace/)：付款失敗、確認信重複寄送。正確答案刻意分散在三個工具。
