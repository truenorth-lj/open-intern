---
description: Run MiniMax review on PR, evaluate comments, fix reasonable issues, and repeat until no significant issues remain.
---

## User Input

```text
$ARGUMENTS
```

## Overview

This skill automates the PR review-fix cycle **locally** using MiniMax M2.7 for code review. After a PR is created (or for an existing PR), it:

1. Runs local CI checks (lint + type check + tests)
2. Runs MiniMax code review via `scripts/review.sh`
3. Evaluates the review comments
4. Fixes issues that are reasonable
5. Pushes the fix and repeats
6. Merges when no actionable issues remain

## Step 0: Determine the PR

- If the user provides a PR number or URL in `$ARGUMENTS`, use that.
- Otherwise, detect the current branch and find the open PR for it:
  ```bash
  gh pr view --json number,title,url,headRefName
  ```
- If no PR exists, inform the user and stop.

**Store the PR number for the entire cycle.**

## Step 1: Run Local CI

Run lint, type check, and tests to catch basic issues before review:

```bash
ruff check . && ruff format --check . && mypy core/ cli/ --ignore-missing-imports && pytest -v
```

If any check fails, fix the issues first, commit, and push before proceeding.

## Step 2: Run MiniMax Code Review

```bash
./scripts/review.sh <pr_number> main
```

This will:
- Get the diff against main
- Send it to MiniMax M2.7 for review
- Post the review as a comment on the PR

## Step 3: Fetch and Evaluate Review Comments

Wait **2 minutes** (120 seconds) for any additional human reviewers:

```bash
sleep 120
```

Then fetch all comments:

### 3a. Issue-level comments
```bash
gh api repos/<owner>/<repo>/issues/<pr_number>/comments \
  --jq '.[] | {author: .user.login, date: .created_at, body: .body}'
```

### 3b. Review comments (inline)
```bash
gh api repos/<owner>/<repo>/pulls/<pr_number>/comments \
  --jq '.[] | {author: .user.login, path: .path, line: .line, body: .body}'
```

**Determine owner/repo from:**
```bash
gh repo view --json owner,name --jq '"\(.owner.login)/\(.name)"'
```

## Step 4: Evaluate Comments

For each comment, determine if it is **actionable and reasonable**:

### Fix these (actionable):
- Obvious bugs or logic errors
- Missing error handling that could cause runtime failures
- Security issues (input validation, auth checks)
- Type annotation issues
- Variable naming improvements that are clearly better

### Skip these (not actionable):
- Comments about pre-existing code that this PR didn't touch
- Suggestions to add features beyond the PR scope
- Pure style preferences without clear improvement
- MiniMax hallucinations (review mentions code/files that don't exist in the diff)
- Duplicate comments

### Important: Detect MiniMax hallucinations
MiniMax M2.7 sometimes hallucinates — referencing files, functions, or code patterns that don't exist. **Always cross-check** review comments against the real code before acting on them.

## Step 5: Apply Fixes

For each actionable item:

1. Read the relevant file
2. Make the fix
3. Mark the item as done

After all fixes:
1. Stage and commit with a descriptive message
2. Push to the PR branch: `git push`

**If no actionable items found**, skip to Step 7.

## Step 6: Re-review and Repeat

After pushing fixes:
1. Inform the user: > Pushed fixes. Running review again...
2. Run `./scripts/review.sh <pr_number> main` again
3. Wait 2 minutes: `sleep 120`
4. Go back to **Step 3**

## Step 7: Auto-Merge and Cleanup

When a review round produces **no new actionable items**, the cycle is complete.

### 7a. Squash merge the PR
```bash
gh pr merge <pr_number> --squash --delete-branch
```

### 7b. Update local main
```bash
git checkout main && git pull --rebase
```

### 7c. Delete local feature branch
```bash
git branch -d <branch_name> 2>/dev/null || true
```

### 7d. Monitor Deployment

After merge, monitor the Zeabur deployment until it's running:

```bash
# Poll deployment status (check every 15s, max 5 minutes)
zeabur deployment list --service-id 69beada1ceee47754dac1038 --env-id 69beabb576bc68ba374ca4da -i=false --json | head -30
```

- Look for a deployment with the merged commit SHA and `"status": "RUNNING"`
- If `"status": "BUILDING"` or `"status": "DEPLOYING"`, wait and re-check
- If `"status": "FAILED"`, check logs and report the error:
  ```bash
  zeabur deployment log --service-id 69beada1ceee47754dac1038 --env-id 69beabb576bc68ba374ca4da -t runtime -i=false
  ```
- Once RUNNING, verify the app responds:
  ```bash
  curl -s https://open-intern.zeabur.app/api/dashboard/status
  ```

### 7e. Post-Deploy Testing

After deployment is confirmed running, test the feature in the browser:

1. Open `https://open-intern.zeabur.app` in Chrome using browser tools
2. Navigate to the relevant page for the feature/fix
3. Verify the change works as expected (check UI renders, API calls succeed, no console errors)
4. Take a screenshot as evidence
5. If the feature involves interactive elements, test the main user flows

If post-deploy testing reveals issues:
- Report the issue to the user
- If it's a quick fix, create a follow-up PR

### 7f. Report to the user
- Total review rounds completed
- Summary of all fixes made
- Any comments intentionally skipped and why
- Deployment status (success/failure)
- Post-deploy test results (with screenshot)
- Confirm: PR merged, deployed, and tested

## Key Rules

1. **Never wait more than 3 rounds** — If after 3 cycles there are still new issues, stop and report.
2. **Never fix code you haven't read** — Always read the file before editing.
3. **Commit messages should be concise** — Group related fixes into one commit per round.
4. **Skip duplicate feedback** — If a new round repeats the same comment, ignore it.
5. **Respect the PR scope** — Don't refactor beyond what the review asks for.
6. **Verify MiniMax output** — Always cross-check review comments against real code.
