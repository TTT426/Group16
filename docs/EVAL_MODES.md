# 問答模式比較：rag / full / agent

- 執行時間：2026-11-21T21:30:56
- LLM：claude_cli（CLI default）；embedding：fastembed:BAAI/bge-small-zh-v1.5
- 題目：兩個評估情境各 3 題（完整任務題、只問原因、只問理由），每題每種模式各跑 1 次
- 要點涵蓋率：回答寫出了答案 key 中多少要點（由 Claude 依答案 key 評分）
- 來源命中率：情境的三個答案來源（Discord 討論串、GitHub PR、Notion 規格）有幾個被引用

| 模式 | 要點涵蓋率 | 來源命中率 | 矛盾 / 捏造 | 無來源段落 | 不存在的引用 | 平均回應時間 | 最慢 | LLM 呼叫數 | 給模型的來源數 | 失敗 |
|---|---|---|---|---|---|---|---|---|---|---|
| rag | 98% | 100% | 0 | 0 | 0 | 11.433 秒 | 14.8 秒 | 1 | 8.833 | 0 |
| full | 98% | 100% | 0 | 0 | 0 | 10.933 秒 | 14.6 秒 | 1 | 13 | 0 |
| agent | 100% | 100% | 0 | 0 | 0 | 20.76 秒 | 22.6 秒 | 1 | 13 | 1 |

## 每題結果

| 情境 | 題目 | 模式 | 涵蓋 | 來源 | 秒 | 評分說明 |
|---|---|---|---|---|---|---|
| duplicate-email | 找出「訂單確認信會重複寄送」的原因，並說明目前的 | rag | 100% | 100% | 10.9 | 七個要點都有涵蓋，也沒有和要點矛盾的內容。兩處細節不完整：重啟原因只寫了部署，沒提 OOM；回答說的是「設計文件」和「討 |
| duplicate-email | 找出「訂單確認信會重複寄送」的原因，並說明目前的 | full | 100% | 100% | 10.3 | 回答涵蓋全部 7 個要點，也沒有和要點矛盾的內容；只是沒寫出 OOM、Notion、Discord 這幾個來源細節，但不 |
| duplicate-email | 找出「訂單確認信會重複寄送」的原因，並說明目前的 | agent | 100% | 100% | 22.6 | 七個要點都有涵蓋，也沒有和要點矛盾的內容。只有兩處小缺漏：重啟原因只寫了部署，沒提到 OOM；設計文件也沒寫明是 Not |
| duplicate-email | 客人為什麼會收到兩封一樣的確認信？ | rag | 100% | 100% | 9.6 | 回答有寫到 worker 從 Redis Streams 讀訊息、先寄信再 XACK，也寫到重啟（部署）時還沒 ACK  |
| duplicate-email | 客人為什麼會收到兩封一樣的確認信？ | full | 100% | 100% | 10.4 | 回答涵蓋了三個要點：worker 從 Redis Streams 讀訊息、先寄信再 ACK；寄信後、ACK 前重啟會讓訊 |
| duplicate-email | 客人為什麼會收到兩封一樣的確認信？ | agent | 100% | 100% | 20.5 | 回答已寫出 worker 從 Redis Streams 讀訊息後先寄信再 ACK、重啟時訊息會被重新投遞而重複寄信，以 |
| duplicate-email | 為什麼不改用 Kafka 做到 exactly- | rag | 100% | 100% | 8.8 | 兩點都有涵蓋：回答提到設計文件規定 at-least-once、consumer 須自行做到 idempotent（沒寫 |
| duplicate-email | 為什麼不改用 Kafka 做到 exactly- | full | 100% | 100% | 8.0 | 兩個要點都有涵蓋：回答提到設計文件規定 at-least-once、consumer 要 idempotent，也提到  |
| duplicate-email | 為什麼不改用 Kafka 做到 exactly- | agent | 100% | 100% | 18.5 | 回答涵蓋了兩個要點：一是設計文件規定佇列為 at-least-once、consumer 須自行做到 idempoten |
| payment-failure | 找出「信用卡付款失敗」bug 的原因，並說明目前 | rag | 88% | 100% | 11.4 | 前 7 點都有涵蓋。第 8 點不算涵蓋：回答有說重試前先查狀態，也提到同一張訂單只會建立 1 筆交易，但沒有明確寫出這樣 |
| payment-failure | 找出「信用卡付款失敗」bug 的原因，並說明目前 | full | 88% | 100% | 10.7 | 回答涵蓋第 1 到第 7 點，也沒有矛盾。第 8 點只提到「重試 3 次只會建立 1 筆交易」，沒有明確說先查狀態是為了 |
| payment-failure | 找出「信用卡付款失敗」bug 的原因，並說明目前 | agent | 100% | 100% | 22.4 | 回答涵蓋全部 8 個要點：重試原因、key 會變、PayNow 風控、固定 key、先查狀態、規格依據、保留重試的理由， |
| payment-failure | 結帳時出現 PAYMENT_DUPLICATE  | rag | 100% | 100% | 14.8 | 三個要點回答都有寫到：v1.4 加了 axios-retry，逾時會重送 POST /checkout；key 用 or |
| payment-failure | 結帳時出現 PAYMENT_DUPLICATE  | full | 100% | 100% | 11.6 | 三點都有涵蓋：回答寫了 v1.4 前端逾時自動重送 POST /checkout，寫了 key 是 order_id + |
| payment-failure | 結帳時出現 PAYMENT_DUPLICATE  | agent | 失敗 | | 4.8 | LLMError: Claude CLI error (exit 1): The model's tool call c |
| payment-failure | 為什麼不直接把前端的自動重試拿掉就好？ | rag | 100% | 100% | 13.1 | 三點都有涵蓋：key 由 server 產生且每筆訂單固定、不拿掉重試是因為弱網使用者（PR #5 討論）、先查詢付款狀 |
| payment-failure | 為什麼不直接把前端的自動重試拿掉就好？ | full | 100% | 100% | 14.6 | 三點都有涵蓋，也沒有矛盾：回答寫到 key 由 server 端產生並每筆訂單固定、PR 討論中弱網使用者會更常失敗，以 |
| payment-failure | 為什麼不直接把前端的自動重試拿掉就好？ | agent | 100% | 100% | 19.8 | 三個要點都有涵蓋：回答引用了 Notion 規格，指出 key 由 server 端產生、每筆訂單固定、保留 24 小時 |

## 結論（這次執行）
> 上面的表格由 `scripts/eval_modes.py` 自動產生；這一段是人工（AI 協助）整理的解讀，重跑腳本時會被覆蓋，請記得更新。

**問題：把整個專案當成記憶（full）、讓 LLM 直接搜尋（agent），會不會比目前的 RAG 準？**

在目前的兩個評估情境上，**三種模式的準確度幾乎相同**：
- 要點涵蓋率：rag 98%、full 98%、agent 100%。差距只有一個要點（付款情境的完整任務題，agent 多寫出「先查狀態是為了避免重複扣款」）。
- 三種模式的來源命中率都是 100%，沒有矛盾、捏造或不存在的引用。
- 速度：rag 和 full 約 11 秒；agent 約 21 秒，慢一倍。
- 穩定度：agent 有 1 題因為 Claude CLI 內部的工具呼叫錯誤而失敗（已加入自動重試一次）。

**決定：預設使用 `rag`**（`QA_MODE=rag`）。
- 準確度和 full 相同、速度一樣快，而且專案變大時也不會失效；full 遇到超過上限的專案本來就會自動改用 rag。
- agent 的完整度略高，但速度慢一倍。這次的差距在誤差範圍內，不值得付出這個代價。
- full 和 agent 仍然可以用 `QA_MODE` 切換，正式評估前可以再比較一次。

**限制**：
- 只有 6 題，每題每種模式只跑 1 次。
- 資料只有 13 份文件，所以 full 可以把全部內容放進 context。真實專案的資料量大很多，這個比較不能直接推論到大型專案。
- 評分由 Claude 對照答案 key 進行，正式評估時仍要由人用答案 key 評分（觀察者頁面的「得分」欄）。
