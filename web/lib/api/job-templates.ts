import { apiFetch, extractErrorMessage } from "./common";

export interface JobTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  default_schedule_type: "cron" | "interval" | "once";
  default_schedule_expr: string;
  default_timezone: string;
  default_prompt: string;
  default_isolated: boolean;
  skill: string;
}

export interface InstallTemplateParams {
  agent_id: string;
  schedule_expr?: string;
  timezone?: string;
  prompt?: string;
  delivery_platform?: string;
  delivery_chat_id?: string;
}

export async function listJobTemplates(): Promise<{
  templates: JobTemplate[];
}> {
  const res = await apiFetch("/job-templates");
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to load job templates"));
  }
  return res.json();
}

export async function installJobTemplate(
  templateId: string,
  params: InstallTemplateParams,
): Promise<void> {
  const res = await apiFetch(`/job-templates/${templateId}/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(err, "Failed to install template"));
  }
}
