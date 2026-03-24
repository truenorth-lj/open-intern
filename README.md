<p align="center">
  <img src="docs/images/avatar.png" alt="Open Intern" width="100"/>
</p>

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

**Open Intern** is an enterprise-grade, self-hosted AI employee that joins your team as a real colleague — not a chatbot widget, not a personal assistant, but a persistent team member with its own identity, organizational memory, and the judgment to act on its own.

Think of it as hiring an AI that actually *works here*.

> Built for teams that need the power of AI agents with the security and control of on-premise software. If OpenClaw is the personal AI assistant and IronClaw is the security-hardened CLI, **Open Intern is the enterprise AI teammate** — deployed on your infra, governed by your policies, embedded in your workflows.

---

## Why Open Intern

### The Problem with Traditional AI Agents

Most AI agent platforms today — including the popular Claw ecosystem (OpenClaw, IronClaw, etc.) — share the same fundamental flaw: **they're single-machine, single-user tools that tie up an entire server just to run one agent**.

This creates real problems at scale:

- **Wasted resources** — your agent idles 90% of the time, but the server (and your bill) runs 24/7
- **Can't scale** — need 10 agents? Spin up 10 servers. Need 2 tomorrow? Too bad, you're already paying for 10
- **Coupled architecture** — the agent runtime, filesystem, and infrastructure are tightly bound. Swapping providers means rewriting everything
- **No isolation** — the agent runs on the same machine as your data, with full filesystem access. One bad tool call and it's reading your `.env`

### How Open Intern is Different

Open Intern was designed from the ground up to solve these problems:

| Traditional Agents | Open Intern |
|---|---|
| One agent = one dedicated server | **Multi-agent on one service** — manage all agents from a single dashboard |
| Idle servers burning money 24/7 | **Elastic scaling** — spin up sandboxes on demand, scale to zero when idle |
| Agent has full filesystem access | **Sandboxed runtime** — agent never touches your host machine or private data |
| Locked to one infra provider | **Pluggable filesystem** — swap between E2B, Fly.io, Cloudflare, or local Docker |
| Stateless or session-scoped memory | **3-layer organizational memory** (org / channel / personal) with pgvector |
| Wait for commands | **Proactive heartbeat** — scans for unread mentions, overdue tasks, anomalies |
| Config files and CLI flags | **Web Dashboard** — non-technical admins can configure everything |

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

<tr><td><strong>Runtime Isolation</strong></td>
<td align="center">Sandboxed (E2B / Fly / Cloudflare / Docker)</td>
<td align="center">Runs on host machine</td>
<td align="center">WASM sandbox (single process)</td></tr>

<tr><td><strong>Scalability</strong></td>
<td align="center">Elastic — scale to zero, burst on demand</td>
<td align="center">One server per agent</td>
<td align="center">One server per agent</td></tr>

<tr><td><strong>Telemetry</strong></td>
<td align="center">Zero</td>
<td align="center">Opt-out</td>
<td align="center">Zero</td></tr>

<tr><td><strong>Stability</strong></td>
<td align="center">Production-grade FastAPI</td>
<td align="center">Frequent gateway restarts, memory leaks (15K+ open issues)</td>
<td align="center">Early stage (launched early 2026)</td></tr>

<tr><td><strong>Agent Framework</strong></td>
<td align="center"><a href="https://python.langchain.com/docs/concepts/agents/#deep-agents">LangChain Deep Agents</a></td>
<td align="center">Custom gateway</td>
<td align="center">Custom Rust runtime</td></tr>
</tbody>
</table>

**TL;DR:**
- **OpenClaw** = Swiss Army knife for personal AI, massive ecosystem, but unstable at scale, no isolation, and not team-aware
- **IronClaw** = Security-first rewrite in Rust, great sandbox model, but still early and single-user
- **Open Intern** = Enterprise AI employee — decoupled architecture, elastic scaling, sandboxed runtime, team-first, with organizational memory and a unified multi-agent dashboard

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
                          │   Multi-agent management     │
                          └──────────────┬───────────────┘
                                         │ REST API
┌────────────────────────────────────────┼────────────────────────────────────┐
│                     Harness (FastAPI Backend)                                │
│                                                                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────────────────────────┐  │
│  │  Lark   │  │ Discord │  │  Slack  │  │     Safety Middleware        │  │
│  │ Adapter │  │ Adapter │  │ Adapter │  │  Permissions · Audit Log     │  │
│  └────┬────┘  └────┬────┘  └────┬────┘  └──────────────────────────────┘  │
│       └────────────┴────────────┘                                          │
│                    │                                                        │
│  ┌─────────────────▼─────────────────────────────────────────────────────┐ │
│  │            Agent Core (LangChain Deep Agents + LangGraph)             │ │
│  │                                                                       │ │
│  │  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌────────────────────┐  │ │
│  │  │ Identity │  │ Heartbeat │  │ Planner  │  │   LLM Providers    │  │ │
│  │  │ Manager  │  │   Loop    │  │          │  │ Claude / OpenAI /  │  │ │
│  │  └──────────┘  └───────────┘  └──────────┘  │ MiniMax / Ollama   │  │ │
│  │                                              └────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                    │                                                        │
│  ┌─────────────────▼─────────────────────────────────────────────────────┐ │
│  │              Memory System (PostgreSQL + pgvector)                     │ │
│  │  Shared (Org) · Channel (Team) · Personal (DM) · Semantic search     │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ Abstracted filesystem API
                ┌──────────────▼──────────────────────┐
                │      Sandbox Runtime (isolated)      │
                │                                      │
                │  ┌────────┐ ┌────────┐ ┌──────────┐ │
                │  │  E2B   │ │ Fly.io │ │Cloudflare│ │
                │  └────────┘ └────────┘ └──────────┘ │
                │  ┌────────┐                          │
                │  │ Docker │  (pluggable backends)    │
                │  └────────┘                          │
                └──────────────────────────────────────┘
```

### Design Pillars

| # | Pillar | What It Means |
|---|--------|---------------|
| 1 | **Decoupled Runtime** | Agent logic, harness, and sandbox are cleanly separated. Swap sandbox providers (E2B, Fly, Cloudflare, Docker) without touching agent code. |
| 2 | **Sandboxed by Default** | Agents execute in isolated environments. They never access your host filesystem or private data — secrets stay in the harness. |
| 3 | **Elastic Scaling** | Sandboxes provision on demand and pause when idle. Run 1 agent or 100 — pay only for what you use. |
| 4 | **3-Layer Memory** | Shared (company-wide), Channel (team/project), Personal (DM). Information boundaries are enforced — DMs never leak to public channels. |
| 5 | **Multi-Agent Dashboard** | Create, configure, and monitor all your agents from a single web UI. Each agent has its own identity, LLM config, and sandbox — fully isolated, centrally managed. |
| 6 | **Enterprise Safety** | Every action is classified (auto-allow / require-approval / deny). Full audit trail. Configurable approval workflows. |

---

## Key Differentiators

### 1. Decoupled Architecture — Runtime, Harness, and Infrastructure are Separate

Most agent frameworks tightly couple the agent logic, filesystem, and infrastructure into one monolithic process. Open Intern cleanly separates them:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐
│   Harness    │     │  Agent Core  │     │   Sandbox Runtime    │
│  (FastAPI +  │────▶│  (LangChain  │────▶│  (E2B / Fly.io /    │
│  Dashboard)  │     │ Deep Agents) │     │  Cloudflare / Docker)│
└──────────────┘     └──────────────┘     └──────────────────────┘
      │                                            │
      │           ┌──────────────┐                 │
      └──────────▶│  PostgreSQL  │◀────────────────┘
                  │  + pgvector  │
                  └──────────────┘
```

- **Filesystem is abstracted** — swap between [E2B](https://e2b.dev), [Fly.io](https://fly.io), Cloudflare Workers, or local Docker without changing agent code
- **Agent never touches your host** — all execution happens in isolated sandboxes. No accidental `.env` reads, no filesystem leaks
- **Harness is stateless** — scale the API layer independently of the agent runtimes

### 2. Elastic Scaling — Pay for What You Use

Traditional single-machine agents waste resources:

> Run 5 agents → need 5 servers → 4 sit idle most of the day → you're still paying for all 5.

Open Intern flips this model. Agent sandboxes are **provisioned on demand** and **suspended when idle**:

- Need 1 agent today, 20 tomorrow? Just create them in the dashboard — infrastructure scales automatically
- Idle agents consume **zero compute** (sandbox pauses, R2 backup preserves state)
- Burst capacity is limited only by your sandbox provider, not pre-provisioned hardware

### 3. Multi-Agent Management — One Dashboard to Rule Them All

Other platforms require a separate deployment per agent. Open Intern runs **all your agents in a single service** with a unified dashboard:

- Create, configure, and monitor multiple agents from one UI
- Each agent has its own identity, persona, LLM config, and sandbox — fully isolated
- Shared infrastructure (database, API, platform adapters) means lower overhead per agent

### 4. Powered by LangChain Deep Agents

Open Intern's agent core is built on [**LangChain Deep Agents**](https://python.langchain.com/docs/concepts/agents/#deep-agents) — a production-grade framework for agents that can reason over long horizons, use tools, and maintain state across complex multi-step tasks. This means:

- Battle-tested tool-calling and reasoning loop
- Native support for streaming, retries, and structured outputs
- Compatible with the entire LangChain ecosystem (retrievers, tools, callbacks)

### vs. OpenClaw

OpenClaw is a powerful personal assistant with 20+ channel integrations and a massive skill ecosystem. But it was built for **individual users**, and it shows:

- Gateway restarts every ~50 minutes, memory leaks on basic operations, 15K+ open issues
- No runtime isolation — agent runs on your host with full filesystem access
- No concept of organizational memory or multi-agent management
- Channels frequently break after updates

Open Intern trades breadth for depth: fewer integrations, but each one is **production-stable**, with proper sandboxing and team-scoped memory.

### vs. IronClaw

IronClaw (by NEAR AI) is an impressive security-focused rewrite in Rust with WASM sandboxing and credential protection. It's still a relatively new project and designed as a personal tool:

- Single-user architecture — no organizational memory layers or multi-agent dashboard
- WASM sandbox is elegant but limited to a single process model
- No web dashboard — Rust CLI only
- Still building core features (multi-tenant isolation in progress)

Open Intern shares IronClaw's commitment to security (zero telemetry, full audit trail, permission-gated actions) but wraps it in a **team-ready, elastically scalable** package with a mature Python ecosystem.

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
| **Agent Core** | [LangChain Deep Agents](https://python.langchain.com/docs/concepts/agents/#deep-agents) + LangGraph | Production-grade reasoning loop with tool-calling, streaming, and state management |
| **Backend** | Python 3.11+ · FastAPI | Async-first API harness, decoupled from agent runtime |
| **Frontend** | Next.js 16 · React 19 · Tailwind CSS 4 | Modern multi-agent dashboard with server components |
| **Database** | PostgreSQL 17 + pgvector | Structured data + vector search in one DB — no extra infra |
| **Sandbox** | E2B · Fly.io · Cloudflare · Docker | Pluggable isolated runtimes — agent never touches host |
| **LLM** | Claude · GPT-4 · MiniMax · Ollama | Pluggable providers, local model support for air-gapped deployments |
| **IM** | Lark SDK · discord.py · Slack Bolt | Native SDKs for reliable, maintained integrations |
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

- **Sandboxed execution** — agents run in isolated environments (E2B / Fly / Docker). They never touch your host filesystem or read credentials directly
- **Zero telemetry** — no data ever leaves your infrastructure
- **Self-hosted only** — runs on your servers, your cloud, your rules
- **Action-level permissions** — every capability is classified as auto-allow, require-approval, or deny
- **Full audit trail** — every agent action logged with reasoning chain, context retrievals, and confidence score
- **Memory isolation** — 3-layer boundary enforcement ensures DMs never leak to shared context
- **Encrypted credentials** — API keys and OAuth tokens encrypted at rest, injected at the harness boundary — never exposed to agent code
- **No vendor lock-in** — swap LLM providers or sandbox backends without changing a line of application code

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
