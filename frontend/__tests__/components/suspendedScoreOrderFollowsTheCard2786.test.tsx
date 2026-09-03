// THE SUSPENDED SCORE READS IN THE CARD'S OWN ORDER — #2786.
//
// `suspendedSummary` hardcoded away-home and justified it as "matching every
// card in the app". Measured, that premise is false for three of its four
// callers. On production 2026-09-03 (`842e6167` / v4020) it shipped an inverted
// score: event 15293347 (`home_score=3`, `away_score=6`) rendered
// "No result reported · last score 6-3" on a shared `EventCard` that lists the
// HOME team directly above it — one glance from its settled twin's "3 – 6".
//
// WHY THIS FILE EXISTS SEPARATELY FROM THE 786/792 GUARDS. Those pin the
// STRING, which is exactly why this shipped green: a constant cannot notice that
// the card around it counts the other way. Every assertion here is a comparison
// between TWO RENDERS OF THE SAME COMPONENT ON THE SAME ROW — settled or live
// versus suspended — so the reference is the component's own behaviour and it
// moves when the component moves.
//
// THE SCORES ARE DELIBERATELY DISTINCT (home 3, away 6). An equal pair would
// make every ordering assertion in this file pass for free.
//
// EVERY EXTRACTION IS ASSERTED NON-EMPTY FIRST. A regex that silently stops
// matching would otherwise turn each of these into `[] === []`.
//
// NOT COVERED HERE: the event page hero (`app/events/[id]/page.tsx`), the fourth
// caller. It is a data-fetching page component, not renderable in this harness
// without stubbing its whole network surface, and a source scan cannot tell a
// rendered order from a declared one (#2060). Its home-above-away hero is
// asserted by the production LOOK on the ship, and it is the least ambiguous of
// the four because the hero labels both sides with the team name.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

jest.mock("@/components/Analytics", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("@/hooks", () => ({
  useAnalytics: () => ({ trackEventCardClick: () => {}, track: () => {} }),
}));

import SharedEventCard from "@/components/EventCard";
import FeedCard from "@/components/FeedCard";
import { EventCard as DiscoverEventCard } from "@/components/discover/EventCard";
import type { Event, FeedEventData, FeedItem } from "@/lib/types";

const IN_THE_PAST = new Date(Date.now() - 15 * 3600_000).toISOString();

/** The production specimen: Angels at Yankees, 3-6, home 3 / away 6. */
const HOME_SCORE = 3;
const AWAY_SCORE = 6;

function baseRow(over: Record<string, unknown> = {}) {
  return {
    id: 15293347,
    external_id: "evt-15293347",
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: "Los Angeles Angels",
    away_team: "New York Yankees",
    commence_time: IN_THE_PAST,
    status: "suspended",
    home_score: HOME_SCORE,
    away_score: AWAY_SCORE,
    home_team_data: { primary_color: "#2563eb", logo_small: "h.png" },
    away_team_data: { primary_color: "#64748b", logo_small: "a.png" },
    current_odds: {
      captured_at: IN_THE_PAST,
      home_probability: 0.6,
      away_probability: 0.4,
      spread: null,
      over_under: null,
      projected_home_score: null,
      projected_away_score: null,
    },
    ...over,
  };
}

function text(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&middot;|&#xB7;/g, "·")
    .replace(/&#x27;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ");
}

/** The two numbers the suspended sentence prints, in the order it prints them. */
function suspendedPair(html: string): string[] {
  const m = text(html).match(/last score (\d+)-(\d+)/);
  expect(m).not.toBeNull();
  return [m![1], m![2]];
}

/** Every match of a capture group, in document order. */
function ordered(html: string, re: RegExp, expected: number): string[] {
  const found = Array.from(html.matchAll(re)).map((m) => m[1]);
  // The anti-vacuity assertion. If a class name or an aria-label is renamed,
  // this file must go red rather than quietly comparing two empty lists.
  expect(found).toHaveLength(expected);
  return found;
}

// ---------------------------------------------------------------------------
// The shared EventCard — league rails, category grids, search, pinned, My Stuff
// ---------------------------------------------------------------------------

function renderShared(over: Record<string, unknown> = {}): string {
  return renderToStaticMarkup(
    <SharedEventCard event={baseRow(over) as unknown as Event} />,
  );
}

describe("the shared EventCard's suspended score reads like its own scores", () => {
  it("matches the order of its FINAL score block", () => {
    // The settled twin, rendered from the same row. Its block is unambiguous
    // because it labels each number with a team abbreviation — and it puts the
    // home number first.
    const settled = text(renderShared({ status: "completed" }));
    // The abbreviations are uppercased by CSS, not in the DOM, so this reads
    // "3 Angels — 6 Yankees".
    const settledPair = settled.match(/(\d+) \w+ — (\d+) \w+/);
    expect(settledPair).not.toBeNull();

    expect(suspendedPair(renderShared())).toEqual([
      settledPair![1],
      settledPair![2],
    ]);
  });

  it("matches the order of its LIVE inline scores", () => {
    // The live arm stacks the home block above the away block. Read off the
    // accessible labels, which name the team the number belongs to.
    const live = renderShared({ status: "live" });
    const liveOrder = ordered(live, /score: (\d+)"/g, 2);

    expect(suspendedPair(renderShared())).toEqual(liveOrder);
  });

  it("prints the home number first, which is 3 and not 6", () => {
    // The user-visible claim, stated plainly so the failure message names it.
    // Angels (home) scored 3; the card printed "last score 6-3" under the
    // Angels' own name.
    expect(suspendedPair(renderShared())).toEqual([
      String(HOME_SCORE),
      String(AWAY_SCORE),
    ]);
  });
});

// ---------------------------------------------------------------------------
// FeedCard — the two branches share ONE slot
// ---------------------------------------------------------------------------

function renderFeed(over: Record<string, unknown> = {}): string {
  const data = baseRow(over) as unknown as FeedEventData;
  return renderToStaticMarkup(
    <FeedCard item={{ type: "event", score: 50, reason: "", headline: "", data } as unknown as FeedItem} />,
  );
}

describe("FeedCard's suspended line does not swap the numbers", () => {
  it("prints them in the same order the live branch does", () => {
    // This is the sharpest form of the defect: both branches render into the
    // SAME slot, so the numbers changed places the moment play stopped, with
    // nothing on the card to say they had.
    const livePair = text(renderFeed({ status: "live" })).match(/(\d+) - (\d+)/);
    expect(livePair).not.toBeNull();

    expect(suspendedPair(renderFeed())).toEqual([livePair![1], livePair![2]]);
  });
});

// ---------------------------------------------------------------------------
// The Discover card — the one surface that really is away-first
// ---------------------------------------------------------------------------

function renderDiscover(over: Record<string, unknown> = {}): string {
  const data = baseRow(over) as unknown as FeedEventData;
  return renderToStaticMarkup(
    <DiscoverEventCard
      item={{ type: "event", score: 50, reason: "", headline: "", data } as unknown as FeedItem}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />,
  );
}

describe("the Discover card keeps away-home, because that is what it paints", () => {
  it("matches the order of its own hero scores", () => {
    // The control for the whole change, and the reason the fix is a parameter
    // rather than a global flip: this card paints `away_score` to the LEFT of
    // `home_score`, so away-home is correct here and must not move.
    const heroOrder = ordered(
      renderDiscover(),
      /tabular-nums text-white drop-shadow">(\d+)</g,
      2,
    );

    expect(suspendedPair(renderDiscover())).toEqual(heroOrder);
    expect(heroOrder).toEqual([String(AWAY_SCORE), String(HOME_SCORE)]);
  });
});
