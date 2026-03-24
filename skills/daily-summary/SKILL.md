---
name: daily-summary
description: Generate a daily summary of all conversations, actions taken, and work status. Produces a structured digest of what got done, what's stuck, and what needs attention.
allowed-tools: execute,read
metadata:
  category: meta
  version: "1.0"
---

# Daily Summary

## When to Use
- Triggered automatically by a scheduled cron job at end of day
- User manually asks for a summary of today's work
- User asks "what happened today?" or "give me a status update"

## How to Execute

### Step 1: Gather Today's Data

Review all available context for today:

1. **Conversation threads** — Recall all conversations you had today. Summarize the topics discussed, decisions made, and outcomes.
2. **Actions taken** — List any code commits, PRs created/merged, files edited, deployments, or other concrete actions.
3. **Scheduled jobs** — Check if any scheduled jobs ran today and their status (success/failure).
4. **Memory** — Recall any important information stored to memory today.

### Step 2: Categorize

Organize findings into three categories:

#### Done
- Tasks completed, PRs merged, questions answered, problems resolved
- Include brief context for each item (e.g., "Fixed auth bug reported by @alice in #backend")

#### Stuck
- Tasks that are blocked or stalled
- Include the reason (e.g., "Waiting for API key from DevOps", "Test flaking on CI")
- Tag who or what is blocking if known

#### Needs Attention
- Items that require follow-up tomorrow
- Upcoming deadlines or time-sensitive items
- Unresolved questions or open threads

### Step 3: Format Output

Produce a clean, scannable summary in this format:

```
📋 Daily Summary — {date}

✅ Done
• {item 1}
• {item 2}

🔸 Stuck
• {item 1} — {reason}

👀 Needs Attention
• {item 1}

📊 Stats: {N} conversations, {N} actions taken
```

### Guidelines
- Keep each item to 1-2 lines max
- Use plain language, not technical jargon unless the audience is technical
- If nothing happened today, say so — don't fabricate activity
- If delivering to a channel, keep the message concise and scannable
- Prioritize items by importance, most important first
