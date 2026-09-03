// ux/1036 Tier A — A FINISHED CARD GIVES EACH TEAM ITS OWN PRE-MATCH NUMBER.
//
// Alex, on /sports "Just Happened" at phone width, 2026-09-02: *"How come none
// of these show pre-event probability?"*
//
// He was reading a column of FINAL cards on which the only pre-match figure was
// a grey `Opened 40/60` footnote. That string fails at the one job the number
// has — it never says WHICH TEAM is the 40 — and the live card three rows up
// gives each team its own. His instruction: keep the live-card layout on FINAL
// cards, score bold in the right column, the pre-match probability greyed beside
// each name, winner bold, and drop `Opened x/y` once the per-team numbers exist.
//
// ## Why this file renders instead of grepping
//
// #2060's lesson, and `discoverEventCardDuelInvariant`'s: a source grep cannot
// tell a rendered field from a declared one. `lib/prematchReading.ts` has its own
// contract tests; only this file proves the two CARDS show what it decides.
//
// Both directions per gotcha #43: the number appears on a FINAL card AND the
// live card is asserted unchanged — it keeps `Opened X/Y`, because there the
// opening is a second comparative fact beside a per-team current split rather
// than the only pre-match figure on the card.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import FeedCard from "@/components/FeedCard";
import { EventCard as DiscoverEventCard } from "@/components/discover/EventCard";
import type { FeedEventData, FeedItem } from "@/lib/types";

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

// The pairing Alex named. Padres won at 40%, which is also why "Won as 40%
// underdog" has to survive — it is the story, and it is a different sentence
// from the two numbers.
function makeData(over: Partial<FeedEventData> = {}): FeedEventData {
  return {
    id: 15299725,
    external_id: "evt-15299725",
    sport: "baseball_mlb",
    sport_name: "MLB",
    home_team: "Cincinnati Reds",
    away_team: "San Diego Padres",
    commence_time: "2026-09-02T23:10:00.000Z",
    status: "completed",
    home_score: 3,
    away_score: 5,
    ...over,
  } as FeedEventData;
}

function makeItem(data: FeedEventData, over: Partial<FeedItem> = {}): FeedItem {
  return {
    type: "event",
    score: 50,
    reason: "",
    headline: "",
    data,
    ...over,
  } as unknown as FeedItem;
}

function renderFeedCard(data: FeedEventData, item?: Partial<FeedItem>): string {
  return renderToStaticMarkup(<FeedCard item={makeItem(data, item)} />);
}

function renderDiscoverCard(data: FeedEventData): string {
  return renderToStaticMarkup(
    <DiscoverEventCard
      item={makeItem(data)}
      data={data}
      liked={false}
      setLiked={() => {}}
      trending={false}
    />
  );
}

/** The percent printed in a `data-testid` cell, or `null` when the cell is absent. */
function printedPercent(html: string, testid: string): number | null {
  const cell = new RegExp(
    `<span[^>]*data-testid="${testid}"[^>]*>([\\s\\S]*?)</span>\\s*(?:</div>|<span|</span>)`
  ).exec(html);
  if (!cell) return null;
  const match = /(\d+)%/.exec(cell[1].replace(/<[^>]*>/g, " "));
  return match ? Number(match[1]) : null;
}

// CARRIES BOTH RUNGS ON PURPOSE. `opening_odds` is present on most settled
// events (36 of the 40 most recent finals, production 2026-09-03), so a fixture
// without it would make the "drops the Opened footnote" assertion vacuous — the
// old code had nothing to print either. With it, the pre-fix card prints
// `Opened 55/45` and the post-fix card must not; and the ladder is under test
// too, because Kalshi's 60 has to beat the books' 55.
const KALSHI_FINAL = makeData({
  opening_odds: { home_probability: 0.55, away_probability: 0.45, favorite: "home" },
  prematch_odds: {
    home_probability: 0.6,
    away_probability: 0.4,
    home_rendered_percent: 60,
    away_rendered_percent: 40,
    source: "kalshi",
  },
});

// ── /sports and every other FeedCard list ───────────────────────────────────

describe("the /sports FINAL card", () => {
  it("prints a pre-match percent beside EACH team, off the winning rung", () => {
    // 60/40 is Kalshi's; 55/45 is the books' `opening_odds` on the same payload.
    // The ladder is ordered, so the books number must not reach the card.
    const html = renderFeedCard(KALSHI_FINAL);

    expect(printedPercent(html, "feed-card-prematch-away")).toBe(40);
    expect(printedPercent(html, "feed-card-prematch-home")).toBe(60);
  });

  it("names the team each number is about, for a reader who cannot see the layout", () => {
    // The whole defect in one assertion: `Opened 40/60` could not do this.
    const html = renderFeedCard(KALSHI_FINAL);

    expect(html).toContain("Before the game, the market gave San Diego Padres");
    expect(html).toContain("Before the game, the market gave Cincinnati Reds");
  });

  it("drops the Opened footnote now that the per-team numbers exist", () => {
    expect(renderFeedCard(KALSHI_FINAL)).not.toContain("Opened");
  });

  it("still shows the score, in its own right-hand column", () => {
    const html = renderFeedCard(KALSHI_FINAL);

    expect(html).toContain('data-testid="feed-card-final-score"');
    expect(html).toContain(">5</div>");
    expect(html).toContain(">3</div>");
  });

  it("keeps the underdog story, which the numbers do not replace", () => {
    // Alex: "'Won as 40% underdog' stays (it is the story)."
    const html = renderFeedCard(KALSHI_FINAL, { reason: "Won as 40% underdog" });

    expect(html).toContain("Won as 40% underdog");
  });

  it("labels a sportsbook reading and leaves a prediction-market one bare", () => {
    // Alex: "labelled when not a prediction market."
    const books = renderFeedCard(
      makeData({
        opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
      })
    );

    expect(printedPercent(books, "feed-card-prematch-home")).toBe(60);
    expect(books).toContain("Pre-match · books");
    expect(renderFeedCard(KALSHI_FINAL)).not.toContain("Pre-match ·");
  });

  it("prints nothing at all when we hold no pre-match reading", () => {
    // The empty space is a real answer. It is what the tennis hub's finished
    // list has always done, and what stops a card inventing a prior.
    const html = renderFeedCard(makeData());

    expect(html).not.toContain('data-testid="feed-card-prematch-home"');
    expect(html).not.toContain("Pre-match");
  });

  it("leaves the LIVE card exactly as it was — Opened X/Y and no per-team prior", () => {
    // The regression arm. A live card shows the CURRENT split per team, so the
    // opening is a comparative second fact there rather than the only one.
    const html = renderFeedCard(
      makeData({
        status: "live",
        current_odds: { home_probability: 0.52, away_probability: 0.48 },
        opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
      } as Partial<FeedEventData>)
    );

    expect(html).toContain("Opened 60/40");
    expect(html).not.toContain('data-testid="feed-card-prematch-home"');
  });
});

// ── Discover ────────────────────────────────────────────────────────────────

describe("the Discover FINAL card", () => {
  it("prints the pre-match pair in the live strip's three slots", () => {
    const html = renderDiscoverCard(KALSHI_FINAL);

    expect(printedPercent(html, "event-card-prematch-away")).toBe(40);
    expect(printedPercent(html, "event-card-prematch-home")).toBe(60);
    expect(html).toContain("Pre-match");
  });

  it("keeps the winner line the pre-match numbers sit under", () => {
    const html = renderDiscoverCard(KALSHI_FINAL);

    expect(html).toContain("Padres won");
  });

  it("labels a sportsbook reading here too", () => {
    const html = renderDiscoverCard(
      makeData({
        opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
      })
    );

    expect(html).toContain("Pre-match · books");
  });

  it("shows no strip on a card we hold no reading for", () => {
    expect(renderDiscoverCard(makeData())).not.toContain('data-testid="event-card-prematch"');
  });

  it("leaves the LIVE win-probability strip untouched", () => {
    const html = renderDiscoverCard(
      makeData({
        status: "live",
        current_odds: { home_probability: 0.52, away_probability: 0.48 },
      } as Partial<FeedEventData>)
    );

    expect(html).toContain("Win Probability");
    expect(html).not.toContain('data-testid="event-card-prematch"');
  });
});
