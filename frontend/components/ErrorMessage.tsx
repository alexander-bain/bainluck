"use client";

interface ErrorMessageProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

/**
 * Error message display - inline, actionable per design brief.
 */
export default function ErrorMessage({
  title = "Something went wrong",
  message,
  onRetry,
}: ErrorMessageProps) {
  return (
    <div className="bg-white border border-mist rounded-card p-4">
      <p className="text-body-strong text-graphite mb-1">{title}</p>
      <p className="text-caption text-rust mb-3">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-caption text-ink underline hover:no-underline transition-colors"
        >
          Tap to retry
        </button>
      )}
    </div>
  );
}
