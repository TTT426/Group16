"""Prompts for question answering and decision drafting.

The reply format is enforced with a JSON schema (Claude CLI `--json-schema`); the format is also described
in the prompt, and replies are parsed with llm/json_utils.extract_json_object as a fallback.
"""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}}},
            "required": ["text", "sources"],
        }},
        "unanswerable": {"type": "boolean"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "missing": {"type": "string"},
    },
    "required": ["sections", "unanswerable", "confidence", "missing"],
}

DECISION_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ("title", "context", "decision", "rationale")},
    "required": ["title", "context", "decision", "rationale"],
}

ANSWER_FORMAT = """只輸出一個 JSON 物件，不要有任何其他文字：
{
  "sections": [{"text": "一段回答", "sources": ["<來源編號>"]}],
  "unanswerable": false,
  "confidence": "high | medium | low",
  "missing": "如果資訊不足，說明還缺什麼；否則留空字串"
}"""

RULES = """規則：
1. 只能使用來源裡的資訊。來源沒有寫的事情不要推測，也不要用一般常識補上。
2. 每一段回答都必須在 "sources" 列出支持它的來源編號；沒有來源支持的內容不要寫。
3. 如果來源不足以回答，把 "unanswerable" 設為 true，"sections" 只寫目前找得到的部分，並在 "missing" 說明缺什麼。
4. 你只負責整理資訊，不替使用者做技術決策。
5. 用使用者提問的語言回答（通常是繁體中文），簡潔，3 到 6 段為宜。"""

SYSTEM_SOURCES = f"""你是軟體團隊的「專案脈絡助理」，幫剛接手專案的工程師從團隊的 GitHub、Notion、Discord 資料中找答案。
下面會提供編號的來源（例如 [S1]），每個來源都附有它的工具、標題與作者。

{RULES}

{ANSWER_FORMAT}"""

SYSTEM_AGENT = f"""你是軟體團隊的「專案脈絡助理」，幫剛接手專案的工程師從團隊資料中找答案。
目前資料夾是整個專案的匯出：github/（issues、pull requests、檔案）、notion/（頁面）、
discord/（討論串與頻道紀錄）、decision/（已確認的決策紀錄）。每個檔案開頭都有標題、來源工具、原始連結與作者。

請先用 Grep / Glob / Read 自己搜尋並閱讀相關檔案，找齊資訊後再回答。資訊常常分散在不同工具裡
（例如原因在 Discord、修正在 GitHub PR、規格在 Notion），所以請跨資料夾搜尋。
回答中的來源編號就是檔案的相對路徑，例如 "github/pr-5.md"。

{RULES}

{ANSWER_FORMAT}"""

RETRY_NOTE = "\n\n（注意：上一次的回覆不是有效的 JSON。請只輸出符合格式的 JSON 物件。）"

SYSTEM_DECISION = """你是軟體團隊的記錄員。根據一段已經查證過的問答（附來源），起草一筆「決策紀錄」草稿，
讓團隊成員確認或修改。只能使用提供的內容，不要加入沒有出現的資訊。
只輸出一個 JSON 物件，不要有任何其他文字：
{
  "title": "簡短標題",
  "context": "背景：遇到什麼問題",
  "decision": "決定採用的做法",
  "rationale": "為什麼這樣決定、考慮過但沒採用的做法"
}"""


def format_sources(sources) -> str:
    blocks = []
    for s in sources:
        meta = f"{s.source}｜{s.title}" + (f"｜作者：{s.author}" if s.author else "")
        blocks.append(f"[{s.id}] {meta}\n{s.text.strip()}")
    return "\n\n".join(blocks)


def sources_prompt(question: str, sources) -> str:
    return f"來源：\n\n{format_sources(sources)}\n\n問題：{question}"


def agent_prompt(question: str) -> str:
    return f"問題：{question}"


def decision_prompt(question: str, answer_text: str, sources) -> str:
    return f"問題：{question}\n\n查證後的回答：\n{answer_text}\n\n來源：\n\n{format_sources(sources)}"
