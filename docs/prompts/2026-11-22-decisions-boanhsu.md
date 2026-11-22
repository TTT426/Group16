# DECISIONS.md：補齊 @boanhsu1213 的紀錄

- **Tool / Model**：Claude Code（Claude Opus 5.5）
- **Prompt**（摘要）：「decision 把 boanhsu 的部分照這些格式寫進去，你可以挖 branch 中我的東西，並且發 PR」。「這些格式」是使用者在本機 DECISIONS.md 的修改：steward 審閱條目加上 `**PR author**`，`Led by` 改成審閱者，每行結尾用 ` \` 換行。
- **回應 / 建議**：
  - 檢查 `fff-initial-build`（#9）、`fff-reduce-deps`（#10）、`fff-full-mvp`（#11）、`fff-test`、`fff-decisions-pr12`（#17，已關閉）、`fff-pr-process`（#18，已關閉）。
  - #9、#10 的四筆提案補上 `What the mainly change/improve` 和 `Led by`，原有內容不變。
  - 從 `fff-decisions-pr12` 取出 PR #12 的審閱紀錄，改成新格式；新增沒有記錄過的 PR #19 審閱紀錄。
  - 從 `fff-pr-process` 取出 PR 處理順序提案；因為 #18 已關閉，條目直接寫出規則內容，不再引用 AI_GUIDELINES Section 4。
  - `fff-test` 只有九月的課堂草稿（已被 #8 取代），沒有要記錄的決策。
- **驗證 / 修改**：PR、review、merge 的編號與 commit 用 GitHub API 和 `git log` 核對；使用者本機的格式修改原樣保留。
- **結果**：Accepted（待組員審閱）。
