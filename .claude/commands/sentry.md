---
description: Triage Sentry errors — list unresolved issues, inspect details, correlate with code, and fix.
---

## User Input

```text
$ARGUMENTS
```

Triage and investigate Sentry errors for the open-intern-backend project.

### Prerequisites

- `sentry-cli` installed (`brew install getsentry/tools/sentry-cli`)
- Personal token configured in `~/.sentryclirc`
- Default org: `openhealth-c7`, project: `open-intern-backend`

### Arguments

- `` (no args): List all unresolved issues
- `--recent` or `-r`: Show issues from last 1 hour only
- `--resolve <ID>`: Mark an issue as resolved
- `<issue-id>`: Show details for a specific issue (e.g., `OPEN-INTERN-BACKEND-X`)

### Commands Reference

```bash
# List unresolved issues (default)
sentry-cli issues list --query "is:unresolved"

# List issues from a time period
sentry-cli issues list --query "is:unresolved firstSeen:-1h"

# Show issue details (use numeric ID from list)
sentry-cli issues show <ISSUE_ID>

# Show latest event for an issue
sentry-cli events list <ISSUE_ID> --max-events 1

# Resolve an issue
sentry-cli issues resolve <ISSUE_ID>

# Resolve multiple issues
sentry-cli issues resolve <ID1> <ID2> <ID3>
```

### Workflow

1. **List issues** — Run `sentry-cli issues list --query "is:unresolved"` to see all unresolved issues.

2. **Categorize** — Group issues by root cause:
   - Same stack trace = same root cause
   - Paramiko/SSH errors are usually one issue
   - Scheduler errors wrapping other errors are derivatives

3. **Investigate** — For each unique root cause:
   - Get the error message and logger from the issue list
   - Grep the codebase for the error source: `grep -r "error message" core/`
   - Read the relevant code to understand the bug

4. **Fix** — Follow the standard dev workflow:
   - Create worktree, implement fix, test, PR, review, merge
   - Use `/dev-test` for the full workflow

5. **Verify** — After deploy, check Sentry again:
   ```bash
   sentry-cli issues list --query "is:unresolved firstSeen:-1h"
   ```

6. **Resolve fixed issues** — Bulk resolve old issues that are now fixed:
   ```bash
   sentry-cli issues resolve <ID1> <ID2> ...
   ```

### Tips

- The issue list shows numeric IDs (first column) and short IDs (second column like `OPEN-INTERN-BACKEND-X`). Use **numeric IDs** for CLI commands.
- Issues with similar titles but different short IDs may be the same root cause captured at different stack frames.
- After deploying a fix, wait for the next cron tick before declaring victory — scheduled jobs run on intervals.
- Always check `--query "is:unresolved firstSeen:-1h"` after deploy to catch new regressions.
