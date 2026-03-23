---
description: Monitor deployment after push, check logs, fix failures, and retry until deployment succeeds.
---

## User Input

```text
$ARGUMENTS
```

## Deployment Monitor

After pushing code, monitor deployment by checking build and runtime logs until confirmed successful.

### Arguments

- `$ARGUMENTS` (optional):
  - `--max-retries <n>`: Maximum fix attempts (default: 3)
  - `--docker`: Monitor docker compose deployment (default)

### Steps

1. **Get current context**:
   - Get current branch: `git branch --show-current`
   - Get latest commit: `git log -1 --format='%H %s'`

2. **Build and deploy**:
   ```bash
   docker compose build agent
   docker compose up -d
   ```

3. **Monitor build logs**:
   ```bash
   docker compose logs --tail=50 agent
   ```
   - Check for build errors (pip install failures, missing dependencies)
   - If build errors → Step 5

4. **Check runtime health**:
   ```bash
   # Wait for startup
   sleep 10
   # Health check
   curl -s http://localhost:8000/health | python -m json.tool
   # Check for runtime errors
   docker compose logs --tail=100 agent 2>&1 | grep -i "error\|exception\|traceback"
   ```
   - Look for successful startup: `"status": "ok"` in health response
   - Look for error patterns:
     - `psycopg.OperationalError` — DB connection issues
     - `ModuleNotFoundError` — missing dependencies
     - `ValidationError` — config issues
     - Unhandled exceptions or crash loops
   - If healthy → Step 7
   - If errors → Step 5

5. **Analyze failures**:
   - Categorize failure type:
     - `build`: Missing packages, syntax errors
     - `db`: Connection or schema issues
     - `config`: YAML config or env var issues
     - `runtime`: Application crashes or unhandled errors
   - For **build failures**: check Dockerfile, pyproject.toml dependencies
   - For **db issues**: check `docker compose ps postgres`, verify DATABASE_URL
   - For **config issues**: check .env, database agent settings
   - For **runtime errors**: read the error stack trace and fix the code

6. **Fix and redeploy**:
   ```bash
   # Fix the identified issues locally
   # Verify locally:
   ruff check . && pytest -v

   # Commit and push
   git add <specific-files>
   git commit -m "fix: resolve deployment failure - <description>"
   git push

   # Redeploy
   docker compose build agent && docker compose up -d
   ```
   - Increment retry counter
   - Go back to Step 3

7. **Confirm deployment success**:
   - Health endpoint returns `{"status": "ok"}`
   - No errors in recent logs
   - Report success to user

### Output Format

```
## Deployment Report

**Branch**: feat/my-feature
**Commit**: abc1234 - feat: add feature X

### Deployment Status

| Attempt | Build | Runtime | Fix Applied |
|---------|-------|---------|-------------|
| 1       | fail  | -       | missing dep |
| 2       | pass  | pass    | -           |

### Fixes Applied

1. **Attempt 1** - Build failure
   - Added missing dependency to pyproject.toml

### Final Status: SUCCESS

Deployment confirmed healthy after 1 fix iteration.
```

### Error Handling

- **Max retries exceeded**: After 3 failed attempts, stop and ask user
- **Infra issues**: If Docker/DB platform issues, tell user to check docker compose
- **DB migration needed**: Suggest running alembic migration and ask user to confirm
