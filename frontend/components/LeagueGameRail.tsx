"use client";

import type { LeagueGameBrief } from "@/lib/api";
import { leagueGameToEvent } from "@/lib/leagueCards";
import EventCard from "./EventCard";

/**
 * The league page's games rails (UX-P062 / #1743, Alex's 2026-08-11 amendment).
 *
 * "League pages include an UPCOMING GAMES rail and a RECENT RESULTS rail — event
 * cards, the product's richest and freshest content."
 *
 * ── WHY THESE RENDER FROM THE LEAGUE ENVELOPE, NOT FROM THE FEED ──
 *
 * The page used to fetch `/api/feed?sport=…` for its games. The feed answers a
 * DIFFERENT question — "which games are interesting?" — and applies its own
 * scoring, pools and diversity caps. Since the tier census counts games (the
 * amendment), sourcing the render from the feed would let the backend count eight
 * games while the reader sees two: the broken shelf, arriving through the census
 * instead of the template. Same route declares the tier and supplies the rail.
 *
 * ── UX-P074 (#1860), RULING 047: THE CARD IS THE SHARED ONE ──
 *
 * This rail used to draw its own `GameRow` — a two-line variant with a bar and a
 * single percentage. It was a perfectly reasonable local choice and that is the
 * whole problem ruling 047 names: "a bespoke variant spends the reader's
 * accumulated fluency to save one queue an afternoon." A reader who learned the
 * event card on /sports or in search had to learn a second one here, on the same
 * content.
 *
 * So the rail is now a LAYOUT and the card is `components/EventCard` — the same
 * component /sports/[key], search, My Stuff and Preferences render. What the
 * variant used to draw and the shared card draws instead:
 *
 *   both sides of the blend (not just home) · team colours and logos · the live
 *   period/clock · the settled score block · the opening line on a live game
 *
 * None of that is new invention: the league envelope was extended to carry it
 * (ruling 047's scope clause — extend the contract, do not fork the card), and
 * every field is one `/api/events` already serves under the same name.
 *
 * The two invariants this rail was already right about are unchanged and still
 * pinned by `__tests__/components/leagueGameRail.test.tsx`: the cap declaration
 * follows the rail (upcoming vs settled), and an unpriced game renders NO number
 * rather than a fabricated 0%/50%.
 */
export default function LeagueGameRail({
  title,
  games,
  hasMore,
  settled = false,
  emptyStateName,
}: {
  title: string;
  games: LeagueGameBrief[];
  hasMore?: boolean;
  settled?: boolean;
  emptyStateName?: string;
}) {
  if (games.length === 0) {
    // Honest-empty is the PAGE's job (spec §6), not a per-rail "check back later".
    // A rail with nothing in it renders nothing at all.
    return emptyStateName ? (
      <div data-empty-state-name={emptyStateName} className="hidden" />
    ) : null;
  }

  return (
    <section data-section-key={settled ? "results" : "games"}>
      <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
        {title}
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {games.map((g, i) => (
          <EventCard
            key={g.id}
            event={leagueGameToEvent(g)}
            // The league page IS the league context — repeating "MLB" on eight
            // cards is the chrome the entity-page grammar makes pages earn.
            showSport={false}
            sourceSection="sport_category"
            positionIndex={i}
          />
        ))}
      </div>
      {/* A cap is always DECLARED (spec §4). An uncounted cap reads as coverage.
          The wording follows the rail: this component serves BOTH the upcoming
          and the settled rail, and "most recent" was printing over future
          fixtures on the upcoming one. */}
      {hasMore && (
        <p className="mt-2 text-xs text-text-muted">
          Showing the {settled ? `${games.length} most recent` : `next ${games.length}`} — more exist.
        </p>
      )}
    </section>
  );
}
