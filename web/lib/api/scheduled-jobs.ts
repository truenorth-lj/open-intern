import { apiFetch, extractErrorMessage } from "./common";

export interface ScheduledJob {
  id: string;
  agent_id: string;
  name: string;
  schedule_type: "cron" | "interval" | "once";
  schedule_expr: string;
  prompt: string;
  timezone: string;
  channel_id: string;
  delivery_platform: "" | "lark" | "telegram" | "discord";
  delivery_chat_id: string;
  isolated: boolean;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
  last_run_status: "success" | "error" | null;
  last_run_error: string | null;
  next_run_at: string | null;
}

export async function listScheduledJobs(
  agentId: string,
): Promise<{ jobs: ScheduledJob[] }> {
  const res = await apiFetch(`/scheduled-jobs?agent_id=${agentId}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to load scheduled jobs"));
  }
  return res.json();
}

export async function deleteScheduledJob(jobId: string): Promise<void> {
  const res = await apiFetch(`/scheduled-jobs/${jobId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to delete job"));
  }
}

export async function pauseScheduledJob(jobId: string): Promise<void> {
  const res = await apiFetch(`/scheduled-jobs/${jobId}/pause`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to pause job"));
  }
}

export async function resumeScheduledJob(jobId: string): Promise<void> {
  const res = await apiFetch(`/scheduled-jobs/${jobId}/resume`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to resume job"));
  }
}

export async function triggerScheduledJob(jobId: string): Promise<void> {
  const res = await apiFetch(`/scheduled-jobs/${jobId}/trigger`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to trigger job"));
  }
}
