# Draft AI Usage Guidelines

## Section 1 — Tool-to-Task Mapping
* **Claude 3.5 Sonnet (via Web/API):** We will use Sonnet for drafting boilerplate endpoint logic and first-pass unit test skeletons — not for core business architecture, authentication, or payment logic, which must be authored from scratch by a human.
* **GitHub Copilot:** We will use inline autocomplete for speed while typing familiar patterns — not as a substitute for authoring PR descriptions, commit messages, or DECISIONS.md entries.
* **Claude / LLMs for Design & Architecture:** We will use Claude to brainstorm and compare structural design options — not to make final architectural calls, which require a team sync and a recorded entry in `DECISIONS.md`.
* **Documentation:** We will use Claude to draft initial API docstrings and markdown formatting — a human must review, verify accuracy against implementation, and edit before merging.

## Section 2 — Interaction Logging & Documentation
* **Prompt Engineering Log (`docs/prompts/`):** Any prompt that generates code, test suites, or documentation that ends up committed to the repository must be logged (prompt text, model used, and what was manually adapted). One-off syntax checks and debugging questions do not require logging.
* **PR Descriptions:** The PR description template must explicitly note whether AI was involved. If used, it must cite the tool and point to the corresponding log entry.
* **DECISIONS.md:** If an AI interaction suggests a change in architectural approach, data schema, or library choice that the team adopts, it must be recorded as an ADR in `DECISIONS.md`, not just left in a prompt log.

## Section 3 — Disagreements & Quality Standards
* **Final Authority:** If team members disagree on whether AI-generated code meets standards, the **Code Steward** holds the final decision (not the prompt author or senior member).
* **Required Evidence for Merge:**
  1. Passes all existing automated test suites and linters.
  2. Complies with the PR review checklist.
  3. The implementation can be clearly explained by a team member other than the person who prompted it.
* **Tie-Breaking:** If the dispute is purely stylistic, existing linter rules govern. If non-stylistic, the Code Steward makes the call and documents the rationale in one sentence within `DECISIONS.md`.