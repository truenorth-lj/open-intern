import { useCallback, useEffect, useRef, useState } from "react";
import {
  getSandboxStatus,
  pauseSandbox,
  resumeSandbox,
  startDesktopStream,
  stopDesktopStream,
  type SandboxStatusValue,
} from "./api";

const POLL_INTERVAL_MS = 30_000;

export function useSandboxStatus(agentId: string) {
  const [status, setStatus] = useState<SandboxStatusValue>("stopped");
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [backendType, setBackendType] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const mountedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch true status from backend
  const refresh = useCallback(async () => {
    try {
      const data = await getSandboxStatus(agentId);
      if (!mountedRef.current) return;
      setStatus(data.status);
      setStreamUrl(data.stream_url);
      setBackendType(data.backend_type);
      setError("");
    } catch {
      // Silently ignore polling errors — stale state is better than error flash
    }
  }, [agentId]);

  // Poll on mount + interval
  useEffect(() => {
    mountedRef.current = true;
    refresh();
    timerRef.current = setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [refresh]);

  // Force refresh after any action
  const withRefresh = useCallback(
    async (action: () => Promise<void>) => {
      setLoading(true);
      setError("");
      try {
        await action();
        await refresh();
      } catch (err) {
        if (mountedRef.current) {
          setError(err instanceof Error ? err.message : "Operation failed");
        }
        await refresh();
      } finally {
        if (mountedRef.current) setLoading(false);
      }
    },
    [refresh],
  );

  const start = useCallback(
    () =>
      withRefresh(async () => {
        const data = await startDesktopStream(agentId);
        if (mountedRef.current) setStreamUrl(data.stream_url);
      }),
    [agentId, withRefresh],
  );

  const stop = useCallback(
    () => withRefresh(() => stopDesktopStream(agentId)),
    [agentId, withRefresh],
  );

  const pause = useCallback(
    () => withRefresh(() => pauseSandbox(agentId).then(() => undefined)),
    [agentId, withRefresh],
  );

  const resume = useCallback(
    () =>
      withRefresh(async () => {
        await resumeSandbox(agentId);
        const data = await startDesktopStream(agentId);
        if (mountedRef.current) setStreamUrl(data.stream_url);
      }),
    [agentId, withRefresh],
  );

  return {
    status,
    streamUrl,
    backendType,
    loading,
    error,
    refresh,
    start,
    stop,
    pause,
    resume,
  };
}
