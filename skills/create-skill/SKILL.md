---
name: create-skill
description: Create a new reusable skill that persists across conversations. Use when the user asks to create, add, or save a new skill, workflow, or automation that should be available in future conversations.
allowed-tools: read,write
metadata:
  category: meta
  version: "1.0"
---

# Create Skill

## When to Use
- User asks to create a new skill, workflow, or automation
- User wants to save a reusable procedure for future use
- User says "remember how to do X" or "save this as a skill"

## How to Execute

### Step 1: Gather Information
Ask the user (if not already provided):
- **What** the skill does (→ becomes `description`)
- **When** to use it (→ becomes "When to Use" section)
- **How** to execute it (→ becomes "How to Execute" section)

### Step 2: Choose a Name
- Use lowercase kebab-case (e.g., `deploy-check`, `zeabur-ops`)
- Keep it short and descriptive

### Step 3: Write the SKILL.md File

**CRITICAL**: The file MUST have YAML frontmatter with `---` delimiters. Without it, the skill will NOT be discovered.

Write to `/skills/<skill-name>/SKILL.md` with this exact format:

```markdown
---
name: <skill-name>
description: <one-line description of what this skill does and when to use it>
allowed-tools: execute
metadata:
  category: <category>
  version: "1.0"
---

# <Skill Title>

## When to Use
- <condition 1>
- <condition 2>

## How to Execute
<step-by-step instructions>
```

### Required Fields
| Field | Description |
|-------|-------------|
| `name` | Kebab-case identifier, must match directory name |
| `description` | One-line summary — this is what the agent sees when deciding which skill to use |
| `allowed-tools` | Comma-separated tools: `execute`, `read`, `write`, `edit`, `grep`, `glob` |

### Step 4: Confirm
After writing the file, tell the user:
- The skill has been created
- It will be available in **new conversations** (not the current one)
- Show the skill name and description

## Common Categories
- `devops` — deployment, CI/CD, infrastructure
- `coding` — code generation, refactoring patterns
- `data` — data processing, analysis workflows
- `communication` — messaging, notifications
- `meta` — skills about skills
