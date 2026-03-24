import { apiFetch } from "./common";

export interface SystemSetting {
  key: string;
  value: string;
  is_secret: boolean;
  description: string;
  updated_at: string;
}

export async function getSystemSettings(): Promise<{
  settings: SystemSetting[];
}> {
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
