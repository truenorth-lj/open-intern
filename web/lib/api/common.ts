const BASE = "/api/dashboard";

export function extractErrorMessage(
  err: Record<string, unknown>,
  fallback: string,
): string {
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

export async function apiFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
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
