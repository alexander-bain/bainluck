"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { Event } from "@/lib/types";
import { prematchReading, prematchSourceLegend } from "@/lib/prematchReading";
import EventCard from "./EventCard";

/**
 * The league page's games rails (UX-P062 / #1743, Alex's 2026-08-11 amendment),
 * and — since ux/1053 — the /sports Finished section as well.
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
 * ── ux/1053: THE RAIL TAKES `Event[]`, AND /sports USES IT ──
 *
 * ux/1052 item 6 (#2920) measured that the feed draws `FeedCard` while five
 * surfaces draw `EventCard`. The /sports Finished section is the first bucket to
 * cross over, so this rail stopped taking a `LeagueGameBrief[]` (one producer's
 * envelope) and now takes `Event[]` (the shared card's own input). Each producer
 * adapts at its own call site — `leagueGameToEvent` for the league page,
 * `feedEventToEvent` for /sports — which is what makes "the tab and the page
 * agree" a property of the component rather than of two editors remembering.
 *
 * THE THREE OPTIONAL PROPS ARE SURFACE DIFFERENCES, STATED. Same discipline as
 * `suspendedSummary`'s required `ScoreOrder` argument: where two surfaces
 * genuinely differ, the difference is an argument the caller states, not a
 * default one of them silently inherits.
 *
 *   `header`  — /sports files this beside Live Now and Upcoming, which wear an
 *               emoji, a bold title and a count chip. The league page's own
 *               small-caps `<h2>` is still the default, so that page is
 *               byte-identical to before.
 *   `layout`  — the league page pairs cards two-up; /sports uses the auto-fill
 *               grid its sibling sections use, so Finished does not read as an
 *               imported widget at desktop width.
 *   `moreLinks` — where the capped-away results actually are.
 *
 * The two invariants this rail was already right about are unchanged and still
 * pinned by `__tests__/components/leagueGameRail.test.tsx`: the cap declaration
 * follows the rail (upcoming vs settled), and an unpriced game renders NO number
 * rather than a fabricated 0%/50%.
 */

/** Where the results this rail could not fit actually live. */
export interface RailMoreLink {
  label: string;
  href: string;
}

export default function LeagueGameRail({
  title,
  events,
  hasMore,
  settled = false,
  emptyStateName,
  header,
  layout = "pair",
  moreLinks,
  labels,
}: {
  title: string;
  events: Event[];
  hasMore?: boolean;
  settled?: boolean;
  emptyStateName?: string;
  /** Replaces the rail's own heading. `title` still names the section for a11y. */
  header?: ReactNode;
  /** "pair" = two-up (league page). "feed" = the /sports auto-fill grid. */
  layout?: "pair" | "feed";
  /** Rendered inside the cap declaration. Omitted → the declaration alone. */
  moreLinks?: RailMoreLink[];
  /**
   * The one short label a card may wear, BY EVENT ID.
   *
   * ux/1053 — the feed card carries two of these ("Recent upset" from
   * `highlight.label`, "Won as 47% underdog" from `item.reason`) and the shared
   * card has one slot, so the producer picks which one it means rather than the
   * card guessing. Keyed by id and not folded into `Event` because it is a fact
   * about how the FEED ranked this card, not a fact about the event — the league
   * envelope has no such field and passes nothing, which is why that page is
   * unchanged.
   */
  labels?: Record<number, string>;
}) {
  if (events.length === 0) {
    // Honest-empty is the PAGE's job (spec §6), not a per-rail "check back later".
    // A rail with nothing in it renders nothing at all.
    return emptyStateName ? (
      <div data-empty-state-name={emptyStateName} className="hidden" />
    ) : null;
  }

  // THE LEGEND FOR THE MARK THE CARDS DREW (D57 / ux/1053). A settled card
  // prints `†` beside a pre-match number that came from a sportsbook median
  // rather than a prediction market, and D57's shape is "a mark on the number,
  // and a note below saying what the mark means". The rail counts what its OWN
  // cards will mark, using the same reader they use, so the note can never
  // describe a mark that is not on screen — or miss one that is.
  const markedCards = events.filter(
    (event) =>
      prematchReading({
        prematch_odds: event.prematch_odds,
        opening_odds: event.opening_odds,
      })?.marker != null,
  ).length;
  const sourceLegend = settled ? prematchSourceLegend(markedCards) : "";

  return (
    <section data-section-key={settled ? "results" : "games"} aria-label={title}>
      {header ?? (
        <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
          {title}
        </h2>
      )}
      <div
        className={
          layout === "feed" ? "grid gap-3" : "grid grid-cols-1 sm:grid-cols-2 gap-3"
        }
        style={
          layout === "feed"
            ? { gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }
            : undefined
        }
      >
        {events.map((event, i) => (
          <EventCard
            key={event.id}
            event={event}
            // The league page IS the league context — repeating "MLB" on eight
            // cards is the chrome the entity-page grammar makes pages earn.
            // /sports is NOT a league context, so it asks for the label back.
            showSport={layout === "feed"}
            sourceSection={settled ? "recently_finished" : "sport_category"}
            positionIndex={i}
            highlightLabel={labels?.[event.id]}
          />
        ))}
      </div>
      {/* A cap is always DECLARED (spec §4). An uncounted cap reads as coverage.
          The wording follows the rail: this component serves BOTH the upcoming
          and the settled rail, and "most recent" was printing over future
          fixtures on the upcoming one.

          ux/1053 — and the declaration now leads somewhere. A capped section
          that only says "more exist" tells a reader something is missing and
          not where to find it; each link is the league page whose Recent
          Results rail is THIS component, drawing these same cards. A league the
          register cannot resolve contributes no link and the sentence still
          declares the cap (UX-P062 register E5: never a link that goes
          nowhere). */}
      {hasMore && (
        <p className="mt-2 text-xs text-text-muted">
          Showing the {settled ? `${events.length} most recent` : `next ${events.length}`}
          {moreLinks && moreLinks.length > 0 ? (
            <>
              {" — more in "}
              {moreLinks.map((link, i) => (
                <span key={link.href}>
                  {i > 0 && ", "}
                  <Link href={link.href} className="underline hover:text-text-secondary">
                    {link.label}
                  </Link>
                </span>
              ))}
              .
            </>
          ) : (
            " — more exist."
          )}
        </p>
      )}
      {sourceLegend && (
        <p className="mt-1 text-xs text-text-muted" data-testid="rail-prematch-source-note">
          The grey figure beside a name is what the market gave that team before
          the game started. {sourceLegend}
        </p>
      )}
    </section>
  );
}
