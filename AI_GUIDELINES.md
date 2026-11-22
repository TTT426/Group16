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

## Section 4 — Pull Request Order (proposal, pending team confirmation)

Every change reaches `main` through a pull request, in this order. Review
happens before merge, and the decision record goes in with the change it
describes.

1. **Branch.** Branch from the latest `main` as `<name>-<topic>`. One topic
   per PR. Do not stack a PR on another unmerged branch; wait until that PR
   is merged, then branch from `main`.
2. **Prepare.** Before asking for review, the author:
   - merges the latest `main` into the branch;
   - runs `pytest` and `ruff check .` on a clean checkout (a fresh clone or
     worktree, without a reused local database) and reports the results;
   - states AI use in the PR body and adds a log under `docs/prompts/`
     (Section 2).
3. **Review.** A team member other than the author acts as code steward
   for the PR. The steward reads every changed file, reruns the tests on a
   clean checkout of the PR merged with the current `main`, and submits a
   formal GitHub review. A comment alone is not a review.
4. **AI-assisted review.** AI may draft a review. It must not approve or
   merge without the steward's instruction for that specific PR. The steward
   must read the diff, be able to explain it, and state in the review that
   it was AI-assisted.
5. **Record before approval.** The steward review entry in `DECISIONS.md`
   (`Code steward 審閱：PR #N`), and any decision the PR makes, are committed
   to the same PR branch before the final Approve. Write each entry as it
   will read after merge, so that it does not say "not yet merged".
6. **Approve, then merge.** The steward submits Approve after the record
   commit, checks that the branch is up to date with `main` and the tests
   still pass, and merges with a merge commit. No one merges a PR that has
   no Approve from someone other than the author.
7. **No direct pushes to `main`,** including documentation such as
   `DECISIONS.md`. A fix to a record that is already merged goes through its
   own PR.
8. **Updating a PR.** To sync a PR with `main`, update its branch; do not
   open a duplicate PR. When a PR is closed without merging, leave a comment
   saying why.
