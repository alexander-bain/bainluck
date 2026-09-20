"use client";

// The range chips + coverage line for the futures page's Probability Trend
// (#7545). This lives in its own file rather than inside `app/futures/[id]/page.tsx`
// because a Next page module may not carry a second named export — exporting a
// subcomponent from a page reds the typecheck gate — so a piece of a page that
// needs its own test needs its own file.

import ChartRangeChips from "@/components/event/ChartRangeChips";
import {
  FUTURES_RANGE_CHIPS,
  rangeCoverageNote,
  type FuturesRangeKey,
} from "@/lib/futuresHistoryRange";

interface FuturesTrendRangeControlsProps {
  /** The rung the reader is on. */
  range: FuturesRangeKey;
  onSelect: (range: FuturesRangeKey) => void;
  /** The `hours=` this rung asked the API for. */
  requestedHours: number;
  /** The window the API says it actually served, when it says. */
  actualHours?: number | null;
  /** Appended to the cadence/sparse line the page already shows, if any. */
  cadenceNote?: string | null;
  className?: string;
}

export default function FuturesTrendRangeControls({
  range,
  onSelect,
  requestedHours,
  actualHours,
  cadenceNote,
  className,
}: FuturesTrendRangeControlsProps) {
  const coverage = rangeCoverageNote(requestedHours, actualHours);

  return (
    <div className={`flex flex-col gap-1.5 ${className ?? ""}`}>
      <ChartRangeChips
        ranges={FUTURES_RANGE_CHIPS}
        selected={range}
        // ChartRangeChips speaks the full shared ChartRangeKey vocabulary, but it
        // can only ever hand back a key from the `ranges` it was given, and those
        // are this page's three.
        onSelect={(key) => onSelect(key as FuturesRangeKey)}
      />
      {(coverage || cadenceNote) && (
        <p className="text-xs text-text-muted">
          {[coverage, cadenceNote].filter(Boolean).join(" · ")}
        </p>
      )}
    </div>
  );
}
