# Agent Settings

The Settings page configures an individual agent's identity, LLM model, platform connections, and sandbox. Access it from **Settings** in the agent sidebar, or click the **Settings** button on any agent card.

Admin users see 4 tabs: **General**, **Model**, **Platforms**, **Desktop**. Regular users only see the API Keys section.

---

## General Tab

Configure the agent's identity:

| Field | Description |
|-------|-------------|
| **Name** | Display name shown in chat and platform messages (e.g. "Rin (TrueNorth) Dev Intern") |
| **Role** | Agent's job title, used in the system prompt (e.g. "AI Employee", "QA Tester") |
| **Personality** | Free-text personality description that shapes how the agent communicates (e.g. "Friendly and helpful.") |

Click **Save Changes** to apply.

<!-- screenshot: settings general tab -->

---

## Model Tab

Configure the LLM provider and sandbox environment.

### Quick Select

Pre-configured model buttons for one-click setup:
- Claude Sonnet 4.6 / Claude Opus 4.6 / Claude Haiku 4.5
- MiniMax M2.7
- OpenAI GPT-4o / OpenAI o3

Clicking a button auto-fills the Provider and Model fields.

### Fields

| Field | Description |
|-------|-------------|
| **Provider** | LLM provider identifier (e.g. `anthropic`, `minimax`, `openai`) |
| **Model** | Specific model name (e.g. `claude-sonnet-4-6-20250514`, `MiniMax-M2.7`) |
| **API Key** | Per-agent LLM API key. Leave blank to use the system default key. |
| **Temperature** | Controls response randomness (0.0 = deterministic, 1.0 = creative). Default: 0.7 |
| **Sandbox** | Execution environment for the agent. Options: |
| | - **None** — no sandbox, agent has no filesystem |
| | - **Base (CLI only)** — E2B cloud microVM with terminal access |
| | - **Desktop (GUI + browser)** — E2B microVM with GUI, browser, and VNC streaming |

Click **Save Changes** to apply. Click **Reload Runtime** at the top to apply changes to the running agent.

<!-- screenshot: settings model tab with quick select buttons -->

---

## Platforms Tab

Connect the agent to messaging platforms. Each platform section has its own credential fields.

### Telegram
- **Bot Token** — from [@BotFather](https://t.me/BotFather)
- **Test Connection** button sends a test message to verify the setup

### Discord
- **Bot Token** — from the [Discord Developer Portal](https://discord.com/developers/applications)

### Lark (Feishu)
- **App ID** and **App Secret** — from the [Lark Open Platform](https://open.larksuite.com/app)
- See [Lark Bot Setup](lark_setting.md) for a step-by-step guide

Click **Save Changes** after entering credentials, then **Reload Runtime** to connect.

<!-- screenshot: settings platforms tab -->

---

## Desktop Tab

Controls for the desktop sandbox (only visible when sandbox mode is "Desktop").

### Stream Controls
- **Launch Stream** — start the noVNC desktop stream
- **Open in Tab** — open the stream URL in a new browser tab
- **Pause (Keep Data)** — pause the sandbox VM (preserves files, auto-backs up to R2)
- **Resume** — resume a paused sandbox
- **Stop & Destroy** — permanently destroy the sandbox VM

### Backup Management
- **Backup Now** — manually create a snapshot of the sandbox to R2 cloud storage
- **Backup list** — shows the 5 most recent backups with timestamp and size
- **Restore** — restore any backup into the running sandbox

The desktop stream is embedded as an iframe below the controls when active.

<!-- screenshot: settings desktop tab with stream and backups -->

---

## API Keys

Visible to all users. API keys allow programmatic access to the agent.

### Create a Key
1. Enter an optional key name (e.g. "CI pipeline")
2. Click **Create API Key**
3. Copy the key immediately — it won't be shown again

### Using API Keys

Send requests with the `X-Agent-API-Key` header:

```bash
curl -H "X-Agent-API-Key: your-key-here" \
  "https://your-domain.com/api/dashboard/agents/{agent_id}/files?path=/home/user"
```

### Manage Keys
- View key prefix, name, creation date, and last used date
- Click **Revoke** to permanently disable a key

Expand the **Usage Example** section for a complete curl example.

<!-- screenshot: API keys section -->
