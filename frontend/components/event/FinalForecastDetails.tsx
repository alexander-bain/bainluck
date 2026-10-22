/**
 * #11296 — WHERE A FINAL'S "BEFORE SCHEDULED START" FORECAST CAME FROM.
 *
 * The headline band says which reading it is; this says whose and when, one
 * tap down and closed by default, so the headline carries no method prose
 * (notice 34). Three facts, each the forecast's own and never the
 * win-probability prior's:
 *
 *   - how many sportsbooks contributed;
 *   - when their lines were recorded — a RANGE, because each sportsbook's last
 *     line before the start was taken at its own time (Buccaneers v Vikings,
 *     14781704: Sep 24 to Sep 27). There is no single "recorded at";
 *   - the scheduled start they were taken before. Listed, not observed.
 *
 * It prints what `finalForecastComparison` admitted; it decides nothing.
 */

import React from "react";

import type { FinalForecastComparison } from "@/lib/finalForecastComparison";

const DATE_TIME: Intl.DateTimeFormatOptions = {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
};
const TIME: Intl.DateTimeFormatOptions = { hour: "numeric", minute: "2-digit" };

function sameLocalDay(a: Date, b: Date): boolean {
  return a.toDateString() === b.toDateString();
}

/** "Oct 18, 9:29 – 9:59 AM"-style range; the date repeats only when the day changes. */
export function recordedRange(earliestIso: string, latestIso: string): string {
  const earliest = new Date(earliestIso);
  const latest = new Date(latestIso);
  const first = earliest.toLocaleString(undefined, DATE_TIME);
  if (earliest.getTime() === latest.getTime()) return first;
  const second = latest.toLocaleString(undefined, sameLocalDay(earliest, latest) ? TIME : DATE_TIME);
  return `${first} – ${second}`;
}

export default function FinalForecastDetails({
  details,
  testId = "event-hero-final-forecast-details",
}: {
  details: FinalForecastComparison["details"];
  /** #11296 — the live headline's retained pregame pair reuses this disclosure. */
  testId?: string;
}) {
  const { bookmakerCount, earliestCapturedAt, latestCapturedAt, boundaryAt } = details;
  return (
    <details
      className="group mt-1 self-stretch text-center text-[11px] text-text-muted"
      data-testid={testId}
      data-forecast-earliest={earliestCapturedAt}
      data-forecast-latest={latestCapturedAt}
      data-forecast-boundary={boundaryAt}
    >
      <summary className="cursor-pointer list-none select-none hover:text-text-secondary">
        Details{" "}
        <span aria-hidden="true" className="inline-block transition-transform group-open:rotate-180">
          &#9662;
        </span>
      </summary>
      {/* `w-0 min-w-full`: the opened list wraps inside the width the band
          already set, so opening it can never widen the headline's centre
          column and squeeze the two team columns beside it. */}
      <dl className="mt-1 w-0 min-w-full flex flex-col items-center gap-y-0.5 text-center text-text-secondary">
        <div>
          <dt className="inline">From </dt>
          <dd className="inline">
            {bookmakerCount} {bookmakerCount === 1 ? "sportsbook" : "sportsbooks"}
          </dd>
        </div>
        <div>
          <dt className="inline">Lines recorded </dt>
          <dd className="inline">{recordedRange(earliestCapturedAt, latestCapturedAt)}</dd>
        </div>
        <div>
          <dt className="inline">Scheduled start </dt>
          <dd className="inline">{new Date(boundaryAt).toLocaleString(undefined, DATE_TIME)}</dd>
        </div>
      </dl>
    </details>
  );
}
