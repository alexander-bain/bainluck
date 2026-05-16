"use client";

/**
 * Full-page or section-level error state.
 *
 * Use this when an entire page or major section fails to load data.
 * For smaller inline errors within a page, use ErrorMessage instead.
 *
 * Uses design system tokens: text-text-secondary, text-text-muted, text-accent-brand.
 */

interface ErrorStateProps {
  /** Main message shown to the user */
  message?: string;
  /** Optional retry handler — shows a retry button when provided */
  onRetry?: () => void;
  /** Optional className for the outer wrapper */
  className?: string;
}

export default function ErrorState({
  message = "Failed to load data",
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div className={className ?? "py-20"}>
      <div className="text-center max-w-md mx-auto px-4">
        <p className="text-text-secondary text-sm">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-3 text-sm text-accent-brand hover:underline transition-colors"
          >
            Try again
          </button>
        )}
      </div>
    </div>
  );
}
