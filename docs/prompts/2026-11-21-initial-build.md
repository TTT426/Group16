# 2026-11-21 — Initial build（規劃、M1 骨架、M2 連接器與檢索）

依 [AI_GUIDELINES.md](../../AI_GUIDELINES.md) §2 記錄。

## Tool / Model
- Claude Opus 5.5（`claude-opus-5-5`），透過 Claude Code（VS Code extension）以 agent 模式執行：讀寫檔案、安裝套件、執行測試與 lint、建立 PR
- 對應 PR：`initial build`

## Prompts（使用者原文，依時間順序）
1. 附上 `Group16_CP1.pdf`：「照著這個pdf 給我可商業化的規劃」
2. 「我要你規畫的是如何建構這個專案 不是找出如何變現」
   - AI 提出三個問題，使用者選擇：後端 Python + FastAPI；「要是可切換抽象出LLM介面 也要可以使用訂閱制用量的」；範圍「只做課程 MVP」
3. 「繼續做 M2 連接器 然後需要的東西你可以直接下載 然後確定全部測試完成就丟PR:initial build 要依照原本有的檔案的那些guideline去做」

## AI 的回應 / 建議（摘要）
| # | 回應 | 結果 |
|---|---|---|
| 1 | 產出一份商業化規劃（定價、GTM 等） | **Rejected**：使用者指出要的是建構規劃，沒有寫進 repo |
| 2 | `docs/PROJECT_PLAN.md`：MVP 範圍、架構、LLM 抽象層、檢索設計、資料模型、里程碑 | **Accepted**：使用者核准規劃；`DECISIONS.md` 中的技術選型仍標示「提案」，待組內確認 |
| 2 | M1：專案設定、`llm/`（`claude_cli` 訂閱制、`anthropic_api`、`fake`）、`db/` schema、兩個虛構的評估情境 YAML | 待 review |
| 3 | M2：GitHub / Notion / Discord 連接器（REST）、`ScenarioConnector`、chunker、匯入 pipeline、embedding（bge-m3 / hashing）、BM25 + pgvector 混合搜尋與跨工具連結展開、`/search`、`/ingest`、`scripts/ingest.py`、內嵌 Postgres 測試環境、`ruff` | 待 review |

AI 在實作時偏離原規劃的地方（BM25 取代 `pg_trgm`、Discord 改用 REST、新增 `ScenarioConnector`），以及原因，記在 `docs/PROJECT_PLAN.md` §9 和 `DECISIONS.md`（提案）。

## 驗證（目前都是 AI 自己做的，還沒有人工驗證）
- `pytest`：全部通過；DB 測試跑在內嵌 PostgreSQL + pgvector 上。另外用真實的 bge-m3 模型跑了檢索測試，結果寫在 PR 描述
- `ruff check .`：通過
- `claude_cli` provider 實際呼叫過 Claude Code CLI（用訂閱額度），確認 JSON 輸出格式；Anthropic SDK 的用法對照了官方 SDK 文件
- GitHub / Notion / Discord 的 API 用法，由 AI 對照官方文件逐條查核（AI_GUIDELINES §3.4），共 12 項：endpoint、欄位、分頁、rate limit 都正確。待確認：
  - 程式固定使用的 API 版本（GitHub `2022-11-28`、Notion `2022-06-28`）比文件上的最新版舊，需要在第一次接真實帳號時確認仍可使用
  - Notion `archived` 已被 `in_trash` 取代：程式兩個都有處理
- **尚未驗證**：連接器還沒有對真實的 GitHub / Notion / Discord 帳號跑過（只用 mock HTTP 測過）
- 沒有提供任何 secret 或個資給 AI（AI_GUIDELINES §3.5）：建立 PR 時 token 直接從 git credential manager 傳給 API，沒有出現在對話或檔案中

## 人工驗證 / 修改（reviewer 填寫）
- [ ] reviewer 檢查過變更的檔案
- [ ] prompt 作者以外的組員能說明實作內容（AI_GUIDELINES §3.3）
- [ ] `DECISIONS.md` 的提案經組內討論確認（或修改 / 否決）
- [ ] 最終結果：Accepted / Modified / Rejected —
