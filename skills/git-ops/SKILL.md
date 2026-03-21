---
name: git-ops
description: Perform git operations like status, diff, commit, push, branch management, and pull requests on repositories. Use when a user asks to check code changes, commit work, create branches, or manage git workflow.
allowed-tools: execute
metadata:
  category: devops
  version: "1.0"
---

# Git Operations

## When to Use
- User asks to check repository status, view diffs, or see recent commits
- User asks to commit changes, stage files, or create branches
- User asks to push code or create pull requests
- User asks to manage branches (create, switch, merge, delete)
- User asks about git history or blame

## How to Execute

### Safety Rules (ALWAYS follow)
1. **Never force push** (`git push --force`) without explicit user confirmation
2. **Never commit secrets** (.env, credentials, API keys) — warn the user if detected
3. **Always show `git status` first** before committing so the user can review
4. **Stage specific files** — avoid `git add .` or `git add -A` unless the user explicitly requests it
5. **Never run `git reset --hard`** or other destructive commands without explicit user confirmation
6. **Ask before pushing** — always confirm with the user before `git push`

### Common Workflows

#### Check Status
```bash
git status
git log --oneline -10
```

#### Commit Changes
1. Run `git status` to show current state
2. Show `git diff` for the files to be committed
3. Confirm with the user which files to stage
4. Stage specific files: `git add <file1> <file2>`
5. Commit with a descriptive message: `git commit -m "type: description"`

#### Create Branch
```bash
git checkout -b feature/branch-name
```

#### View History
```bash
git log --oneline -20
git log --graph --oneline --all -20
git diff HEAD~1
```

### Commit Message Convention
Follow conventional commits format:
- `feat:` new feature
- `fix:` bug fix
- `refactor:` code refactoring
- `docs:` documentation
- `chore:` maintenance tasks
- `test:` adding or updating tests

### Error Handling
- If a git command fails, read the error message and explain it to the user
- If there are merge conflicts, show the conflicting files and ask the user how to resolve
- If the working directory is dirty before a branch switch, warn the user
