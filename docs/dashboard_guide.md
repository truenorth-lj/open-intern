# Dashboard Guide

The Open Intern dashboard is a web UI for managing agents, chatting, viewing memories, monitoring token usage, and administering users.

## Login

Navigate to your deployment URL (e.g. `https://your-domain.com`). Enter the admin email and password configured during setup.

- **Admin** accounts have full access to all features.
- **User** accounts can only access agents assigned to them.

## Navigation

The left sidebar has two sections:

**Global navigation** (always visible):
- **Agents** — list and manage all agents
- **Usage** — token usage analytics
- **Settings** — system-wide default API key
- **Admin** — user management (admin only)

**Agent navigation** (visible when inside an agent):
- **Chat** — send messages and view threads
- **Memories** — browse stored memories
- **Skills** — view loaded agent skills
- **Files** — browse the agent's sandbox filesystem
- **Scheduled Jobs** — manage cron and interval tasks

---

## Agents

The Agents page shows all configured agents as cards. Each card displays:

- Agent name, ID, and status badge (Active / Inactive)
- Role and LLM provider/model
- Connected platforms (Telegram, Discord, Lark)
- Quick actions: **Chat**, **Settings**, **Deactivate**

Click **Create Agent** (admin only) to add a new agent.

<!-- screenshot: agents list page showing agent cards -->

---

## Chat

The Chat page is a real-time messaging interface with the agent.

**Left panel**: Thread history sidebar
- Click **+ New Chat** to start a new conversation
- Click any thread to resume it
- Hover a thread to rename or delete it

**Main area**: Message input and response stream
- Type a message and press **Enter** to send
- Responses stream in real-time with token-by-token display
- Tool usage is shown as status indicators during processing

Click **Reload** at the top to reload the agent runtime (useful after config changes).

<!-- screenshot: chat page with thread sidebar and message area -->

---

## Memories

The Memories page shows all stored memories for the agent, organized by scope.

**Scope tabs**:
- **All** — show everything
- **Shared** — organization-wide memories visible to all agents
- **Channel** — channel/group-specific memories
- **Personal** — private DM memories

Each memory row shows: content preview, scope badge, source (web/lark/telegram), date, and a **Delete** button.

Pagination at the bottom (20 items per page). The top-right shows total counts by scope.

<!-- screenshot: memories page with scope tabs and table -->

---

## Skills

The Skills page lists all skills loaded into the agent's sandbox.

Each skill card shows:
- **Name** and version badge
- **Category** badge (data, devops, meta, etc.)
- Description of what the skill does
- Tools it uses, number of files, last updated date
- **Details** button to expand and view the full skill instructions

<!-- screenshot: skills page with skill cards -->

---

## Files

See [Sandbox File Browser](file_browser.md) for detailed documentation.

Browse, read, edit, and create files in the agent's E2B sandbox. Requires sandbox mode to be enabled (base or desktop).

<!-- screenshot: file browser with directory listing and file editor -->

---

## Scheduled Jobs

The Scheduled Jobs page manages automated recurring tasks for the agent.

Jobs are created via chat (e.g. "remind me every day at 9am") and can be:
- **Cron** — runs on a cron schedule (e.g. `0 9 * * *`)
- **Interval** — runs every N minutes/hours
- **Once** — runs at a specific time

Each job row shows: name, schedule, status, last run, next run, and error count.

**Actions per job**:
- **Pause** / **Resume** — temporarily disable/enable
- **Trigger** — run immediately
- **Delete** — remove with confirmation

Click **Settings** at the top-right to configure the job system.

<!-- screenshot: scheduled jobs page with job list -->

---

## Token Usage

The Usage page tracks LLM token consumption across all agents.

**Summary cards** (top): one card per agent showing:
- Total tokens (input + output)
- Request count
- Color-coded dot for the timeseries chart

**All Agents** card: aggregate totals.

**Usage Over Time** chart (bottom):
- Timeseries line chart showing daily token usage
- **Time Range** filter: 7D, 14D, 30D, 90D, or Custom date range
- **Agent** filter: view all agents or a specific one
- Legend shows each agent's color

<!-- screenshot: usage page with summary cards and timeseries chart -->

---

## Settings (Global)

The global Settings page (sidebar > Settings) configures system-wide defaults:

- **Default LLM API Key** — fallback API key used by agents that don't have their own key set

---

## Admin

The Admin page (admin only) manages dashboard users.

**Create User**: enter an email and click **Create User**. A temporary password is generated.

**User list**: shows all users with:
- Email, role badge (admin / user), status badge (Active / Inactive)
- **Agent Access** — which agents this user can see (or "all")
- **Reset Password** — generate a new temporary password
- **Deactivate** / **Activate** — toggle user access
- **Edit** — change agent access permissions
