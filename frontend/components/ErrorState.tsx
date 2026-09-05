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
  /**
   * Optional heading naming WHICH failure this was ("Too many requests").
   *
   * Added by CAL-P1023 so this component can render a `LoadFailure`
   * (`lib/loadFailure.ts`) whole. That module's rule is that the server's own
   * `detail` stays as the message because it is the most specific true thing
   * available, "and the title is only ever a heading over it" — so a caller
   * that renders the message without the title publishes a raw machine
   * sentence ("Rate limit exceeded: 60/minute") with nothing naming it.
   *
   * Optional, and absent by default: every existing caller renders exactly as
   * it did before.
   */
  title?: string;
  /** Main message shown to the user */
  message?: string;
  /** Optional retry handler — shows a retry button when provided */
  onRetry?: () => void;
  /** Optional className for the outer wrapper */
  className?: string;
}

export default function ErrorState({
  title,
  message = "Failed to load data",
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div className={className ?? "py-20"}>
      <div className="text-center max-w-md mx-auto px-4">
        {title && (
          <p className="text-text-primary text-base font-semibold mb-1">{title}</p>
        )}
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
