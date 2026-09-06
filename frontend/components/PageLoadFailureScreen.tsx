"use client";

/**
 * The full-page "we could not show you this" screen — #3254.
 *
 * `/sport/[sport]` and `/sport/[sport]/[league]` each carried their own copy of
 * this block, and each printed one unconditional sentence with one
 * unconditional retry button. Both are now driven by `lib/loadFailure.ts`, so
 * the retry is offered when a retry can help and withheld when it cannot.
 *
 * Distinct from `components/ErrorMessage.tsx`, which is an inline card for a
 * failed SECTION inside a working page. This is the whole viewport, and it
 * carries the one thing that shape needs: somewhere else to go.
 */

import Link from "next/link";
import type { LoadFailure } from "@/lib/loadFailure";

export interface PageLoadFailureScreenProps {
  failure: LoadFailure;
  /**
   * The HTTP status, published as an ATTRIBUTE and never as copy, so a LOOK
   * pass can tell our own throttling from a real regression without the reader
   * ever seeing a number (the #3297 precedent).
   */
  status?: number;
  /**
   * Where a reader who cannot get this page should go instead. The caller
   * picks it, because only the caller knows what it has established: offering
   * "Back to tennis" from a page that just declared tennis does not exist is
   * the incoherence #3254 was filed on.
   */
  escape: { href: string; label: string };
  /** Defaults to a full reload, which is what both call sites want. */
  onRetry?: () => void;
}

export default function PageLoadFailureScreen({
  failure,
  status,
  escape,
  onRetry,
}: PageLoadFailureScreenProps) {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div
        className="text-center max-w-md mx-auto px-4"
        data-error-status={status}
      >
        <p className="text-sm font-semibold text-text-primary mb-1">
          {failure.title}
        </p>
        <p className="text-text-secondary text-sm mb-3">{failure.message}</p>
        <div className="flex items-center justify-center gap-4">
          {failure.retryable && (
            <button
              onClick={onRetry ?? (() => window.location.reload())}
              className="text-sm text-accent-brand hover:underline transition-colors"
            >
              Try again
            </button>
          )}
          <Link
            href={escape.href}
            className="text-sm text-text-muted hover:text-text-primary transition-colors"
          >
            {escape.label}
          </Link>
        </div>
      </div>
    </div>
  );
}
