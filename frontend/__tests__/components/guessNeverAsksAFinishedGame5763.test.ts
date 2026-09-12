// #5763 (p1) — Discover never asks a reader to guess the odds on a game that
// has already been played.
//
// MEASURED ON PRODUCTION 2026-09-12 22:05Z, Discover page one at 390px:
//
//   index  9  Pittsburgh Pirates @ Chicago Cubs   completed, final 4-3
//              -> (9 + 1) % 5 === 0, so the feed rendered
//                 "WHAT ARE THE ODDS? ... higher or lower than 68%?"
//                 with no score and no FINAL badge on the card
//   index 10  Elche CF @ Athletic Bilbao          completed, final 1-1
//              -> not a guess slot, correctly rendered as a FINAL card
//
// The second specimen is why this is the slot rule and not a coincidence.
//
// The grading number is worse than the question. The Cubs card served
// `current_odds.home_probability = 0.921` — an in-game reading frozen at the
// whistle — while `hero_probability` was 1.0 and the game was won. A reader who
// answered "higher" against the 68% threshold was marked against a number that
// had stopped being true.
//
// LATENT, MADE REACHABLE BY #4681/#5100, NOT A REASON TO REVERT THEM: before the
// marquee-final arm seated finals on page one, a `completed` event could not
// reach the first twenty cards and the missing status test cost nothing.
//
// TWO CALL SITES, ONE PREDICATE. `isGuessSlot` and `challengeItems` in
// `app/discover/page.tsx` each decided eligibility privately and disagreed:
// the challenge required a probability, the feed slot required only a type.
// Both now call `feedItemCanBeGuessed`, and the arms below assert BOTH
// conditions in BOTH directions (gotcha #43) so neither half can be dropped.

import type { FeedItem, FeedEventData } from "@/lib/types";
import { feedItemCanBeGuessed } from "@/components/discover/utils";

function eventItem(data: Partial<FeedEventData>): FeedItem {
  return {
    type: "event",
    headline: null,
    reason: "",
    score: 68,
    data: {
      id: 15310365,
      status: "live",
      commence_time: "2026-09-12T18:20:00Z",
      away_team: "Pittsburgh Pirates",
      home_team: "Chicago Cubs",
      sport: "baseball_mlb",
      current_odds: { home_probability: 0.921, away_probability: 0.079 },
      ...data,
    } as unknown as FeedEventData,
  } as unknown as FeedItem;
}

function futuresItem(probability: number | null): FeedItem {
  return {
    type: "futures",
    headline: null,
    reason: "",
    score: 50,
    data: {
      id: 113364,
      name: "Next French Presidential Election",
      status: "open",
      top_outcomes:
        probability === null
          ? [{ name: "Marine Le Pen" }]
          : [{ name: "Marine Le Pen", probability }],
    },
  } as unknown as FeedItem;
}

/** The production specimen, verbatim in the fields that decide. */
const CUBS_FINAL = eventItem({ status: "completed" });

describe("#5763 — who may be asked a 'higher or lower?' question", () => {
  it("refuses the finished game the feed actually asked about", () => {
    expect(feedItemCanBeGuessed(CUBS_FINAL)).toBe(false);
  });

  it("refuses a `closed` event as well as a `completed` one", () => {
    expect(feedItemCanBeGuessed(eventItem({ status: "closed" }))).toBe(false);
  });

  it("refuses a settled game even though it still carries live-looking odds", () => {
    // The specimen's own trap: the settled card DOES have
    // `current_odds.home_probability`, so a fix written as "require a
    // probability" alone would have let this exact card through.
    const settledWithOdds = eventItem({
      status: "completed",
      current_odds: { home_probability: 0.921, away_probability: 0.079 },
    } as Partial<FeedEventData>);

    expect(settledWithOdds.data).toHaveProperty("current_odds.home_probability", 0.921);
    expect(feedItemCanBeGuessed(settledWithOdds)).toBe(false);
  });

  it("still asks a live game — the question the card exists for", () => {
    expect(feedItemCanBeGuessed(eventItem({ status: "live" }))).toBe(true);
  });

  it("still asks a scheduled game", () => {
    expect(feedItemCanBeGuessed(eventItem({ status: "scheduled" }))).toBe(true);
  });

  it("refuses an unsettled game with no probability to grade against", () => {
    // The half `challengeItems` already had and `isGuessSlot` did not. Without
    // it `GuessCard` falls back to `actualProb ?? 0` and asks a question whose
    // answer is 0%.
    const noOdds = eventItem({ status: "live", current_odds: undefined } as Partial<FeedEventData>);

    expect(feedItemCanBeGuessed(noOdds)).toBe(false);
  });

  it("still asks a futures market with a priced leader, and refuses one without", () => {
    expect(feedItemCanBeGuessed(futuresItem(0.35))).toBe(true);
    expect(feedItemCanBeGuessed(futuresItem(null))).toBe(false);
  });

  it("refuses the card types that were never eligible, and a missing item", () => {
    expect(feedItemCanBeGuessed({ type: "bundle", data: {} } as unknown as FeedItem)).toBe(false);
    expect(feedItemCanBeGuessed(null)).toBe(false);
  });
});

describe("#5763 — both call sites ask the shared predicate", () => {
  // A SOURCE SCAN, DELIBERATELY, and it is doing work no render test here can.
  // `app/discover/page.tsx` is a client page whose quiz slot depends on
  // `gamesUnlocked`, SWR data, localStorage cohorts and an IntersectionObserver;
  // a rendered arm would prove the composition of all of those, not the rule.
  // What must not silently come back is a SECOND private eligibility test, and
  // that is a property of the source. The arms above are the behaviour.
  const source = require("fs").readFileSync(
    require("path").join(__dirname, "..", "..", "app", "discover", "page.tsx"),
    "utf8",
  ) as string;

  it("uses the predicate in the feed's every-fifth-card slot", () => {
    const line = source.split("\n").find((l) => l.includes("const isGuessSlot"));
    expect(line).toBeDefined();
    expect(line).toContain("feedItemCanBeGuessed(gi.item)");
  });

  it("uses it in the daily challenge's question pool too", () => {
    const block = source.slice(
      source.indexOf("const challengeItems"),
      source.indexOf("const incrementDailyGuesses"),
    );
    expect(block).toContain("feedItemCanBeGuessed(gi.item)");
  });

  it("leaves no private status or probability test beside it in either block", () => {
    // The exact shapes the two sites used to carry. Scoped to the two blocks,
    // not the whole file, so an unrelated probability read elsewhere on the page
    // cannot red this.
    const slot = source.slice(
      source.indexOf("const isGuessSlot"),
      source.indexOf("const analytics = getGroupedAnalytics(gi)"),
    );
    const pool = source.slice(
      source.indexOf("const challengeItems"),
      source.indexOf("const incrementDailyGuesses"),
    );

    for (const block of [slot, pool]) {
      expect(block).not.toContain('gi.item!.type === "futures"');
      expect(block).not.toContain("top_outcomes?.[0]?.probability");
      expect(block).not.toContain("current_odds?.home_probability");
    }
  });
});
