# open_intern

An open-source AI employee that joins your team as a real teammate — not a chatbot, not a task runner, but a persistent colleague with its own identity, organizational memory, and initiative.

---

## Why This Exists

Most AI tools are **reactive** — you prompt, they respond, context is gone. open_intern is different:

- It **lives** in your team chat (Lark, Discord, Slack) as a real member, not a sidebar widget
- It **remembers** your org — decisions from 3 months ago, who owns what, how things work
- It **acts on its own** — posts daily summaries, flags anomalies, follows up on stalled tasks
- It has its **own identity** — email, chat profile, tool accounts

The difference between a chatbot and an AI employee is the same as the difference between Google Search and a new hire. One answers questions. The other gets work done.

---

## Core Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     open_intern                         │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │Heartbeat │  │ Planner  │  │ Identity │              │
│  │  Loop    │──│          │──│ Manager  │              │
│  └────┬─────┘  └────┬─────┘  └──────────┘              │
│       │              │                                   │
│  ┌────▼──────────────▼─────┐  ┌─────────────────────┐  │
│  │    Memory System        │  │   Safety Middleware  │  │
│  │  ┌────────┐ ┌────────┐  │  │  ┌───────────────┐  │  │
│  │  │Shared  │ │Channel │  │  │  │  Permissions   │  │  │
│  │  │(Org)   │ │(Group) │  │  │  │  Read/Write    │  │  │
│  │  └────────┘ └────────┘  │  │  │  Approval      │  │  │
│  │  ┌────────┐ ┌────────┐  │  │  │  Audit Log     │  │  │
│  │  │Personal│ │  RAG   │  │  │  └───────────────┘  │  │
│  │  │(DM)    │ │Retrieval│  │  └─────────────────────┘  │
│  │  └────────┘ └────────┘  │                            │
│  └─────────────────────────┘                            │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Integration Plugins                 │    │
│  │  ┌─────┐ ┌───────┐ ┌──────┐ ┌──────┐ ┌──────┐  │    │
│  │  │Lark │ │Discord│ │Email │ │GitHub│ │Notion │  │    │
│  │  └─────┘ └───────┘ └──────┘ └──────┘ └──────┘  │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### The Five Design Pillars

| # | Pillar | What It Means |
|---|--------|---------------|
| 1 | **Root Identity** | The agent has its own email. With that email, it can sign up for any SaaS tool, send emails to clients, and exist as a real person in your org chart. |
| 2 | **Proactive Heartbeat** | The agent wakes up periodically, scans for unread mentions, overdue tasks, anomalies, and acts. It doesn't wait for you to ask. |
| 3 | **3-Layer Memory** | Shared (company-wide knowledge), Channel (team/project context), Personal (DM-level private context). The hard part: teaching an omniscient agent what to _forget_. |
| 4 | **Multi-Agent Collaboration** | Multiple AI employees can coordinate, onboard each other, and hand off work — supervised by humans. |
| 5 | **Standard Tool Access** | Uses OAuth and real accounts to access tools the way a human would. Not special API integrations — actual tool usage. |

---

## Features

### MVP (Phase 1-2)

- [x] Project research and architecture design
- [ ] **Lark Bot** — joins your Lark workspace as a team member, responds in threads, handles mentions
- [ ] **Discord Bot** — joins your Discord server, responds in channels and threads
- [ ] **Persistent Memory** — remembers conversations across sessions (PostgreSQL-backed)
- [ ] **Configurable Persona** — YAML-based identity: name, role, personality, expertise areas
- [ ] **LLM Provider Abstraction** — Claude, OpenAI, or local models (Ollama/vLLM)
- [ ] **Basic Safety Layer** — read/write permission separation, action audit logging
- [ ] **Knowledge Ingestion** — ingest Notion pages, Markdown docs, GitHub READMEs into RAG
- [ ] **3-Layer Memory Isolation** — shared/channel/personal with access control
- [ ] **Chat History Ingestion** — build organizational context from existing Lark/Discord conversations
- [ ] **CLI** — `open_intern init`, `open_intern start`, `open_intern status`
- [ ] **Docker Compose** — one-command local deployment

### Proactive Agent (Phase 3)

- [ ] **Heartbeat Scheduler** — configurable periodic awareness scanning (default: every 10 min)
- [ ] **Awareness Scanner** — detect unread mentions, new events, overdue items across all integrations
- [ ] **Proactivity Budget** — configurable max unsolicited actions per hour to avoid being overwhelming
- [ ] **Daily Summary** — auto-generated end-of-day digest: what got done, what's stuck, what needs attention
- [ ] **Human Approval Workflow** — chat-based approve/reject for write actions (reactions)
- [ ] **Confidence Threshold** — only act proactively when confidence exceeds configurable threshold

### Full Identity (Phase 4)

- [ ] **Email Identity** — own Gmail/SMTP address, can send/receive/draft emails
- [ ] **GitHub Integration** — review PRs, comment on issues, create branches, push fixes
- [ ] **Calendar Awareness** — know about upcoming meetings, prep context ahead of time
- [ ] **OAuth Connection Manager** — manage credentials for all connected tools
- [ ] **Transparent Audit Trail** — every action logged with reasoning chain, retrievals, and confidence

### Advanced (Phase 5+)

- [ ] **Multi-Agent Coordination** — multiple AI employees with claim mechanism and loop detection
- [ ] **Meeting Participation** — join Zoom/Meet calls via transcription, take notes, send follow-ups
- [ ] **Browser Automation** — Playwright-based web research, competitor analysis, product sign-up
- [ ] **Web Dashboard** — visual management panel for non-technical users
- [ ] **Slack Integration** — Slack Bot support for teams using Slack
- [ ] **Plugin Marketplace** — community-contributed integrations (Linear, Jira, HubSpot, etc.)

---

## Project Structure

```
open_intern/
├── core/
│   ├── agent.py              # Main agent orchestrator — the brain
│   ├── heartbeat.py          # Periodic wake-up and awareness scanning
│   ├── planner.py            # Task decomposition and prioritization
│   ├── identity.py           # Agent identity (name, email, persona)
│   └── llm/
│       ├── provider.py       # Abstract LLM interface
│       ├── claude.py         # Claude API implementation
│       ├── openai.py         # OpenAI API implementation
│       └── local.py          # Ollama/vLLM local model support
├── memory/
│   ├── store.py              # Abstract memory storage interface
│   ├── layers.py             # Shared/Channel/Personal layer logic
│   ├── retrieval.py          # RAG retrieval with relevance scoring
│   ├── ingestion.py          # Document chunking and embedding pipeline
│   └── access_control.py     # Who can see what memory, boundary enforcement
├── safety/
│   ├── permissions.py        # Action classification (read/write/destructive)
│   ├── approval.py           # Human-in-the-loop approval workflow
│   ├── audit.py              # Action logging for transparency
│   └── boundaries.py         # Information boundary enforcement
├── integrations/
│   ├── base.py               # Integration plugin interface (connect/scan/execute/ingest)
│   ├── lark/
│   │   ├── bot.py            # Lark (Feishu) bot setup
│   │   ├── events.py         # Message, mention, reaction handlers
│   │   └── memory_sync.py    # Lark history → memory ingestion
│   ├── discord/
│   │   ├── bot.py            # Discord bot (discord.py)
│   │   ├── events.py         # Message, mention, reaction handlers
│   │   └── memory_sync.py    # Discord history → memory ingestion
│   ├── slack/
│   │   ├── bot.py            # Slack Bolt bot (lower priority)
│   │   ├── events.py         # Message, mention, reaction handlers
│   │   └── memory_sync.py    # Slack history → memory ingestion
│   ├── github/
│   │   ├── webhooks.py       # PR/issue event handling
│   │   └── actions.py        # Review, comment, create PR
│   ├── email/
│   │   ├── identity.py       # Email account management
│   │   └── handler.py        # Send/receive/draft
│   ├── notion/
│   │   └── sync.py           # Page reading and knowledge sync
│   └── calendar/
│       └── sync.py           # Meeting awareness
├── skills/
│   ├── base.py               # Skill interface (tool-use pattern)
│   ├── research.py           # Web research and competitor analysis
│   ├── summarize.py          # Summarization and daily digests
│   ├── code_review.py        # PR review and bug detection
│   └── writing.py            # Content drafting
├── config/                      # (reserved for future use)
├── cli/
│   ├── main.py               # CLI entry point
│   ├── setup.py              # Interactive setup wizard
│   └── monitor.py            # Status, logs, cost tracking
├── docker-compose.yml        # PostgreSQL + Agent
├── RESEARCH.md               # Deep product research and analysis
└── README.md                 # This file
```

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Language | Python 3.11+ | Largest AI/ML ecosystem, most contributors |
| LLM | Claude / OpenAI / Ollama (pluggable) | Flexibility, local model support for privacy |
| Memory DB | PostgreSQL + pgvector | Structured data + vector search in one DB |
| Task Queue | APScheduler | Heartbeat scheduling, background processing |
| Chat (Primary) | Lark (Feishu) Open API | Rich bot API, widely used in Asia-Pacific teams |
| Chat (Secondary) | discord.py | Massive developer community, easy bot setup |
| Chat (Tertiary) | Slack Bolt SDK | Enterprise standard, lower priority |
| Email | Gmail API / SMTP | Identity-based email access |
| RAG | LlamaIndex or custom pipeline | Document ingestion and retrieval |
| Browser | Playwright | Web automation for research tasks |
| Deployment | Docker Compose | One-command local setup |
| CLI | Click / Typer | Developer-friendly CLI |

---

## Key Technical Challenges

### 1. Proactive Without Being Annoying

Early adopters of AI employees have reported that overly proactive agents led teams to create "human only" channels. Our solution:

- **Proactivity budget**: max N unsolicited actions per hour (default: 3)
- **Confidence threshold**: only act when confidence > 0.8
- **Escalation tiers**: low-confidence → daily digest, high-confidence → immediate message
- **Feedback loop**: message reactions (thumbs up/down) calibrate future behavior
- **Quiet hours**: configurable do-not-disturb windows
- **Channel opt-in/out**: per-channel proactivity toggle

### 2. Memory That Doesn't Leak

The 3-layer isolation model must enforce real information boundaries:

- **DMs are always Personal** — never surfaced in public channels
- **Public channels are Channel-scoped** — accessible in that channel's context only
- **Org-wide docs are Shared** — accessible everywhere
- **LLM-assisted classification** for ambiguous cases
- **User override**: "forget this" / "this is org-wide knowledge"

### 3. Cost Control

A heartbeat every 5 minutes with full RAG retrieval could burn $100+/day. Solutions:

- **Small model for triage** (decide whether to engage), large model for actual work
- **Configurable cost budget** with automatic throttling
- **Token usage tracking** visible in CLI (`open_intern costs`)
- **Aggressive context caching**
- **Lazy retrieval**: check relevance before pulling full documents

### 4. Multi-Agent Safety

When multiple AI employees coexist:

- **Claim mechanism**: agent marks a task as "working on it" to prevent duplication
- **Loop detection**: message chain depth limit prevents infinite A→B→A cycles
- **Separate memory namespaces** with explicit sharing controls

---

## Quick Start (Target)

```bash
# Clone and start infrastructure
git clone https://github.com/user/open_intern.git
cd open_intern
docker compose up -d

# Initialize your AI employee
open_intern init
# → Choose platform: Lark / Discord / Slack
# → Enter Bot Token / App credentials
# → Enter LLM API Key (Claude/OpenAI)
# → Choose agent name and role

# Start your AI employee
open_intern start

# Check status
open_intern status

# View what your agent has been doing
open_intern logs

# See token costs
open_intern costs
```

---

## Configuration Example

Agent configuration (identity, platform credentials, LLM provider, safety rules) is managed through the **Web Dashboard UI** and stored in PostgreSQL. Environment-level settings (DATABASE_URL, API keys) go in `.env`.

---

## Roadmap

| Phase | Timeline | Goal | Key Deliverable |
|-------|----------|------|-----------------|
| **1** | Weeks 1-3 | Living Agent | Lark/Discord bot with persistent memory and configurable persona |
| **2** | Weeks 4-6 | Org Brain | Knowledge ingestion (Notion, GitHub), 3-layer memory, RAG |
| **3** | Weeks 7-9 | Proactive | Heartbeat loop, daily summaries, human approval workflow |
| **4** | Weeks 10-12 | Full Identity | Email identity, GitHub integration, calendar awareness |
| **5** | Ongoing | Community | Multi-agent, meetings, browser automation, web dashboard |

---

## How It Compares

| Feature | open_intern | LangChain Agent | Devin | ChatGPT |
|---------|-------------|-----------------|-------|---------|
| Persistent identity | Yes | No | No | No |
| Organizational memory | 3-layer isolated | Manual RAG | Codebase only | Per-conversation |
| Proactive initiative | Heartbeat loop | No | No | No |
| Multi-person collaboration | Team-wide | Single user | Single user | Single user |
| Self-hosted | Yes | Yes | No | No |
| Tool access via own accounts | Yes | Via API keys | Limited | No |
| Remembers across sessions | Yes | Manual | Limited | Limited |

---

## Contributing

This project is in early development. Key areas where contributions are welcome:

1. **Integration plugins** — add support for Linear, Jira, HubSpot, Telegram, etc.
2. **Memory system** — improve retrieval quality, boundary classification
3. **Heartbeat tuning** — better heuristics for when to act vs. stay quiet
4. **Local model support** — optimize prompts and memory for smaller models
5. **Documentation** — setup guides, architecture docs, tutorials

---

## License

MIT

---

## Acknowledgments

This project is built on the open-source community's contributions to AI agent tooling and infrastructure.
