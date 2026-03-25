"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html>
      <body style={{ padding: 40, fontFamily: "system-ui, sans-serif", background: "#111", color: "#eee" }}>
        <h2>Something went wrong</h2>
        <pre style={{ whiteSpace: "pre-wrap", color: "#f88", background: "#222", padding: 16, borderRadius: 8 }}>
          {error.message}
        </pre>
        {error.digest && (
          <p style={{ color: "#888" }}>Digest: {error.digest}</p>
        )}
        <pre style={{ whiteSpace: "pre-wrap", color: "#aaa", fontSize: 12 }}>
          {error.stack}
        </pre>
        <button
          onClick={reset}
          style={{ marginTop: 16, padding: "8px 16px", cursor: "pointer" }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
