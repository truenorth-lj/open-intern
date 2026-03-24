import { apiFetch, extractErrorMessage } from "./common";

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
  sandbox_mode: string;
  ssh_host: string;
  ssh_port: number;
  ssh_user: string;
  ssh_key: string;
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
  ssh_host?: string;
  ssh_port?: number;
  ssh_user?: string;
  ssh_key?: string;
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
): Promise<{
  ok: boolean;
  bot_username: string;
  chat_id: string;
  message: string;
}> {
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
      msg = detail
        .map((d: { msg?: string }) => d.msg || JSON.stringify(d))
        .join("; ");
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
