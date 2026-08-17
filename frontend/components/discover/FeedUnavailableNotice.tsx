"use client";

/**
 * The Discover/Sports surfaces' honest state when the feed cannot be shown.
 *
 * ── L2-238: WHY IT EXISTS ──
 *
 * The backend returns `cache.status = "unavailable"` with `items: []` and
 * `has_more: false` when a singleflight waiter runs out of budget with no
 * last-good to serve. That body says "I know nothing", not "there is nothing".
 * Rendering it as the end-of-feed card told the reader the opposite of the truth
 * and left no way forward.
 *
 * ── UX-P087 / #1909: WHY THE COPY CHANGED ──
 *
 * L2-238 deliberately reused the page's existing words — "Failed to load feed" /
 * "Try again" — because inventing copy was not that queue's job. #1909 makes the
 * copy the job, so that constraint is now retired rather than quietly broken.
 *
 * What was actually measured (browser-audit run 32009921496, journey
 * `consent.two_tabs`, and the terminal screenshot in its artifact): when every
 * request on the page 429'd, Discover did **not** render blank as filed — it
 * rendered exactly this state. Two real defects were hiding behind that:
 *
 *  1. **It named neither a why nor a when.** "Failed to load feed" is the empty
 *     state [ruling 027](../../docs/rulings/027-entity-page-tiers.md) names as the
 *     specific death of an auto-generated page: one that "says 'check back later'
 *     and names neither a why nor a when". A reader cannot tell a rate limit from
 *     an outage from their own dead wifi, and each wants a different response.
 *  2. **`Try again` reloaded the whole document.** On the failure that actually
 *     happens most — too many requests from one network — a full reload re-fires
 *     every request on the page and is rate-limited again, so the one control
 *     offered was the one action guaranteed not to work. The retry is now the
 *     caller's, and on Discover it revalidates the feed alone.
 *
 * So the state is told by REASON. Each says what happened and what will change
 * it. The words are still few; they are just no longer the same three words for
 * three different situations.
 *
 * Two placements, one component:
 *   • `variant="empty"`  — nothing on screen. Takes the full-height error slot.
 *   • `variant="inline"` — last-good cards are still rendered above it. Sits
 *     below them where the infinite-scroll spinner would otherwise spin forever.
 */

/**
 * Why the feed is not on screen.
 *
 * `unavailable` is the DEFAULT so every pre-#1909 call site — `/sports`, and
 * Discover's two typed-degradation slots — keeps its exact prior meaning without
 * being touched. A silent behaviour change on another surface is not this
 * component's to make.
 */
export type FeedFailureReason = "unavailable" | "rate_limited" | "error";

interface Copy {
  /** Names the situation. Never "something went wrong". */
  headline: string;
  /** The why and the when, in one sentence (ruling 027). */
  detail: string;
  /**
   * The hook the browser rail and the audit tests bind to. The typed-degradation
   * case keeps `discover-feed-unavailable`; the two transport failures keep
   * `discover-feed-error`, which is the hook `discoverAuditHooks` has asserted
   * since the branch was inline on the page. Neither is renamed — a rail
   * selector is a contract with runs that have already been filed.
   */
  testId: string;
}

const COPY: Record<FeedFailureReason, Copy> = {
  unavailable: {
    headline: "The feed is catching up",
    detail:
      "The server has no fresh page ready yet and is building one. This usually clears within a few seconds.",
    testId: "discover-feed-unavailable",
  },
  rate_limited: {
    headline: "Too many requests, briefly",
    detail:
      "This network asked for more than the minute's allowance — often several people, or several tabs, at once. It clears on its own within a minute.",
    testId: "discover-feed-error",
  },
  error: {
    headline: "We couldn't load the feed",
    detail:
      "The request didn't come back. Nothing on this page is out of date — there is simply nothing to show until it does.",
    testId: "discover-feed-error",
  },
};

export default function FeedUnavailableNotice({
  onRetry,
  variant = "empty",
  reason = "unavailable",
}: {
  onRetry: () => void;
  variant?: "empty" | "inline";
  reason?: FeedFailureReason;
}) {
  const copy = COPY[reason] ?? COPY.unavailable;

  return (
    <div
      className={
        variant === "empty"
          ? "text-center py-20 text-text-muted"
          : "mt-6 mb-2 text-center text-text-muted"
      }
      data-testid={copy.testId}
      data-variant={variant}
      data-reason={reason}
      role="alert"
    >
      <p className="text-text-secondary text-sm font-medium">{copy.headline}</p>
      <p className="mt-1 mx-auto max-w-sm text-text-muted text-sm">{copy.detail}</p>
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
