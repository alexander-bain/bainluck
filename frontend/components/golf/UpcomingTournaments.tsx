// The "Upcoming Tournaments" section on `/categories/golf` — what a reader is
// told is coming next.
//
// EXTRACTED FROM THE PAGE BY UX-P169, for the same two reasons `GolferRow` was
// (see its header): the guard beside it has to render THIS component rather than
// assert over a helper, and a Next.js route file may only export the reserved
// names, so it cannot live in `page.tsx` and be testable.
//
// ═══ WHY THIS SECTION WAS BLANK ═══
//
// It was fed by `upcoming_events`, which the backend built from the `events`
// table filtered to `Sport.key ILIKE 'golf_%'`. Golf has six rows there in all of
// history, every one `closed` and in the past, and they are props and mis-ingests
// rather than tournaments — including a Philippine BASKETBALL game. So the list
// was always empty, and `.length > 0` removed the whole section from the page.
// Meanwhile the DataGolf schedule, which knows about twenty future tournaments,
// was already in the very same payload under `pga_schedule`, with no consumer.
//
// ═══ TWO THINGS THAT LOOK LIKE TIDY-UP AND ARE NOT ═══
//
// 1. Dates are formatted with `timeZone: "UTC"`. A tournament's dates are
//    calendar facts, not instants: the schedule sends `2026-09-03T00:00:00+00:00`
//    and a reader west of Greenwich would otherwise be told the Omega European
//    Masters starts on September 2nd. The frontend jest gate runs `TZ=UTC`, so
//    this class of bug is INVISIBLE to it — the pin is the explicit option here,
//    not the suite.
// 2. Rows are not links. A tournament that has not started has no markets and so
//    no tournament page; linking it would hand the reader a dead end. Naming it
//    is the whole ship.

"use client";

import type { GolfUpcomingEvent } from "@/lib/types";

// Tournament dates are calendar facts — see note 1 in the header.
function utcPart(iso: string, opts: Intl.DateTimeFormatOptions): string {
  return new Date(iso).toLocaleDateString("en-US", { ...opts, timeZone: "UTC" });
}

/**
 * "Sep 3 – 6" when a tournament stays inside one month, "Sep 24 – Oct 1" when it
 * does not, and just the start when there is no end date to pair it with.
 */
export function formatDateRange(
  start: string | null | undefined,
  end: string | null | undefined,
): string | null {
  if (!start) return null;
  const startLabel = utcPart(start, { month: "short", day: "numeric" });
  if (!end) return startLabel;

  const full: Intl.DateTimeFormatOptions = {
    year: "numeric",
    month: "short",
    day: "numeric",
  };
  // Compare the whole date. Comparing the RENDERED labels cannot work: a
  // same-month end renders as the bare day ("3"), which never equals "Sep 3".
  if (utcPart(start, full) === utcPart(end, full)) return startLabel;

  const sameMonth =
    utcPart(start, { month: "short", year: "numeric" }) ===
    utcPart(end, { month: "short", year: "numeric" });

  const endLabel = sameMonth
    ? utcPart(end, { day: "numeric" })
    : utcPart(end, { month: "short", day: "numeric" });

  return `${startLabel} – ${endLabel}`;
}

export default function UpcomingTournaments({
  events,
}: {
  events: GolfUpcomingEvent[];
}) {
  if (!events || events.length === 0) return null;

  return (
    <section data-testid="golf-upcoming">
      <h2 className="text-xl font-bold text-text-primary mb-4 flex items-center gap-2">
        <span className="text-[#006747]">&#x1F4C5;</span>
        Upcoming Tournaments
      </h2>
      <div className="space-y-2">
        {events.map((event, i) => {
          const dates = formatDateRange(event.start_date, event.end_date);
          const where = event.location || event.venue || null;
          return (
            <div
              key={event.key || `${event.name}-${i}`}
              data-testid="golf-upcoming-row"
              className="bg-surface-card rounded-lg border border-surface-border p-3 flex items-center justify-between gap-3"
            >
              <div className="min-w-0">
                <div className="text-sm text-text-primary truncate">
                  {event.name}
                </div>
                {where && (
                  <div className="text-xs text-text-muted truncate">{where}</div>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {event.tour_label && (
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-surface-elevated text-text-secondary">
                    {event.tour_label}
                  </span>
                )}
                {dates && (
                  <span className="text-xs text-text-muted">{dates}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
