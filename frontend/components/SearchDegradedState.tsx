"use client";

/**
 * SearchDegradedState — what the search page shows when it could not finish.
 *
 * #2239. The state this replaces was `SearchZeroState`, which says "No results
 * for X" and "We couldn't find any teams, games, or markets matching that". Both
 * sentences are assertions about what exists. When `/api/events/search` sheds a
 * stage against its deadline it returns an empty answer and says so in
 * `degraded` — and the page printed those sentences anyway.
 *
 * Two rules this copy follows:
 *
 *  1. **It never claims the thing is absent.** That is the defect.
 *  2. **It offers the retry**, because the failure is transient by construction
 *     — the answer was shed for time, so asking again is the correct next step,
 *     and #2239's user worked that out unaided by retyping four times.
 *
 * Deliberately NOT the shared `ErrorState`: nothing errored. The request
 * succeeded and returned a partial answer, and calling it an error would send a
 * reader looking for a broken site. It is its own state for the same reason
 * `degraded` is its own key.
 */

export default function SearchDegradedState({
  query,
  onRetry,
}: {
  query: string;
  onRetry: () => void;
}) {
  return (
    <div className="max-w-3xl mx-auto">
      <div className="text-center py-10" data-empty-state-name="search-degraded">
        <div className="text-4xl mb-4">⏳</div>
        <h1 className="text-title-2 text-text-primary mb-2">
          We didn&apos;t finish searching
          {query ? <> for &quot;{query}&quot;</> : null}
        </h1>
        <p className="text-text-secondary">
          This one took too long, so we stopped early — there may well be results
          waiting. Nothing here means we ran out of time, not that we came up empty.
        </p>
        <button
          onClick={onRetry}
          className="mt-5 inline-block rounded-full bg-accent-brand px-5 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
