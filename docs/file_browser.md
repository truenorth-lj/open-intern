# Sandbox File Browser

The **Files** page lets you browse, read, edit, and create files inside an agent's E2B sandbox — directly from the dashboard.

## Prerequisites

- The agent must have **sandbox mode** enabled (`base` or `desktop`) in Settings > Model tab.
- The E2B sandbox must be running (not paused or destroyed).

## How to Access

1. Open the dashboard and navigate to an agent.
2. Click **Files** in the left sidebar.

![file browser overview](image/file_browser/overview.png)

## Features

### Browse Directories

- The file browser starts at `/home/user` by default.
- Click any **folder** to navigate into it.
- Click **`..`** at the top of the list to go to the parent directory.
- Use the **breadcrumb** path at the top to jump to any ancestor directory.

### View Files

- Click any **file** to open it in the right panel.
- File content is displayed with line numbers (monospace font).
- Large files are loaded in chunks (default: first 2000 lines).

### Edit Files

1. Open a file by clicking it.
2. Click the **Edit** button in the top-right of the viewer panel.
3. Make your changes in the text editor.
4. Click **Save** to write changes to the sandbox, or **Cancel** to discard.

### Create Files & Folders

- Click **+ File** to create a new empty file in the current directory.
- Click **+ Folder** to create a new directory.
- Type the name and press **Enter** (or click **Create**).
- Press **Escape** to cancel.

### Refresh

Click **Refresh** to reload the current directory listing (useful after the agent modifies files).

## API Endpoints

The file browser uses these REST endpoints (all require authentication):

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/dashboard/agents/{id}/files?path=` | List directory contents |
| `GET` | `/api/dashboard/agents/{id}/files/read?path=&offset=&limit=` | Read file content |
| `POST` | `/api/dashboard/agents/{id}/files/write` | Write/create a file |
| `POST` | `/api/dashboard/agents/{id}/files/mkdir` | Create a directory |

### Example: List files via curl

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://your-domain.com/api/dashboard/agents/my-agent/files?path=/home/user"
```

### Example: Read a file

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://your-domain.com/api/dashboard/agents/my-agent/files/read?path=/home/user/main.py"
```

### Example: Write a file

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/home/user/hello.txt", "content": "Hello World"}' \
  "https://your-domain.com/api/dashboard/agents/my-agent/files/write"
```

## Limitations

- **Max file write size**: 10 MB per request.
- **Max read lines**: 100,000 lines per request (configurable via `limit` parameter).
- **Binary files**: The viewer displays raw text; binary files will appear garbled.
- **Sandbox required**: Agents without E2B sandbox enabled will see a "no sandbox" error.
