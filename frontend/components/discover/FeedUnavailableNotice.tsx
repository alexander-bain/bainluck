"use client";

/**
 * L2-238 Item 0/1 — the Discover surface's retry state for a typed-UNAVAILABLE
 * feed response.
 *
 * The backend returns `cache.status = "unavailable"` with `items: []` and
 * `has_more: false` when a singleflight waiter runs out of budget with no
 * last-good to serve. That body says "I know nothing", not "there is nothing".
 * Rendering it as the end-of-feed card told the reader the opposite of the truth
 * and left no way forward.
 *
 * This deliberately reuses the words the Discover page ALREADY shows for a
 * failed load ("Failed to load feed" / "Try again") — no new copy is invented
 * here. It exists as its own component only so the state is renderable, and
 * therefore testable, without standing up the whole page.
 *
 * Two placements, one component:
 *   • `variant="empty"`  — nothing on screen. Takes the full-height error slot.
 *   • `variant="inline"` — last-good cards are still rendered above it. Sits
 *     below them where the infinite-scroll spinner would otherwise spin forever.
 */
export default function FeedUnavailableNotice({
  onRetry,
  variant = "empty",
}: {
  onRetry: () => void;
  variant?: "empty" | "inline";
}) {
  return (
    <div
      className={
        variant === "empty"
          ? "text-center py-20 text-text-muted"
          : "mt-6 mb-2 text-center text-text-muted"
      }
      data-testid="discover-feed-unavailable"
      data-variant={variant}
      role="alert"
    >
      <p className="text-text-secondary text-sm">Failed to load feed</p>
      <button
        onClick={onRetry}
        // The visible label is a bare verb phrase; a screen reader announcing a
        // button alone would not say what is being retried (the L2-237 lesson
        // from the calibration cohort toggle). The accessible name carries the
        // state; the visible words are unchanged.
        aria-label="Try again to load the feed"
        className="mt-3 text-sm text-accent-brand hover:underline transition-colors"
      >
        Try again
      </button>
    </div>
  );
}
