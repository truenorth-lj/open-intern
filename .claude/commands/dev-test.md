---
description: Dev Test Workflow
---

## User Input

```text
$ARGUMENTS
```

Full development workflow: clarify → worktree → implement → test → PR → review → merge → cleanup.

## Phase 1: Clarify

1. **Understand the task** — Read user's description. If unclear, ask questions until you fully understand:
   - What is the expected behavior?
   - What is the current behavior (if bug)?
   - Which modules/components are affected?
2. **Explore the codebase** — Read relevant files, understand current architecture.
3. **Confirm plan** — Briefly state what you'll do and get user's OK before proceeding.

## Phase 2: Worktree Setup

4. **Create worktree** with a descriptive branch name:
   ```bash
   git worktree add -b <type>/<short-name> ../open_intern-<short-name> main
   ```
   Where `<type>` is `feat/`, `fix/`, `docs/`, etc.

5. **Symlink env files** (required for DB, API keys):
   ```bash
   cd ../open_intern-<short-name>
   ln -sf /Users/lj/Documents/open_intern/.env .env
   ```

6. **Install dependencies**:
   ```bash
   pip install -e ".[all,dev]"
   ```

## Phase 3: Implement

7. **Write code** — Follow project conventions (see CLAUDE.md).
8. **Lint & type check** — Run `ruff check . && ruff format --check . && mypy core/ cli/` to catch errors early.
9. **Run tests** — `pytest -v` to verify nothing is broken.
10. **Commit** — Stage relevant files (NOT `git add -A`) and commit with conventional commit message.

## Phase 4: Local Testing

11. **Start services** — `docker compose up -d postgres` to start DB.
12. **Start agent** — Run `python -m cli.main start --web` in background (port 8000). Wait for startup.
13. **Start web dashboard** — `cd web && npm run dev` (port 3000).
14. **Test the feature/fix** — Use Chrome tools or curl to verify behavior.
15. **Fix issues** — If test fails, fix code, re-test.
16. **Stop services** — Kill background processes after testing.

## Phase 5: PR & Review

17. **Push branch** — `git push -u origin <branch-name>`.
18. **Create PR** — Use `gh pr create` with descriptive title and body.
19. **Run PR review cycle** — Follow `/pr-review-cycle` flow:
    - Run `./scripts/review.sh <pr_number> main`
    - Evaluate comments, fix actionable items
    - Repeat until LGTM (max 3 rounds)
20. **Squash merge** — `gh pr merge <pr_number> --squash --delete-branch`

## Phase 6: Cleanup

21. **Update local main**:
    ```bash
    git checkout main && git pull --rebase
    ```
22. **Remove worktree**:
    ```bash
    git worktree remove ../open_intern-<short-name>
    git branch -d <branch-name> 2>/dev/null || true
    ```
23. **Report** — Summarize what was done, link to merged PR.

## Important Notes

- Backend API runs on port **8000**, web dashboard on port **3000**
- Docker services: PostgreSQL on 5556
- All work happens in the worktree — never modify files in the main repo directory
- If a phase fails, stop and ask the user before proceeding
