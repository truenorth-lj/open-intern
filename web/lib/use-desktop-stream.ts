import { useCallback, useEffect, useRef, useState } from "react";
import { getDesktopStream, startDesktopStream, stopDesktopStream } from "./api";

export function useDesktopStream(agentId: string) {
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      const data = await getDesktopStream(agentId);
      if (mountedRef.current && data.active && data.stream_url) {
        setStreamUrl(data.stream_url);
      }
    } catch {
      // ignore — stream may not be available
    }
  }, [agentId]);

  const start = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await startDesktopStream(agentId);
      if (mountedRef.current) setStreamUrl(data.stream_url);
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : "Failed to start stream");
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [agentId]);

  const stop = useCallback(async () => {
    setLoading(true);
    try {
      await stopDesktopStream(agentId);
      if (mountedRef.current) setStreamUrl(null);
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : "Failed to stop stream");
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [agentId]);

  return { streamUrl, loading, error, loadStatus, start, stop };
}
