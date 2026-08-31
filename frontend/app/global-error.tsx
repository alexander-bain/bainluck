"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // LAT-P171: import the SDK on the error path, not the happy path. A STATIC
  // `import * as Sentry` here pinned the 102 kB browser SDK into the chunk graph
  // that every route loads before it can hydrate — to serve a component that
  // only ever renders after an unrecoverable error. Loading it here costs one
  // async chunk in the case that is already broken, and nothing in the case
  // Alex is waiting on. Guarded on the DSN for the same reason as
  // `sentry.client.config.ts`: with none set, webpack drops the branch.
  useEffect(() => {
    if (!process.env.NEXT_PUBLIC_SENTRY_DSN) return;
    void import("@sentry/nextjs").then((Sentry) => Sentry.captureException(error));
  }, [error]);

  return (
    <html>
      <body>
        <div
          style={{
            padding: "2rem",
            textAlign: "center",
            fontFamily: "system-ui, sans-serif",
            minHeight: "100vh",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <h2 style={{ marginBottom: "1rem" }}>Something went wrong</h2>
          <p style={{ color: "#666", marginBottom: "1.5rem" }}>
            An unexpected error occurred. The error has been reported automatically.
          </p>
          <button
            onClick={reset}
            style={{
              padding: "0.5rem 1.5rem",
              borderRadius: "0.375rem",
              border: "1px solid #ddd",
              background: "#fff",
              cursor: "pointer",
              fontSize: "0.875rem",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
