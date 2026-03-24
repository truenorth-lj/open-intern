import type { Skill } from "../types";
import { apiFetch, extractErrorMessage } from "./common";

export async function sendMessage(
  message: string,
  threadId?: string,
  agentId?: string,
): Promise<{ response: string; thread_id: string; title: string }> {
  const res = await apiFetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      thread_id: threadId || "",
      agent_id: agentId || "",
    }),
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
  onDone: (data: {
    thread_id: string;
    title: string;
    agent_id: string;
    token_usage: Record<string, number>;
  }) => void,
  onError?: (error: string) => void,
  threadId?: string,
  agentId?: string,
  signal?: AbortSignal,
  onStatus?: (data: { tool: string; status: "running" | "done" }) => void,
): Promise<void> {
  const res = await apiFetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      thread_id: threadId || "",
      agent_id: agentId || "",
    }),
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

export async function getThreads(
  agentId?: string,
): Promise<{
  threads: { thread_id: string; title: string; created_at: string }[];
}> {
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

export async function getMemories(
  scope?: string,
  limit = 50,
  offset = 0,
  agentId?: string,
) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
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

export async function getSkills(
  agentId?: string,
): Promise<{ skills: Skill[] }> {
  const params = new URLSearchParams();
  if (agentId) params.set("agent_id", agentId);
  const res = await apiFetch(`/skills?${params}`);
  if (!res.ok) throw new Error("Failed to fetch skills");
  return res.json();
}

export async function getSkill(
  name: string,
  agentId?: string,
): Promise<Skill> {
  const params = new URLSearchParams();
  if (agentId) params.set("agent_id", agentId);
  const res = await apiFetch(`/skills/${name}?${params}`);
  if (!res.ok) throw new Error("Failed to fetch skill");
  return res.json();
}

export async function deleteMemory(id: string, agentId?: string) {
  const params = new URLSearchParams();
  if (agentId) params.set("agent_id", agentId);
  const res = await apiFetch(`/memories/${id}?${params}`, {
    method: "DELETE",
  });
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
