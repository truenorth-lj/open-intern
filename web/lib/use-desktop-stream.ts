import { useCallback, useEffect, useRef, useState } from "react";
import {
  getDesktopStream,
  pauseSandbox,
  resumeSandbox,
  startDesktopStream,
  stopDesktopStream,
} from "./api";

export type SandboxStatus = "stopped" | "running" | "paused";

export function useDesktopStream(agentId: string) {
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sandboxStatus, setSandboxStatus] = useState<SandboxStatus>("stopped");
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
        setSandboxStatus("running");
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
      if (mountedRef.current) {
        setStreamUrl(data.stream_url);
        setSandboxStatus("running");
      }
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
      if (mountedRef.current) {
        setStreamUrl(null);
        setSandboxStatus("stopped");
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : "Failed to stop stream");
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [agentId]);

  const pause = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      await pauseSandbox(agentId);
      if (mountedRef.current) {
        setStreamUrl(null);
        setSandboxStatus("paused");
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : "Failed to pause sandbox");
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [agentId]);

  const resume = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      await resumeSandbox(agentId);
      if (mountedRef.current) {
        setSandboxStatus("running");
        // After resume, start streaming again
        const data = await startDesktopStream(agentId);
        if (mountedRef.current) {
          setStreamUrl(data.stream_url);
        }
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : "Failed to resume sandbox");
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [agentId]);

  return { streamUrl, loading, error, sandboxStatus, loadStatus, start, stop, pause, resume };
}
