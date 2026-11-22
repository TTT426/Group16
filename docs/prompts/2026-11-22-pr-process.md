# PR 處理順序規則

- **Tool / Model**：Claude Code（Claude Opus 5.5）
- **Prompt**（摘要）：審閱並合併 PR #12 後，使用者問「整串 PR 是不是都有問題，先後順序很奇怪」，接著要求「幫我寫進專案處理規則裡面，並且你以後在執行這個專案時都要遵守」。
- **回應 / 建議**：用 GitHub API 整理 #9–#17 的開啟、review、合併時間線，找出四個問題：先合併後審閱（#9、#11）、AI 核准後立刻合併（#14、#15、#12）、DECISIONS.md 紀錄和 PR 分開進 main（直接推 main、#17）、PR 堆疊與重複 PR（#16）。建議固定順序：開分支 → 作者在乾淨環境測試 → steward 審閱並重跑測試 → 紀錄 commit 進同一個 PR → Approve → 合併。
- **驗證 / 修改**：時間線由 GitHub API 的 `created_at`、`merged_at`、review `submitted_at` 核對。規則寫進 `AI_GUIDELINES.md` Section 4，並在 `DECISIONS.md` 記為提案，待組內確認。
- **結果**：Accepted（作為提案；組內確認前，Claude Code 在這個專案中先依此規則執行）。
