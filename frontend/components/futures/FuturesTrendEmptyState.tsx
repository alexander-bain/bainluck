"use client";

// The futures page's "no trend to draw" card (#7545).
//
// WHY THIS IS ITS OWN FILE AND ITS OWN DECISION. Before the range chips there
// was one emptiness and one sentence for it — "Not enough price history yet" —
// and that sentence was true, because the window was derived and the reader had
// no say in it. Once the window is the reader's, the same empty payload has two
// completely different meanings:
//
//   * the market has no prices at all — the old sentence, still true; or
//   * the market's prices all predate the rung the reader is standing on, in
//     which case the history exists, we are serving it, and telling them it is
//     not there yet is false. /futures/112921 has 4,527 points and would say
//     this on any week-long window that happened to miss them.
//
// And the second case has a second trap: the empty result must not take the
// CHIPS down with it. A control that disappears exactly when the reader needs it
// to get back is worse than no control — they would have to edit the URL or
// reload the page to escape a rung their own tap put them on.

import FuturesTrendRangeControls from "@/components/futures/FuturesTrendRangeControls";
import {
  futuresRangeSpanWords,
  type FuturesRangeKey,
} from "@/lib/futuresHistoryRange";

interface FuturesTrendEmptyStateProps {
  range: FuturesRangeKey;
  onSelect: (range: FuturesRangeKey) => void;
  requestedHours: number;
  actualHours?: number | null;
  /** The market's own open, which sizes the "All" rung. */
  createdAt?: string | null;
}

export default function FuturesTrendEmptyState({
  range,
  onSelect,
  requestedHours,
  actualHours,
  createdAt,
}: FuturesTrendEmptyStateProps) {
  // On "all" there is no wider rung to send anyone to, so an empty result here
  // really is an empty market — the original sentence, unchanged.
  const marketIsEmpty = range === "all";

  return (
    <div className="bg-surface-card rounded-card shadow-card p-6">
      <h2 className="text-title-3 font-semibold text-text-primary flex items-center gap-2 mb-3">
        <span>📈</span>
        Probability Trend
      </h2>
      <div className="h-24 flex flex-col items-center justify-center gap-1.5 text-sm text-text-secondary">
        {marketIsEmpty ? (
          <>
            <span>Not enough price history yet</span>
            <span className="text-xs text-text-muted">
              The trend line appears once this market has a few price points.
            </span>
          </>
        ) : (
          <>
            <span>No prices in {futuresRangeSpanWords(range, createdAt)}</span>
            <span className="text-xs text-text-muted">Try a longer range.</span>
          </>
        )}
      </div>
      {!marketIsEmpty && (
        <FuturesTrendRangeControls
          range={range}
          onSelect={onSelect}
          requestedHours={requestedHours}
          actualHours={actualHours}
        />
      )}
    </div>
  );
}
