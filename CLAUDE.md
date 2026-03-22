# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

open_intern — An open-source AI employee that joins your team as a real teammate. Python backend (FastAPI + LangGraph + Deep Agents) with a Next.js dashboard frontend. Supports Lark, Discord, Slack, and web-only modes.

## Project Structure

```
open_intern/
├── core/                  # Agent logic, config, identity, LLM providers
│   ├── agent.py           # Main OpenInternAgent class (LangGraph + Deep Agents)
│   ├── config.py          # Pydantic config models + YAML loader
│   └── identity.py        # System prompt builder
├── memory/
│   └── store.py           # PostgreSQL + pgvector memory store
├── safety/
│   └── permissions.py     # Action approval system (allow/deny/ask)
├── integrations/
│   ├── base.py            # Abstract platform adapter
│   ├── lark/              # Lark (Feishu) bot adapter
│   ├── discord/           # Discord bot adapter
│   └── slack/             # Slack bot adapter (stub)
├── api/
│   └── dashboard.py       # Dashboard REST API (FastAPI router)
├── cli/
│   └── main.py            # Typer CLI (init, start, status, logs, chat)
├── skills/                # Agent skills (extensible)
├── web/                   # Next.js dashboard frontend (port 3000)
├── config/
│   └── agent.example.yaml # Example agent configuration
├── server.py              # FastAPI app factory + platform runners
├── docker-compose.yml     # PostgreSQL (pgvector) + agent
├── Dockerfile             # Python 3.12-slim container
├── pyproject.toml         # Hatchling build, ruff, dependencies
└── uv.lock                # uv lockfile (committed)
```

## Commands

```bash
# Install (development) — requires uv (https://docs.astral.sh/uv/)
uv sync --all-extras          # Install all deps + dev deps into .venv

# CLI commands
open_intern init          # Create config/agent.yaml from example
open_intern start         # Start agent on configured platform
open_intern start --web   # Start in web-only mode (dashboard API on port 8000)
open_intern status        # Show agent config and memory stats
open_intern logs          # View recent audit logs
open_intern chat          # Interactive CLI chat mode

# Docker services
docker compose up -d postgres          # Start DB only
docker compose up -d                  # Start everything (DB + agent)
docker compose logs -f agent          # Follow agent logs

# Lint & format
ruff check .              # Lint (rules: E, F, I, N, W)
ruff format .             # Auto-format
ruff check --fix .        # Auto-fix lint issues

# Type check
mypy core/ cli/ --ignore-missing-imports

# Tests
pytest -v                 # Run all tests
pytest -v -k "test_name"  # Run specific test

# Web dashboard (Next.js)
cd web && npm install && npm run dev   # Dev server on localhost:3000
cd web && npm run build                # Production build
cd web && npm run lint                 # ESLint
```

## Tech Stack

### Backend
- **Language**: Python 3.11+, type-annotated
- **Framework**: FastAPI + uvicorn
- **Agent**: LangGraph + Deep Agents + LangChain
- **LLM Providers**: Anthropic (Claude), OpenAI, MiniMax (M2.7), Ollama
- **Database**: PostgreSQL 17 + pgvector (via psycopg + SQLAlchemy)
- **Config**: Pydantic models + YAML files
- **CLI**: Typer + Rich

### Frontend (web/)
- **Framework**: Next.js 16, React 19, TypeScript
- **Styling**: Tailwind CSS 4, Base UI components
- **State**: React hooks + fetch API

## Architecture

### Agent Pipeline
1. Message arrives via platform adapter (Lark/Discord/Slack/web API)
2. Safety middleware checks action permissions (allow/deny/ask)
3. Memory store retrieves relevant context (pgvector similarity search)
4. Deep Agent processes with system prompt (identity + personality)
5. Response sent back via platform adapter
6. Conversation stored to memory

### Config System
- Config loaded from `config/agent.yaml` (or `agent.yaml`, `~/.open_intern/agent.yaml`)
- All settings are Pydantic models with sensible defaults
- Platform credentials via YAML config or environment variables
- LLM API keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `MINIMAX_API_KEY`

### Memory System
- PostgreSQL + pgvector for semantic search
- Three scopes: `shared` (org-wide), `channel` (channel-specific), `personal` (DM)
- Importance decay over time (configurable, default 90 days)
- Agent has `recall_memory` and `store_memory` tools

### Safety System
- Actions classified as: `auto_allow`, `require_approval`, or `deny`
- Default auto-allow: read_channel, respond_to_mention, respond_to_dm
- Default require approval: send_email, create_pr, post_public_channel, delete_anything
- Audit log written to `logs/audit.jsonl`

## Critical Patterns

### LLM Provider Setup
MiniMax uses Anthropic-compatible API with custom base_url. The `_create_llm()` function in `core/agent.py` handles this. When adding new providers, check if they need the Anthropic-compatible path or native LangChain init.

### Platform Adapters
All platform bots extend the pattern in `integrations/base.py`. The `server.py` factory creates the FastAPI app and delegates to platform-specific runners (`run_lark`, `run_discord`, `run_web_only`).

### Environment Variables
- `.env` — LLM API keys, platform tokens (not committed)
- `.env.example` — Template showing required variables
- `config/agent.yaml` — Agent configuration (not committed)
- `config/agent.example.yaml` — Example config (committed)
- **Never ask the user for API key values.** Only tell them which file and variable to set.

### Docker Services
- PostgreSQL: `pgvector/pgvector:pg17` on port **5556** (host) → 5432 (container)
- Agent: port **8000** (FastAPI + uvicorn)

## Development Workflow

**MANDATORY**: All new work (features, bug fixes, refactors, etc.) MUST follow this workflow:
1. **Create a worktree** — always start by opening a worktree (`/dev-test` or equivalent) to isolate changes.
2. **Implement & test** — do all work inside the worktree.
3. **Create PR** — push and open a pull request.
4. **Run PR review cycle** — run `/pr-review-cycle` to get automated MiniMax review, fix issues, and repeat until clean.
5. **Merge & cleanup** — merge the PR and clean up the worktree.

Never commit directly to `main`. Never skip the PR review cycle.

- **Feature / Bug Fix**: Use worktree workflow (`/dev-test`) — create worktree, implement, test, PR, review, merge, cleanup.
- **PR Review**: Use `/pr-review-cycle` — automated MiniMax review + fix cycle.
- **Deployment Monitor**: Use `/cicd-monitor` — watch docker deployment logs and auto-fix.

### Local CI (Pre-push Hook)

CI checks run locally via git pre-push hook. Install:
```bash
cp scripts/pre-push .git/hooks/pre-push && chmod +x .git/hooks/pre-push
```

Runs before each push:
1. `ruff check .` + `ruff format --check .`
2. `mypy core/ cli/ --ignore-missing-imports`
3. `pytest -q`

Skip with: `git push --no-verify`

### PR Review (MiniMax)

Local code review using MiniMax M2.7:
```bash
./scripts/review.sh              # Review diff, print to terminal
./scripts/review.sh 12 main      # Review and post to PR #12
```
