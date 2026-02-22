"use client";

interface ErrorMessageProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export default function ErrorMessage({
  title = "Something went wrong",
  message,
  onRetry,
}: ErrorMessageProps) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-card p-4">
      <p className="text-sm font-semibold text-text-primary mb-1">{title}</p>
      <p className="text-caption text-accent-danger mb-3">{message}</p>
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
