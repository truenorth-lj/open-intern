<p align="center">
  <img src="docs/images/banner.svg" alt="Open Intern — Enterprise AI Employee Platform" width="100%"/>
</p>

<p align="center">
  <a href="#quick-start"><strong>Quick Start</strong></a> ·
  <a href="#why-open-intern"><strong>Why Open Intern</strong></a> ·
  <a href="#how-it-compares"><strong>Comparison</strong></a> ·
  <a href="#architecture"><strong>Architecture</strong></a> ·
  <a href="#documentation"><strong>Docs</strong></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License"/>
  <img src="https://img.shields.io/badge/self--hosted-100%25-blueviolet" alt="Self-Hosted"/>
  <img src="https://img.shields.io/badge/telemetry-zero-critical" alt="Zero Telemetry"/>
</p>

---

<p align="center">
  <img src="docs/images/avatar.png" alt="Open Intern" width="140" style="border-radius: 50%;"/>
</p>

**Open Intern** is an enterprise-grade, self-hosted AI employee that joins your team as a real colleague — not a chatbot widget, not a personal assistant, but a persistent team member with its own identity, organizational memory, and the judgment to act on its own.

Think of it as hiring an AI that actually *works here*.

> Built for teams that need the power of AI agents with the security and control of on-premise software. If OpenClaw is the personal AI assistant and IronClaw is the security-hardened CLI, **Open Intern is the enterprise AI teammate** — deployed on your infra, governed by your policies, embedded in your workflows.

---

## Why Open Intern

Most "AI assistant" platforms are glorified chatbot wrappers — you ask, they answer, context is gone. The Claw ecosystem (OpenClaw, IronClaw, etc.) made great strides in personal AI assistants, but they all share the same DNA: **single-user tools bolted onto chat channels**.

Open Intern is built differently:

| What Others Do | What Open Intern Does |
|---|---|
| Personal assistant for one user | **Team member** visible to everyone |
| Stateless or session-scoped memory | **3-layer organizational memory** (org / channel / personal) with pgvector |
| Wait for commands | **Proactive heartbeat** — scans for unread mentions, overdue tasks, anomalies |
| API key integrations | **Own identity** — real email, real accounts, real OAuth tokens |
| Config files and CLI flags | **Web Dashboard** — non-technical admins can configure everything |
| "Works on my machine" | **Docker one-command deploy** with PostgreSQL + pgvector included |

---

## How It Compares

<table>
<thead>
<tr>
<th></th>
<th align="center"><strong>Open Intern</strong></th>
<th align="center">OpenClaw</th>
<th align="center">IronClaw</th>
</tr>
</thead>
<tbody>
<tr><td><strong>Target User</strong></td>
<td align="center">Teams & enterprises</td>
<td align="center">Individual power users</td>
<td align="center">Privacy-focused individuals</td></tr>

<tr><td><strong>Language</strong></td>
<td align="center">Python (FastAPI + LangGraph)</td>
<td align="center">TypeScript (Node.js)</td>
<td align="center">Rust</td></tr>

<tr><td><strong>Organizational Memory</strong></td>
<td align="center">3-layer isolated (org/channel/personal) with pgvector</td>
<td align="center">Per-user, flat</td>
<td align="center">Hybrid full-text + vector, single-user</td></tr>

<tr><td><strong>Proactive Initiative</strong></td>
<td align="center">Heartbeat loop with proactivity budget</td>
<td align="center">No</td>
<td align="center">Heartbeat (basic)</td></tr>

<tr><td><strong>Safety & Permissions</strong></td>
<td align="center">Action classification + human approval + audit trail</td>
<td align="center">Minimal</td>
<td align="center">WASM sandbox + endpoint allowlisting</td></tr>

<tr><td><strong>Web Dashboard</strong></td>
<td align="center">Full admin UI (Next.js)</td>
<td align="center">Community panels (3rd-party)</td>
<td align="center">No</td></tr>

<tr><td><strong>Multi-Platform IM</strong></td>
<td align="center">Lark, Discord, Slack (enterprise-grade adapters)</td>
<td align="center">20+ channels (frequently breaking)</td>
<td align="center">REPL, HTTP, Telegram, Slack</td></tr>

<tr><td><strong>Self-Hosted</strong></td>
<td align="center">Docker Compose, one command</td>
<td align="center">Manual Node.js setup</td>
<td align="center">Docker or Cargo build</td></tr>

<tr><td><strong>Multi-Agent</strong></td>
<td align="center">Coordinated agents with claim mechanism</td>
<td align="center">Multi-agent routing (nascent)</td>
<td align="center">Parallel jobs (isolated)</td></tr>

<tr><td><strong>Telemetry</strong></td>
<td align="center">Zero</td>
<td align="center">Opt-out</td>
<td align="center">Zero</td></tr>

<tr><td><strong>Stability</strong></td>
<td align="center">Production-grade FastAPI</td>
<td align="center">Frequent gateway restarts, memory leaks (15K+ open issues)</td>
<td align="center">Early stage (~7 weeks old)</td></tr>
</tbody>
</table>

**TL;DR:**
- **OpenClaw** = Swiss Army knife for personal AI, massive ecosystem, but unstable at scale and not team-aware
- **IronClaw** = Security-first rewrite in Rust, great sandbox model, but brand new and single-user
- **Open Intern** = Enterprise AI employee — team-first, admin-friendly, production-stable, with organizational memory and proactive initiative

---

## Quick Start

```bash
# Clone
git clone https://github.com/user/open_intern.git
cd open_intern

# Start everything (PostgreSQL + pgvector + agent)
docker compose up -d

# Initialize
open_intern init
# → Choose platform: Lark / Discord / Slack / Web-only
# → Enter credentials
# → Pick agent name & role

# Launch
open_intern start

# Open dashboard
open http://localhost:3000
```

That's it. Your AI employee is online.

<details>
<summary><strong>Development setup (without Docker)</strong></summary>

```bash
# Requires: uv (https://docs.astral.sh/uv/), PostgreSQL with pgvector

# Install dependencies
uv sync --all-extras

# Configure
cp .env.example .env
# Edit .env with your API keys and DATABASE_URL

# Start backend (port 8000)
open_intern start --web

# Start frontend (port 3000)
cd web && npm install && npm run dev
```

</details>

---

## Architecture

```
                          ┌──────────────────────────────┐
                          │       Web Dashboard          │
                          │   (Next.js + Tailwind)       │
                          │   Agent config, logs, usage  │
                          └──────────────┬───────────────┘
                                         │ REST API
┌────────────────────────────────────────┼────────────────────────────────────┐
│                            FastAPI Backend                                  │
│                                                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────────────────────────┐  │
│  │  Lark   │  │ Discord │  │  Slack  │  │     Safety Middleware        │  │
│  │ Adapter │  │ Adapter │  │ Adapter │  │  ┌────────┐ ┌────────────┐  │  │
│  └────┬────┘  └────┬────┘  └────┬────┘  │  │ Perms  │ │ Audit Log  │  │  │
│       │            │            │        │  │ Engine │ │ (JSONL)    │  │  │
│       └────────────┴────────────┘        │  └────────┘ └────────────┘  │  │
│                    │                     └──────────────────────────────┘  │
│                    ▼                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    Agent Core (LangGraph + Deep Agents)             │  │
│  │                                                                     │  │
│  │  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────────┐  │  │
│  │  │ Identity │  │ Heartbeat │  │ Planner  │  │  LLM Providers   │  │  │
│  │  │ Manager  │  │   Loop    │  │          │  │ Claude / OpenAI  │  │  │
│  │  └──────────┘  └───────────┘  └──────────┘  │ MiniMax / Ollama │  │  │
│  │                                              └──────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                    │                                                       │
│  ┌─────────────────▼───────────────────────────────────────────────────┐  │
│  │              Memory System (PostgreSQL + pgvector)                   │  │
│  │                                                                     │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │  │
│  │  │   Shared     │  │   Channel    │  │   Personal   │              │  │
│  │  │  (Org-wide)  │  │  (Per-team)  │  │    (DMs)     │              │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘              │  │
│  │                                                                     │  │
│  │  Semantic search · Importance decay · Access control boundaries     │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Design Pillars

| # | Pillar | What It Means |
|---|--------|---------------|
| 1 | **Root Identity** | The agent has its own email, chat profile, and OAuth tokens. It exists as a real person in your org — not a bot API wrapper. |
| 2 | **Proactive Heartbeat** | Wakes up periodically, scans for unread mentions, overdue tasks, and anomalies. Acts within a configurable proactivity budget so it's helpful without being annoying. |
| 3 | **3-Layer Memory** | Shared (company-wide), Channel (team/project), Personal (DM). Information boundaries are enforced — DMs never leak to public channels. |
| 4 | **Enterprise Safety** | Every action is classified (auto-allow / require-approval / deny). Full audit trail. Configurable approval workflows. |
| 5 | **Admin Dashboard** | Non-technical team leads can configure identity, permissions, LLM provider, and integrations from a web UI — no YAML editing required. |

---

## Key Differentiators

### vs. OpenClaw: Stability + Team Awareness

OpenClaw is a powerful personal assistant with 20+ channel integrations and a massive skill ecosystem. But it was built for **individual users**, and it shows:

- **Gateway restarts every ~50 minutes** ([#48205](https://github.com/openclaw/openclaw/issues/48205)), memory leaks on basic operations, 15K+ open issues
- No concept of organizational memory — your agent doesn't know what happened in channels it wasn't directly messaged in
- No admin dashboard — configuration requires CLI expertise
- Channels frequently break after updates

Open Intern trades breadth for depth: fewer integrations, but each one is **production-stable**. Team-scoped memory means your AI employee builds context the way a real colleague would.

### vs. IronClaw: Maturity + Team-First Design

IronClaw (by NEAR AI) is an impressive security-focused rewrite in Rust with WASM sandboxing and credential protection. But it's **7 weeks old** and designed as a personal tool:

- Single-user architecture — no organizational memory layers
- No web dashboard — Rust CLI only
- Limited channel support (REPL, HTTP, Telegram, Slack)
- Still building core features (multi-tenant isolation in progress)

Open Intern shares IronClaw's commitment to security (zero telemetry, full audit trail, permission-gated actions) but wraps it in a **team-ready, admin-friendly** package with a mature Python ecosystem.

---

## Features

### Core (Shipping Now)

- **Multi-platform IM** — Lark (Feishu), Discord, Slack adapters with thread support
- **Web Dashboard** — Configure agent identity, LLM provider, permissions, and integrations from a browser
- **Persistent Memory** — PostgreSQL + pgvector with 3-layer isolation (shared / channel / personal)
- **Configurable Persona** — Name, role, personality, expertise areas, communication style
- **LLM Provider Abstraction** — Claude, GPT-4, MiniMax, Ollama — switch with one config change
- **Safety Middleware** — Action classification, human approval workflows, JSONL audit logging
- **Sandbox File Browser** — Browse, read, edit, and create files in the agent's E2B sandbox from the dashboard
- **CLI** — `open_intern init`, `start`, `status`, `logs`, `chat`
- **Docker Compose** — One-command deploy with PostgreSQL + pgvector

### Coming Next

- **Proactive Heartbeat** — periodic scanning with configurable proactivity budget and quiet hours
- **Knowledge Ingestion** — Notion, GitHub, Markdown docs into RAG pipeline
- **Email Identity** — own Gmail/SMTP for sending client-facing emails
- **GitHub Integration** — PR review, issue triage, branch management
- **Multi-Agent Coordination** — claim mechanism, loop detection, shared context
- **Calendar Awareness** — meeting prep, scheduling, follow-up automation

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Backend** | Python 3.11+ · FastAPI · LangGraph · Deep Agents | Production-grade async framework with the largest AI/ML ecosystem |
| **Frontend** | Next.js 16 · React 19 · Tailwind CSS 4 | Modern admin dashboard with server components |
| **Database** | PostgreSQL 17 + pgvector | Structured data + vector search in one DB — no extra infra |
| **LLM** | Claude · GPT-4 · MiniMax · Ollama | Pluggable providers, local model support for air-gapped deployments |
| **IM** | Lark SDK · discord.py · Slack Bolt | Native SDKs for reliable, maintained integrations |
| **CLI** | Typer + Rich | Developer-friendly with beautiful terminal output |
| **Deploy** | Docker Compose | One-command production-ready deployment |

---

## Project Structure

```
open_intern/
├── core/                  # Agent brain — orchestrator, config, identity, LLM providers
│   ├── agent.py           # LangGraph + Deep Agents pipeline
│   ├── config.py          # Pydantic config models
│   └── identity.py        # System prompt builder
├── memory/
│   └── store.py           # PostgreSQL + pgvector memory (3-layer isolation)
├── safety/
│   └── permissions.py     # Action approval system (allow / deny / ask)
├── integrations/
│   ├── base.py            # Platform adapter interface
│   ├── lark/              # Lark (Feishu) bot
│   ├── discord/           # Discord bot
│   └── slack/             # Slack bot
├── api/
│   └── dashboard.py       # Dashboard REST API
├── cli/
│   └── main.py            # Typer CLI
├── skills/                # Extensible agent skills
├── web/                   # Next.js dashboard (React 19 + Tailwind)
├── server.py              # FastAPI app factory
├── docker-compose.yml     # PostgreSQL + agent — one command
├── pyproject.toml         # Dependencies (managed by uv)
└── uv.lock                # Reproducible installs
```

---

## Security & Compliance

Open Intern is built for teams that handle sensitive data:

- **Zero telemetry** — no data ever leaves your infrastructure
- **Self-hosted only** — runs on your servers, your cloud, your rules
- **Action-level permissions** — every capability is classified as auto-allow, require-approval, or deny
- **Full audit trail** — every agent action logged with reasoning chain, context retrievals, and confidence score
- **Memory isolation** — 3-layer boundary enforcement ensures DMs never leak to shared context
- **Encrypted credentials** — API keys and OAuth tokens encrypted at rest
- **No vendor lock-in** — swap LLM providers without changing a line of application code

---

## Configuration

Agent configuration is managed through the **Web Dashboard** and stored in PostgreSQL — no YAML files to manage, no config drift between environments.

Environment-level settings (API keys, database URL) use `.env`:

```bash
# .env
DATABASE_URL=postgresql://user:pass@localhost:5556/open_intern
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# See .env.example for all options
```

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Dashboard Guide](docs/dashboard_guide.md) | Complete walkthrough of every dashboard page — agents, chat, memories, skills, usage, admin |
| [Agent Settings](docs/agent_settings.md) | Configure identity, LLM model, platform connections, sandbox, and API keys |
| [Sandbox File Browser](docs/file_browser.md) | Browse, read, edit, and create files in the agent's E2B sandbox |
| [Lark Bot Setup](docs/lark_setting.md) | Create a Lark (Feishu) bot app, configure permissions, and connect it |

---

## Contributing

We welcome contributions in these areas:

1. **Integration adapters** — add support for Teams, Telegram, LINE, DingTalk, WeCom
2. **Memory system** — improve retrieval quality, boundary classification, importance decay
3. **Skills** — new agent capabilities (Linear, Jira, HubSpot, Notion, etc.)
4. **Dashboard** — new admin features, analytics, usage visualization
5. **Documentation** — setup guides, architecture deep-dives, deployment tutorials

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow and standards.

---

## License

MIT — use it however you want, commercially or otherwise.

---

<p align="center">
  <img src="docs/images/avatar.png" alt="Open Intern" width="48" style="border-radius: 50%;"/>
  <br/>
  <sub>Built with conviction that AI employees should work <em>for</em> the team, not just <em>with</em> one person.</sub>
</p>
