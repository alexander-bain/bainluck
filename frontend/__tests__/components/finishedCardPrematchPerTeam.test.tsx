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

    expect(html).toContain("Pre-match probability: San Diego Padres");
    expect(html).toContain("Pre-match probability: Cincinnati Reds");
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

  it("speaks one venue-free sentence, whichever rung the number came from", () => {
    // D65 (Alex, 2026-09-04): "Can't we just say 'pre-match odds' or 'pre-match
    // probability'? Shouldn't reference sportsbooks."
    //
    // This test used to assert the OPPOSITE — that the clause forked, saying
    // "sportsbooks opened" on the books rung and "the market gave" on Kalshi.
    // That fork was itself a repair: before it, "the market gave" was read out
    // over a sportsbook median on 13 of 13 finished cards on the served /sports
    // payload (2026-09-03), which is a false claim about a venue. Alex's answer
    // removes the claim instead of correcting it — "pre-match probability" is
    // true of every rung.
    //
    // BOTH ARMS, still, for the opposite reason: the point is now that the two
    // rungs are INDISTINGUISHABLE by ear, so a card that reintroduced a fork in
    // either direction fails here.
    const books = renderFeedCard(
      makeData({
        opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
      })
    );
    const market = renderFeedCard(KALSHI_FINAL);

    for (const html of [books, market]) {
      expect(html).toContain("Pre-match probability: San Diego Padres");
      expect(html).not.toContain("sportsbooks opened");
      expect(html).not.toContain("the market gave");
    }
  });

  it("still carries the rung where a measurement can read it", () => {
    // Dropping the words must not drop the fact. The venue leaves the SPOKEN
    // sentence only — `data-prematch-source` and the visible marker are how the
    // hub, the capture suites and anyone auditing still tell the rungs apart,
    // and D65 did not ask for those.
    const books = renderFeedCard(
      makeData({
        opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
      })
    );

    expect(books).toContain('data-prematch-source="books"');
    expect(books).toContain("Pre-match · books");
    expect(renderFeedCard(KALSHI_FINAL)).toContain('data-prematch-source="kalshi"');
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

    // ux/1041 (#2689) — WAS `"Opened 60/40"`. This assertion's subject is that
    // the live card KEEPS the footer, and it still does; the pair is the same
    // pair. What moved is the side order: the footer printed home-first on a
    // card that lists the away team above the home team, which inverted the
    // favourite on 10 of 10 measured rows. Home is 60 here, away 40, so the
    // away-first footer reads 40/60. Updated rather than loosened to a regex,
    // because the specific digits are what make this a regression arm.
    expect(html).toContain("Opened 40/60");
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

  it("speaks the same venue-free sentence as /sports, on both rungs", () => {
    // D65. The two cards are separate components that each built the clause
    // privately, so "they agree" is a real assertion and not a tautology — the
    // phrase now has one owner (`PREMATCH_SAID` in `lib/prematchReading`) and
    // this is the test that notices if one of them stops reading it.
    const books = renderDiscoverCard(
      makeData({
        opening_odds: { home_probability: 0.6, away_probability: 0.4, favorite: "home" },
      })
    );
    const market = renderDiscoverCard(KALSHI_FINAL);

    for (const html of [books, market]) {
      expect(html).toContain("Pre-match probability: San Diego Padres");
      expect(html).not.toContain("sportsbooks opened");
      expect(html).not.toContain("the market gave");
    }
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
