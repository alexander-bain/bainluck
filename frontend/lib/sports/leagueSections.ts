/**
 * ux/1058 — #2948: A LEAGUE PAGE PUTS THE GAMES YOU CAN STILL WATCH FIRST.
 *
 * ═══ WHAT ALEX SAW, MEASURED ═══
 *
 * `/sports/tennis_atp_us_open`, during the US Open. The header promised
 * "Upcoming games with win probabilities" and the first sixteen cards were
 * finished matches; the LIVE Zverev match was card 17 of 29, at y=1651px. Every
 * card carrying a win probability sat below every card that did not.
 *
 * `app/sports/[key]/page.tsx` was 125 lines and rendered `events.map(...)` over
 * `fetchEvents(...)` with **no sort, no filter and no grouping**. So the render
 * order was `/api/events`'s order, which is `commence_time` ASCENDING — and a
 * finished match's commence_time is in the past while an upcoming one's is in
 * the future, so on that endpoint **every completed game precedes every
 * upcoming game by construction**. Not a bad afternoon's data: a property of
 * the ordering, on every league page, every day that has had a game finish.
 *
 * Re-measured on production 2026-09-04 while building the repair: 32 events,
 * **17 completed then 15 scheduled**, still perfectly ascending. The defect had
 * grown by one card since it was filed.
 *
 * ═══ WHY THIS IMPORTS `eventSectionKey` RATHER THAN ASKING ABOUT STATUS ═══
 *
 * 🔴 THE LOAD-BEARING PARAGRAPH. "Which bucket is this event in" already has an
 * owner — `lib/eventState.ts`, whose docblock says it exists because
 * `suspended` (live/048) landed in a vocabulary that every surface had been
 * reading with its own inline `=== "closed"` chain, and every one of those
 * chains fell through to "upcoming" — so a rain-delayed match advertised itself
 * as about to begin.
 *
 * A census of that authority's callers found exactly two — `lib/feedSections.ts`
 * (which serves `/sports`) and `app/my-stuff/page.tsx` — against a docblock
 * saying it is "Shared by `/sports`, the category grids and My Stuff so the
 * three cannot drift". This page was the surface doing neither. So the repair
 * is to join the authority, not to write a third partition: `suspended` reaches
 * the live bucket here for free, and can never be filed under Finished.
 *
 * ═══ WHY FINISHED SITS LAST, WHEN `/sports` TODAY PUTS IT SECOND ═══
 *
 * ⚠️ #2948 names `/sports` as a control. On master that control is half-wrong on
 * this very axis: `feedSections.ts` pushes "Just Happened" ABOVE "Upcoming".
 * The ordering followed here is Alex's D54 = A — results go below the games
 * still to play — which is what `app/my-stuff/page.tsx` already does
 * (live → upcoming → Recently Completed), what `/tournaments/[slug]` already
 * does ("Finished ones move to Finished, below"), and what ux/1053 built for
 * `/sports` itself. The section is titled "Finished" to match ux/1053's wording
 * exactly, so the two surfaces cannot name one bucket two things.
 *
 * ═══ NO CLOCK, BY CONSTRUCTION ═══
 *
 * Nothing here branches on the current time, so there is no `now` to inject and
 * no anchor that can rot (gotcha #44). This module only ever answers "which
 * bucket, and in what order within it" — never "is this still fresh". Ageing a
 * result out is a different decision with a different owner
 * (`lib/sports/finishedCardGuard.ts`), and this module deliberately does not
 * make it: a league page is where you go to see what the league did.
 *
 * PURE and NON-MUTATING — the caller's array is never sorted in place.
 */

import type { Event } from "@/lib/types";
import { eventSectionKey, isSuspendedStatus, liveSectionTitle } from "@/lib/eventState";

/** The three buckets, in the order they are rendered. */
export type LeagueSectionKey = "live" | "upcoming" | "finished";

export interface LeagueSection {
  key: LeagueSectionKey;
  /** The heading the reader sees. */
  title: string;
  /** Ordered cards. Never empty — an empty bucket emits no section at all. */
  events: Event[];
}

/**
 * Milliseconds for an ISO string, or `null` when there is nothing trustworthy
 * to sort on.
 *
 * `new Date("").getTime()` is `NaN`, and a comparator that returns `NaN`
 * produces an implementation-defined order rather than an error — so an
 * undated row would silently scatter. Undated rows are collected explicitly and
 * placed last in both directions instead.
 */
function timeOf(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? t : null;
}

/**
 * When a finished game finished.
 *
 * `completed_at` before `commence_time`, because `lib/types.ts` says so at the
 * field itself: *"Authoritative finished-event date; prefer over commence_time
 * for FINAL cards to avoid rendering a stale/future date beside a Final badge"*
 * (Queue #189 §B). A game that started before midnight and ended after it sorts
 * by when it ENDED, which is what "most recent result" means to a reader.
 */
function finishedAt(event: Event): number | null {
  return timeOf(event.completed_at) ?? timeOf(event.commence_time);
}

/**
 * Compare two possibly-null instants, nulls last in both directions.
 *
 * Returning 0 for a genuine tie is load-bearing: `Array.prototype.sort` is
 * stable (ES2019), so equal-time rows keep the order the payload gave them
 * rather than being reordered by an arbitrary tiebreak. Seven of today's US
 * Open fixtures share one commence_time, so this is the common case, not an
 * edge one.
 */
function compareNullsLast(
  a: number | null,
  b: number | null,
  direction: 1 | -1,
): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return (a - b) * direction;
}

/**
 * Split a league's events into the sections the page renders.
 *
 * Live keeps payload order — there is no "sooner" among games already being
 * played. Upcoming runs soonest-first; Finished runs most-recent-first. Both
 * match `app/my-stuff/page.tsx`, which is the closest sibling that partitions a
 * list of events on a page rather than sectioning a feed.
 *
 * An empty bucket emits no section, so a league with only scheduled games gets
 * exactly one heading rather than two empty ones.
 */
export function buildLeagueSections(events: Event[]): LeagueSection[] {
  const live: Event[] = [];
  const upcoming: Event[] = [];
  const finished: Event[] = [];

  for (const event of events) {
    // The shared ladder (live/048 + CERT-786), not a third copy of it.
    const section = eventSectionKey(event.status);
    if (section === "live") live.push(event);
    else if (section === "finished") finished.push(event);
    else upcoming.push(event);
  }

  const upcomingSorted = [...upcoming].sort((a, b) =>
    compareNullsLast(timeOf(a.commence_time), timeOf(b.commence_time), 1),
  );
  const finishedSorted = [...finished].sort((a, b) =>
    compareNullsLast(finishedAt(a), finishedAt(b), -1),
  );

  const sections: LeagueSection[] = [];
  if (live.length > 0) {
    sections.push({
      key: "live",
      // The header reads the bucket rather than asserting "Live Now" over a
      // rain-delayed match — the same shared rule `/sports` and My Stuff use.
      title: liveSectionTitle(live.some((e) => isSuspendedStatus(e.status))),
      events: live,
    });
  }
  if (upcomingSorted.length > 0) {
    sections.push({ key: "upcoming", title: "Upcoming", events: upcomingSorted });
  }
  if (finishedSorted.length > 0) {
    sections.push({ key: "finished", title: "Finished", events: finishedSorted });
  }
  return sections;
}
