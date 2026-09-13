"use client";

import type { LoadFailureTone } from "@/lib/loadFailure";

interface ErrorMessageProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  /**
   * Whether the body sentence describes a FAILURE or an ANSWER — #5857.
   *
   * This card painted every `message` in `text-accent-danger`, so a 410's
   * "This fixture was removed from the schedule — it was either a duplicate of
   * another game or a game that will not be played." was drawn in the same red
   * as "Rate limit exceeded: 60/minute". One of those is something going
   * wrong; the other is the schedule.
   *
   * `lib/loadFailure.ts` is the module that knows which is which, and its
   * `tone` is meant to be threaded straight through. Defaults to `"error"`, so
   * every call site that passes its own hand-written failure sentence renders
   * exactly as it did before.
   */
  tone?: LoadFailureTone;
}

export default function ErrorMessage({
  title = "Something went wrong",
  message,
  onRetry,
  tone = "error",
}: ErrorMessageProps) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-card p-4">
      <p className="text-sm font-semibold text-text-primary mb-1">{title}</p>
      <p
        className={
          tone === "info"
            ? "text-caption text-text-secondary mb-3"
            : "text-caption text-accent-danger mb-3"
        }
      >
        {message}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-caption text-accent-brand underline hover:no-underline transition-colors"
        >
          Tap to retry
        </button>
      )}
    </div>
  );
}
