import type { Skill } from "./types";

const BASE = "/api/dashboard";

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
    throw new Error(err.detail || "Failed to send message");
  }
  return res.json();
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

export async function getMemories(scope?: string, limit = 50, offset = 0) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (scope) params.set("scope", scope);
  const res = await apiFetch(`/memories?${params}`);
  if (!res.ok) throw new Error("Failed to fetch memories");
  return res.json();
}

export async function getMemoryStats() {
  const res = await apiFetch("/memories/stats");
  if (!res.ok) throw new Error("Failed to fetch memory stats");
  return res.json();
}

export async function getSkills(): Promise<{ skills: Skill[] }> {
  const res = await apiFetch("/skills");
  if (!res.ok) throw new Error("Failed to fetch skills");
  return res.json();
}

export async function getSkill(name: string): Promise<Skill> {
  const res = await apiFetch(`/skills/${name}`);
  if (!res.ok) throw new Error("Failed to fetch skill");
  return res.json();
}

export async function deleteMemory(id: string) {
  const res = await apiFetch(`/memories/${id}`, { method: "DELETE" });
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
  sandbox_enabled: boolean;
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
  sandbox_enabled?: boolean;
}) {
  const res = await apiFetch("/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to create agent");
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
    throw new Error(err.detail || "Failed to update agent");
  }
  return res.json();
}

export async function deleteAgent(agentId: string) {
  const res = await apiFetch(`/agents/${agentId}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to delete agent");
  }
  return res.json();
}
