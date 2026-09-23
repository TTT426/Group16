# Draft AI Usage Guidelines

## Section 1 — Tools and Allowed Uses

### ChatGPT or Claude

We may use ChatGPT or Claude to:

- Explain unfamiliar Git commands and error messages.
- Brainstorm implementation options.
- Draft boilerplate code, documentation, and initial test cases.
- Review a proposed approach and identify possible edge cases.

We may not use AI as the final authority for architecture, authentication,
payment logic, privacy decisions, or security-sensitive code. A human team
member must understand, test, and review all generated content before it is
merged.

### GitHub Copilot

GitHub Copilot may be used for inline completion of familiar and repetitive
patterns. It must not replace human-written PR descriptions, commit messages,
or entries in `DECISIONS.md`.

### Documentation

AI may produce an initial documentation draft. A team member must compare it
with the actual implementation, correct inaccurate claims, and review the final
version before merging.

## Section 2 — Recording AI Interactions

Any AI interaction that produces code, tests, documentation, or an important
technical recommendation that enters the repository must be recorded. The
record must include:

- The tool and model, when known.
- The original prompt or a faithful summary.
- The relevant response or recommendation.
- What a team member verified or changed.
- Whether the output was accepted, modified, or rejected.

One-off syntax questions do not require a full log unless their answers cause a
significant project decision.

Pull requests must state whether AI was used. If a significant AI-assisted
choice affects architecture, data schema, dependencies, security, or team
workflow, the final human decision and rationale must also be recorded in
`DECISIONS.md`.

### Example Interaction

**Tool:** ChatGPT

**Prompt:** “Explain how to create a Git branch, add a contributor file, commit
it, push the branch, and open a pull request without modifying `main`
directly.”

**Result:** The response proposed using `git switch -c`, `git add`,
`git commit`, and `git push -u origin <branch>`.

**Human verification:** A team member checked the current branch with
`git branch --show-current`, inspected staged changes with `git status`,
verified the PR diff on GitHub, and waited for another member’s approval.

**Decision:** Accepted after verification. The commands produced the expected
branch and reviewed pull-request workflow.

## Section 3 — Quality Standards and Disagreements

AI-generated work may be merged only when:

1. Existing automated tests and linters pass, when available.
2. A human reviewer checks the changed files.
3. The implementation can be clearly explained by a team member other than
   the person who prompted the AI.
4. Referenced APIs and library features are checked against official
   documentation.
5. No secrets, personal data, or confidential information were given to the AI.

If team members disagree about AI-generated code, existing project rules and
test evidence take priority. For stylistic disagreements, the configured
formatter or linter decides. For non-stylistic disagreements, the Code Steward
makes the final call and records the rationale in `DECISIONS.md`.

### Accepted Output Example

AI suggested the branch, commit, push, and pull-request workflow described
above. The team accepted it only after checking the active branch, Git status,
GitHub diff, reviewer approval, and successful merge into `main`.

### Rejected Output Example

During review, an AI-assisted draft initially appeared ready to approve.
However, a human inspection of `CONTRIBUTORS.md` showed garbled characters and
GitHub treated the file as binary. The team rejected the draft, requested a
UTF-8 plain-text correction, and verified the repaired file with `file
CONTRIBUTORS.md` before considering approval.

These examples demonstrate that AI output is advisory. Passing human review
and producing observable evidence are required before acceptance.
