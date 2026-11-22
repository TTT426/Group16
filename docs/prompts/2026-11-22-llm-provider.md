# 2026-11-22 — Choose the AI model on the web page (Claude Code, Anthropic API, OpenAI API, Ollama)

Recorded per [AI_GUIDELINES.md](../../AI_GUIDELINES.md) §2. Builds on [2026-11-22-connect-discord.md](2026-11-22-connect-discord.md).

## Tool / Model
- Claude Opus 5.5 (`claude-opus-5-5`), through Claude Code (CLI)

## Prompts (summaries)
1. Check that the Connect tools PRs are merged and that main works, then, following the same workflow as before, add a way to choose the LLM on the web page: right now the app always uses Claude Code. The choice should also be on the Connect tools page, separated from the GitHub / Notion / Discord part (for example by a line); the exact layout is up to the AI for now.
   - The AI noted that the pending #11 proposal ("only the Claude CLI") is reversed by this, kept Claude Code as the default, and added three providers behind the existing `LLMProvider` interface.
2. In the top bar, either remove the model label or add a button that links to switching the model (the user preferred the button).
3. What happens when no provider is set up, or a provider breaks? Agreed on two cases: no provider set up shows a warning; a set-up provider with a bad key, timeout, etc. only shows the error when a question is asked, because that is only known by actually calling it.
   - The AI recommended no automatic switch to another provider (it could move a local setup to a paid or cloud service, or change the model mid-evaluation), and fixed related gaps: errors that won't fix themselves are no longer retried, the "Claude Code not installed" message is in Chinese like the rest of the UI, and an invalid `LLM_PROVIDER` gives a message instead of a server error.

## AI responses / recommendations (summary)
| Recommendation | Result |
|---|---|
| Providers: Claude Code (default, unchanged), Anthropic API (official `anthropic` SDK), OpenAI or any OpenAI-compatible server (httpx), Ollama for local models (httpx) | Pending review |
| `/connect` gets an "AI model" section below a divider line; `/connect/llm` checks each provider (CLI login, key, server), lists its models, tests the model with one short question and saves `LLM_PROVIDER` / `LLM_MODEL` to `.env` | Pending review |
| The ask page gets a model picker next to the "ask" button (locked during an evaluation session) | Pending review |
| `agent` mode needs a model that searches files itself, so only Claude Code supports it; other providers answer `agent` questions in `rag` mode with a notice | Pending review |
| Replies are constrained with each provider's own JSON-schema feature (structured outputs on the APIs, `format` on Ollama); the existing JSON parsing stays as the fallback | Pending review |
| Anthropic API: default model `claude-opus-5-5`; server-side refusal fallbacks (`fallbacks: "default"`) on models that support them | Pending review |
| Ollama: raise the context window to 16k tokens (`OLLAMA_NUM_CTX`), because Ollama's default silently cuts long prompts | Pending review |
| API keys follow the same rules as the tool tokens: stored only in `.env`, never sent back to the browser, routes on localhost only | Pending review |
| Top bar shows the model in use with a "更換" button to `/connect/llm` (hidden during evaluation sessions) | Accepted (user's choice) |
| No model set up: warn on every page without calling any service; a set-up model that fails: show the error when asking, without retrying errors that won't fix themselves | Accepted (user's choice) |
| No automatic fallback to another provider | Pending review |

## Verification (done by the AI)
- `pytest`: 167 passed, 1 skipped (also on a clean checkout); `ruff check .`: passed
- In a sandbox copy (its own `.env` and database), through the API the page uses:
  - Claude Code: status shows it logged in; the test call answered (Haiku, 2.4 s)
  - Ollama (`qwen3:8b`): selected, test call answered; an `agent` question was answered in `rag` mode with the notice, with 4 valid citations (41 s)
  - OpenAI-compatible: Ollama's `/v1` endpoint with no key; the model list loaded, and a question was answered with valid citations (26 s), which exercises the strict `json_schema` request
  - Invalid Anthropic and OpenAI keys are rejected by the real APIs with the friendly message, and nothing is saved
  - No model set up (Anthropic chosen, no key): the top bar, the ask page, `/connect` and `/connect/llm` warn; asking returns the same message
  - Set up but broken: a revoked Anthropic key and an unreachable Ollama show no warning up front; asking fails with the reason after a single call (0.6 s / 0.35 s)
- Headless Chrome screenshots of `/connect`, `/connect/llm` and `/` (model picker, top bar, warnings); no console errors
- **Not yet verified:** a successful call with a real Anthropic or OpenAI API key (mocked tests only); running on Windows
