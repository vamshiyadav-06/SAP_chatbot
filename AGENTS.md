# Repository agent instructions

Before changing this repository, read `docs/engineering-memory/NEXT_SESSION.md`, then `PROJECT_CONTEXT.md` and `IMPLEMENTATION_MAP.md` for unfamiliar areas. Run `git status --short` before editing; this project may contain user work that is not committed.

Inspect the relevant implementation and its tests before proposing a change. Preserve the FastAPI/React architecture and avoid unrelated refactors. Never expose `.env` values, credentials, private chat content, or internal retrieval metadata to regular users. Do not run destructive database or Docker-volume commands.

For every meaningful change: add/update focused regression tests, run the applicable verification, inspect `git diff --check` and the relevant diff, and update the engineering-memory files. Record tests only as passed when they completed successfully. Update `NEXT_SESSION.md` before ending a session, including blockers and unverified assumptions.
