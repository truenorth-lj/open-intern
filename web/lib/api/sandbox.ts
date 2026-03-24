import { apiFetch, extractErrorMessage } from "./common";

export type SandboxStatusValue = "running" | "paused" | "stopped";

export interface SandboxStatusResponse {
  status: SandboxStatusValue;
  sandbox_id: string | null;
  backend_type: "e2b_desktop" | "e2b" | "ssh" | null;
  stream_active: boolean;
  stream_url: string | null;
}

export async function getSandboxStatus(
  agentId: string,
): Promise<SandboxStatusResponse> {
  const res = await apiFetch(`/agents/${agentId}/sandbox/status`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to get sandbox status"));
  }
  return res.json();
}

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

export interface BackupEntry {
  key: string;
  size_bytes: number;
  timestamp: string;
}

export async function backupSandbox(
  agentId: string,
): Promise<{ ok: boolean; key: string }> {
  const res = await apiFetch(`/agents/${agentId}/sandbox/backup`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to backup sandbox"));
  }
  return res.json();
}

export async function listSandboxBackups(
  agentId: string,
): Promise<{ backups: BackupEntry[] }> {
  const res = await apiFetch(`/agents/${agentId}/sandbox/backups`);
  if (!res.ok) return { backups: [] };
  return res.json();
}

export async function restoreSandbox(
  agentId: string,
): Promise<{ ok: boolean }> {
  const res = await apiFetch(`/agents/${agentId}/sandbox/restore`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to restore sandbox"));
  }
  return res.json();
}

export interface SandboxFileInfo {
  path: string;
  is_dir: boolean;
  size: number | null;
}

export async function listFiles(
  agentId: string,
  path: string = "/home/user",
): Promise<{ path: string; items: SandboxFileInfo[] }> {
  const params = new URLSearchParams({ path });
  const res = await apiFetch(`/agents/${agentId}/files?${params}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to list files"));
  }
  return res.json();
}

export async function readFile(
  agentId: string,
  path: string,
  offset: number = 0,
  limit: number = 2000,
): Promise<{ path: string; content: string; offset: number; limit: number }> {
  const params = new URLSearchParams({
    path,
    offset: String(offset),
    limit: String(limit),
  });
  const res = await apiFetch(`/agents/${agentId}/files/read?${params}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to read file"));
  }
  return res.json();
}

export async function writeFile(
  agentId: string,
  path: string,
  content: string,
): Promise<{ ok: boolean; path: string }> {
  const res = await apiFetch(`/agents/${agentId}/files/write`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to write file"));
  }
  return res.json();
}

export async function createDirectory(
  agentId: string,
  path: string,
): Promise<{ ok: boolean; path: string }> {
  const res = await apiFetch(`/agents/${agentId}/files/mkdir`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to create directory"));
  }
  return res.json();
}

export async function startDesktopStream(
  agentId: string,
): Promise<{ stream_url: string; agent_id: string }> {
  const res = await apiFetch(`/agents/${agentId}/desktop-stream`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      extractErrorMessage(err, "Failed to start desktop stream"),
    );
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
