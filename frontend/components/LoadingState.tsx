"use client";

/**
 * Full-page or section-level loading state.
 *
 * Use this when an entire page or major section is loading data.
 * For inline loading within a page section, use LoadingSpinner instead.
 *
 * Uses design system tokens: surface-border, accent-brand, text-muted.
 */

interface LoadingStateProps {
  /** Optional message shown below the spinner */
  message?: string;
  /** Optional className for the outer wrapper */
  className?: string;
}

export default function LoadingState({
  message,
  className,
}: LoadingStateProps) {
  const wrapperClass = className ?? "py-20";
  return (
    <div className={wrapperClass}>
      <div className="flex flex-col items-center justify-center gap-3">
        <div className="w-8 h-8 border-2 border-surface-border border-t-accent-brand rounded-full animate-spin" />
        {message && (
          <p className="text-sm text-text-muted">{message}</p>
        )}
      </div>
    </div>
  );
}
