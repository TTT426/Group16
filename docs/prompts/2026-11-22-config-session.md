# Fix config endpoint session isolation — 2026-11-22

- Tool: Codex, AI-assisted implementation, test, documentation and PR preparation.
- User request: Complete a second substantive code PR following macOS setup work.
- Problem: /api/config opened get_session_factory directly instead of honoring the get_session override used by the API test fixture. Clean environments failed with no such table: documents; existing local databases could mask the failure or provide unrelated document counts.
- Change: Use FastAPI Depends(get_session), matching the other database-backed endpoints. Session lifetime remains owned by the existing dependency.
- Regression: Point the default database factory at a nonexistent temporary database while supplying an ingested test session. Assert HTTP 200, exact per-source counts from that injected session, and that no local database is created.
- Before fix: the new regression test failed with sqlite3.OperationalError: no such table: documents.
- After fix: API flow suite 9 passed. Full suite on Apple Silicon macOS/Python 3.14 with DATABASE_PATH pointing to an absent temporary file and EMBEDDING_PROVIDER=hashing: 127 passed, 1 skipped. Ruff and whitespace checks passed. The temporary database file remained absent.
- Limitation: opt-in real embedding test was not enabled; no real external accounts or Windows test were involved. This fixes a cross-platform isolation bug discovered during macOS review; it is not claimed to be macOS-exclusive.
- Human acceptance: pending independent teammate review; no approval or merge is claimed here.
