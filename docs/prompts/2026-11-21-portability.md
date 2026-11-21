# 2026-11-21 — 一鍵啟動與降低外部依賴

依 [AI_GUIDELINES.md](../../AI_GUIDELINES.md) §2 記錄。

## Tool / Model
- Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code（VS Code extension）

## Prompts（使用者原文）
1. 「我要怎麼執行他 並且告訴我 還需要甚麼」
   - AI 在本機實際跑過一次（用 pgserver 附的 Postgres，因為這台電腦沒有 Docker），回報執行步驟與待辦事項；這一輪沒有修改 repo 的程式碼
2. 「你寫一件啟動的bat 然後看能不能減少外部依賴 讓不同裝置的兼容性高」
3. 「刪除不需要的檔案 並且提交PR:減少外部依賴」，過程中補充：「資料庫的部分不要用選用」
   - 依此移除 PostgreSQL 選項（只用 SQLite），並刪除 `docker-compose.yml`、`scripts/init_db.py`、sentence-transformers 的 embedder

## AI 的回應 / 建議（摘要）
| 建議 | 結果 |
|---|---|
| 資料庫改成 SQLite，向量存成 float32 bytes、在記憶體內計算相似度。原本建議保留 PostgreSQL 當選項 | **Modified**：使用者要求資料庫不要做成選用 → 只用 SQLite |
| embedding 改用 fastembed + `BAAI/bge-small-zh-v1.5`；先用兩個評估情境的 24 題比較 4 個模型再決定（bge-small-zh 21/24、multilingual-MiniLM 18/24、jina-v2-base-zh 17/24、bge-m3 17/24） | 待 review |
| 每個向量記錄 `embedding_model`；換模型時自動重算不一致的部分（`reembed_stale`） | 待 review |
| `LLM_PROVIDER=auto`、`EMBEDDING_PROVIDER=auto` | 待 review |
| `start.bat` / `start.sh` + `scripts/dev.py`（只用標準函式庫）；`.gitattributes` 固定換行字元 | 待 review |
| 核心依賴縮減為 7 個套件，其他改成 extras | 待 review |

架構相關的部分已寫進 `DECISIONS.md`（提案）與 `docs/PROJECT_PLAN.md` §10。

## 驗證（AI 自己做的）
- `pytest`：全部通過（暫存 SQLite 檔）
- `GROUP16_TEST_EMBEDDER=fastembed pytest -k real_embedder`：通過，兩個情境的答案來源都在前 8 筆
- `ruff check .`：通過
- 模擬新電腦：把專案複製到含中文的路徑（沒有 `.venv`、`.env`、資料庫），執行 `start.bat`：自動找到 Python 3.13、建立 venv、裝好套件（含 fastembed）。結果寫在 PR 描述
- 測試中發現並修正：退回離線模式的訊息原本假設是網路問題，改成照實說明
- **尚未驗證**：`start.sh` 只在 Windows 上檢查過語法（`sh -n`），還沒在 macOS / Linux 上實際跑過

## 人工驗證 / 修改（reviewer 填寫）
- [ ] reviewer 檢查過變更的檔案
- [ ] 在另一台電腦（最好是 macOS）跑過 `start.sh`
- [ ] `DECISIONS.md` 的提案經組內討論確認
- [ ] 最終結果：Accepted / Modified / Rejected —
