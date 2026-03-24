import type { Skill } from "./types";

const BASE = "/api/dashboard";

function extractErrorMessage(err: Record<string, unknown>, fallback: string): string {
  const detail = err.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (
      detail
        .map((d: unknown) => {
          if (typeof d === "object" && d !== null && "msg" in d) {
            return (d as { msg: string }).msg || "Unknown error";
          }
          return String(d);
        })
        .join("; ") || fallback
    );
  }
  return fallback;
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  return res;
}

export async function getStatus() {
  const res = await apiFetch("/status");
  if (!res.ok) throw new Error("Failed to fetch status");
  return res.json();
}

// --- System Settings ---

export interface SystemSetting {
  key: string;
  value: string;
  is_secret: boolean;
  description: string;
  updated_at: string;
}

export async function getSystemSettings(): Promise<{ settings: SystemSetting[] }> {
  const res = await apiFetch("/settings");
  if (!res.ok) throw new Error("Failed to fetch settings");
  return res.json();
}

export async function upsertSystemSetting(
  key: string,
  value: string,
  is_secret: boolean = false,
  description: string = "",
) {
  const res = await apiFetch(`/settings/${key}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value, is_secret, description }),
  });
  if (!res.ok) throw new Error("Failed to save setting");
  return res.json();
}

export async function deleteSystemSetting(key: string) {
  const res = await apiFetch(`/settings/${key}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete setting");
  return res.json();
}

export async function sendMessage(message: string, threadId?: string, agentId?: string): Promise<{ response: string; thread_id: string; title: string }> {
  const res = await apiFetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId || "", agent_id: agentId || "" }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to send message"));
  }
  return res.json();
}

export async function sendMessageStream(
  message: string,
  onToken: (token: string) => void,
  onDone: (data: { thread_id: string; title: string; agent_id: string; token_usage: Record<string, number> }) => void,
  onError?: (error: string) => void,
  threadId?: string,
  agentId?: string,
  signal?: AbortSignal,
  onStatus?: (data: { tool: string; status: "running" | "done" }) => void,
): Promise<void> {
  const res = await apiFetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId || "", agent_id: agentId || "" }),
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to send message"));
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const jsonStr = line.slice(6).trim();
      if (!jsonStr) continue;

      try {
        const event = JSON.parse(jsonStr);
        if (event.type === "token") {
          onToken(event.content);
        } else if (event.type === "status") {
          onStatus?.({ tool: event.tool, status: event.status });
        } else if (event.type === "done") {
          onDone(event);
        } else if (event.type === "error") {
          onError?.(event.content);
        }
      } catch {
        // skip malformed JSON
      }
    }
  }
}

export async function getThreads(agentId?: string): Promise<{ threads: { thread_id: string; title: string; created_at: string }[] }> {
  const params = agentId ? `?agent_id=${agentId}` : "";
  const res = await apiFetch(`/threads${params}`);
  if (!res.ok) throw new Error("Failed to fetch threads");
  return res.json();
}

export async function updateThreadTitle(threadId: string, title: string) {
  const res = await apiFetch(`/threads/${threadId}/title`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error("Failed to update thread title");
  return res.json();
}

export async function deleteThread(threadId: string) {
  const res = await apiFetch(`/threads/${threadId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete thread");
  return res.json();
}

export async function getMemories(scope?: string, limit = 50, offset = 0, agentId?: string) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (scope) params.set("scope", scope);
  if (agentId) params.set("agent_id", agentId);
  const res = await apiFetch(`/memories?${params}`);
  if (!res.ok) throw new Error("Failed to fetch memories");
  return res.json();
}

export async function getMemoryStats(agentId?: string) {
  const params = new URLSearchParams();
  if (agentId) params.set("agent_id", agentId);
  const res = await apiFetch(`/memories/stats?${params}`);
  if (!res.ok) throw new Error("Failed to fetch memory stats");
  return res.json();
}

export async function getSkills(agentId?: string): Promise<{ skills: Skill[] }> {
  const params = new URLSearchParams();
  if (agentId) params.set("agent_id", agentId);
  const res = await apiFetch(`/skills?${params}`);
  if (!res.ok) throw new Error("Failed to fetch skills");
  return res.json();
}

export async function getSkill(name: string, agentId?: string): Promise<Skill> {
  const params = new URLSearchParams();
  if (agentId) params.set("agent_id", agentId);
  const res = await apiFetch(`/skills/${name}?${params}`);
  if (!res.ok) throw new Error("Failed to fetch skill");
  return res.json();
}

export async function deleteMemory(id: string, agentId?: string) {
  const params = new URLSearchParams();
  if (agentId) params.set("agent_id", agentId);
  const res = await apiFetch(`/memories/${id}?${params}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete memory");
  return res.json();
}

export async function getThreadTokenUsage(threadId: string) {
  const res = await apiFetch(`/token-usage/thread/${threadId}`);
  if (!res.ok) throw new Error("Failed to fetch token usage");
  return res.json();
}

export async function getAgentTokenUsage(agentId: string) {
  const res = await apiFetch(`/token-usage/agent/${agentId}`);
  if (!res.ok) throw new Error("Failed to fetch token usage");
  return res.json();
}

export async function getTokenUsageSummary() {
  const res = await apiFetch("/token-usage/summary");
  if (!res.ok) throw new Error("Failed to fetch token usage summary");
  return res.json();
}

export async function getTokenUsageTimeseries(params: {
  start?: string;
  end?: string;
  agent_id?: string;
}) {
  const qs = new URLSearchParams();
  if (params.start) qs.set("start", params.start);
  if (params.end) qs.set("end", params.end);
  if (params.agent_id) qs.set("agent_id", params.agent_id);
  const res = await apiFetch(`/token-usage/timeseries?${qs}`);
  if (!res.ok) throw new Error("Failed to fetch token usage timeseries");
  return res.json();
}

// --- Agent CRUD ---

export interface AgentInfo {
  agent_id: string;
  name: string;
  role: string;
  personality: string;
  avatar_url: string;
  llm_provider: string;
  llm_model: string;
  llm_temperature: number;
  llm_api_key: string;
  telegram_token: string;
  discord_token: string;
  lark_app_id: string;
  lark_app_secret: string;
  platform_type: string;
  sandbox_mode: string; // "none" | "base" | "desktop"
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export async function listAgents(): Promise<{ agents: AgentInfo[] }> {
  const res = await apiFetch("/agents");
  if (!res.ok) throw new Error("Failed to fetch agents");
  return res.json();
}

export async function createAgent(data: {
  agent_id: string;
  name: string;
  role?: string;
  personality?: string;
  avatar_url?: string;
  llm_provider?: string;
  llm_model?: string;
  llm_temperature?: number;
  llm_api_key?: string;
  telegram_token?: string;
  sandbox_mode?: string;
}) {
  const res = await apiFetch("/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to create agent"));
  }
  return res.json();
}

export async function updateAgent(
  agentId: string,
  data: Partial<Omit<AgentInfo, "agent_id" | "created_at" | "updated_at">>,
) {
  const res = await apiFetch(`/agents/${agentId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to update agent"));
  }
  return res.json();
}

export async function testTelegramConnection(
  agentId: string,
  chatId: string,
  message?: string,
): Promise<{ ok: boolean; bot_username: string; chat_id: string; message: string }> {
  const body: Record<string, string> = { chat_id: chatId };
  if (message) body.message = message;
  const res = await apiFetch(`/agents/${agentId}/test-telegram`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    let msg = "Failed to test Telegram connection";
    if (typeof detail === "string") {
      msg = detail;
    } else if (Array.isArray(detail)) {
      msg = detail.map((d: { msg?: string }) => d.msg || JSON.stringify(d)).join("; ");
    }
    throw new Error(msg);
  }
  return res.json();
}

export async function reloadAgent(agentId: string) {
  const res = await apiFetch(`/agents/${agentId}/reload`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to reload agent"));
  }
  return res.json();
}

export async function deleteAgent(agentId: string) {
  const res = await apiFetch(`/agents/${agentId}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to delete agent"));
  }
  return res.json();
}

export async function getAgentDetail(agentId: string): Promise<AgentInfo> {
  const res = await apiFetch(`/agents/${agentId}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to fetch agent"));
  }
  return res.json();
}

// --- API Keys ---

export interface ApiKeyInfo {
  id: string;
  key_prefix: string;
  agent_id: string;
  name: string;
  created_by: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyCreateResponse {
  id: string;
  key: string;
  key_prefix: string;
  agent_id: string;
  name: string;
  created_at: string;
}

export async function createApiKey(
  agentId: string,
  name: string = "",
): Promise<ApiKeyCreateResponse> {
  const res = await apiFetch(`/auth/agents/${agentId}/api-keys`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to create API key"));
  }
  return res.json();
}

export async function listApiKeys(
  agentId: string,
): Promise<{ api_keys: ApiKeyInfo[] }> {
  const res = await apiFetch(`/auth/agents/${agentId}/api-keys`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to fetch API keys"));
  }
  return res.json();
}

export async function revokeApiKey(
  agentId: string,
  keyId: string,
): Promise<{ ok: boolean }> {
  const res = await apiFetch(`/auth/agents/${agentId}/api-keys/${keyId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to revoke API key"));
  }
  return res.json();
}

export async function permanentlyDeleteAgent(agentId: string) {
  const res = await apiFetch(`/agents/${agentId}/permanent`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to delete agent"));
  }
  return res.json();
}

// --- Sandbox Lifecycle ---

export async function pauseSandbox(
  agentId: string,
): Promise<{ ok: boolean; sandbox_id: string; status: string }> {
  const res = await apiFetch(`/agents/${agentId}/sandbox/pause`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to pause sandbox"));
  }
  return res.json();
}

export async function resumeSandbox(
  agentId: string,
): Promise<{ ok: boolean; sandbox_id: string; status: string }> {
  const res = await apiFetch(`/agents/${agentId}/sandbox/resume`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to resume sandbox"));
  }
  return res.json();
}

// --- Desktop Stream ---

export async function startDesktopStream(
  agentId: string,
): Promise<{ stream_url: string; agent_id: string }> {
  const res = await apiFetch(`/agents/${agentId}/desktop-stream`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to start desktop stream"));
  }
  return res.json();
}

export async function stopDesktopStream(agentId: string): Promise<void> {
  await apiFetch(`/agents/${agentId}/desktop-stream`, {
    method: "DELETE",
  });
}

export async function getDesktopStream(
  agentId: string,
): Promise<{ stream_url: string | null; agent_id: string; active: boolean }> {
  const res = await apiFetch(`/agents/${agentId}/desktop-stream`);
  if (!res.ok) return { stream_url: null, agent_id: agentId, active: false };
  return res.json();
}
