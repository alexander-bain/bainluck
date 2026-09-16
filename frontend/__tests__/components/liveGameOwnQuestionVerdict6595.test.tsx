/**
 * ux/1302 (#6595) — A LIVE GAME PAGE STOPS DECLARING A WINNER.
 *
 * ═══ THE SPECIMEN ═══
 *
 * Production, `/events/15313117` (Minnesota Twins v New York Yankees, MLB) at
 * 390px, 2026-09-16 20:56Z. The hero read:
 *
 *     live · Bottom 11th · 3-3 · Twins 38%  Yankees 62%
 *
 * and one screen below it, Additional Markets read:
 *
 *     Minnesota Twins vs New York Yankees
 *       New York Yankees                                       Won
 *
 * A tied game, in extra innings, with the page crowning one side of it. The
 * BEFORE screenshot is `artifacts/ux-1302/BEFORE-6595-yankees-live-crowned.png`.
 *
 * ═══ WHY THE FILTER UPSTREAM COULD NOT SEE IT ═══
 *
 * `other[]` carried two markets asking the same question:
 *
 *   | market_name                            | rows | probs       | is_winner |
 *   |----------------------------------------|------|-------------|-----------|
 *   | `New York Yankees vs Minnesota`        | 2    | 0.62 / 0.38 | null      |
 *   | `New York Yankees vs. Minnesota Twins` | 1    | 1.0         | TRUE      |
 *
 * `findWinProbMarkets` removes the first exactly as designed — two
 * complementary rows summing to ~1.0 IS the hero's question. The second is a
 * stale weekly Polymarket container (`api_settlement`, observed 04:08Z, before
 * the 17:40Z first pitch) whose losing leg is gone, so it arrives as ONE row,
 * fails the `probs.length === 2` test, and renders.
 *
 * 🔴 That is the general shape: the redundancy filter recognises the hero's
 * question by its two-sided PRICE, and a fully-settled market collapses to one
 * leg — so the rows carrying a `Won` are the ones least visible to it.
 *
 * ═══ WHAT MOVED, AND WHERE ═══
 *
 * Not `outcomeRowVerdict` — it serves the futures surfaces, where a tier-3 leg
 * on an open market is the ordinary state of a threshold ladder (#6082). The
 * scope test is in `SpecialEventMarkets.outcomeVerdict`, which knows the event
 * status, and reads `marketIsTheGamesOwnQuestion`, which reuses
 * `canonicalMatchupTitle` rather than inventing a second vocabulary of period
 * words: a market is the game's own question exactly when that function yields
 * the BARE matchup.
 *
 * Only the VERDICT is withheld. The row keeps its label and its price, so the
 * card is still a card (#5540's floor), and `settled` still ends it.
 *
 * ═══ THE LABELS ═══
 *
 * `priceAgeMark4970.test.tsx`'s convention:
 *   SHIP     red against the parent. This is the change.
 *   GUARD    green against the parent, red against a NAMED mutant.
 *   CONTROL  green against both. It pins what must not move.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { marketIsTheGamesOwnQuestion } from "@/lib/otherMarketGroups";
import type { GameMarketsResponse } from "@/lib/api";

type WireRow = NonNullable<GameMarketsResponse["other"]>[number];

const HOME = "Minnesota Twins";
const AWAY = "New York Yankees";

/**
 * Verbatim wire, `GET /api/events/15313117/game-markets`, read 20:56Z
 * 2026-09-16 — all three `other` rows, unedited. The live Kalshi moneyline is
 * kept even though `findWinProbMarkets` eats it, because its presence is the
 * whole point: the page HAS a live two-sided price for this question and still
 * printed a winner from the other market.
 */
const WIRE: WireRow[] = [
  { market_name: "New York Yankees vs Minnesota", outcome_name: "New York Yankees", probability: 0.62, source: "kalshi", observed_at: "2026-09-16T20:56:23.554028+00:00", is_winner: null, resolution_source: null },
  { market_name: "New York Yankees vs Minnesota", outcome_name: "Minnesota", probability: 0.37, source: "kalshi", observed_at: "2026-09-16T20:56:23.554028+00:00", is_winner: null, resolution_source: null },
  { market_name: "New York Yankees vs. Minnesota Twins", outcome_name: "New York Yankees", probability: 1.0, source: "polymarket", observed_at: "2026-09-16T04:08:01.948721+00:00", is_winner: true, resolution_source: "api_settlement" },
];

/**
 * A graded question NARROWER than the game, in each of the two grammars the
 * venues actually write. These are the rows codex's 19:15Z assignment names by
 * hand — "preserve legitimate graded props during a live game; do not blanket
 * suppress all settled markets while live" — so they are fixtures, not prose.
 *
 * 🔴 BOTH CARDS CARRY THREE ROWS, AND THAT IS NOT PADDING. A two-row market
 * whose prices sum to ~1.0 is removed by `findWinProbMarkets` BEFORE any of
 * this ship's code runs — it reads as the hero's own question by shape — and a
 * settled pair is exactly `1.0 / 0.0`. The first cut of this fixture was two
 * rows per card, rendered nothing at all, and would have "passed" a withholding
 * mutant for a reason that has nothing to do with the rule under test. Three
 * rows is also what the venues actually ship for these (the measured ladder in
 * `specialEventMarketsGradedVerdict6138` carries nine).
 *
 * The colon card is the real production shape from that sibling fixture, with
 * this event's teams; the dash card is #6417's Polymarket grammar.
 */
const NARROWER: WireRow[] = [
  // Colon grammar: `canonicalMatchupTitle` refuses on the colon.
  //
  // The market NAME is the sibling fixture's measured one, not one written for
  // this file. A name containing the bare word `Winner` is removed upstream by
  // `isRedundantWithMarketMaps` ("written for the moneyline"), so the obvious
  // `…: 1st Inning Winner` also renders nothing — a second way this control
  // could have been vacuous for a reason unrelated to the rule under test.
  { market_name: "New York Yankees vs. Minnesota Twins: 1st Half / Fulltime Result", outcome_name: "Yankees win 1H / Yankees win game", probability: 1.0, source: "kalshi", observed_at: "2026-09-16T18:10:00+00:00", is_winner: true, resolution_source: "api_settlement" },
  { market_name: "New York Yankees vs. Minnesota Twins: 1st Half / Fulltime Result", outcome_name: "Twins win 1H / Yankees win game", probability: 0.0, source: "kalshi", observed_at: "2026-09-16T18:10:00+00:00", is_winner: false, resolution_source: "api_settlement" },
  { market_name: "New York Yankees vs. Minnesota Twins: 1st Half / Fulltime Result", outcome_name: "Tie 1H / Yankees win game", probability: 0.0, source: "kalshi", observed_at: "2026-09-16T18:10:00+00:00", is_winner: false, resolution_source: "api_settlement" },
  // Spaced-dash grammar (#6417): the qualifier is kept, so the canonical title
  // is not the bare matchup.
  { market_name: "New York Yankees vs. Minnesota Twins - 1st Half", outcome_name: "New York Yankees", probability: 1.0, source: "polymarket", observed_at: "2026-09-16T18:40:00+00:00", is_winner: true, resolution_source: "api_settlement" },
  { market_name: "New York Yankees vs. Minnesota Twins - 1st Half", outcome_name: "Minnesota Twins", probability: 0.0, source: "polymarket", observed_at: "2026-09-16T18:40:00+00:00", is_winner: false, resolution_source: "api_settlement" },
  { market_name: "New York Yankees vs. Minnesota Twins - 1st Half", outcome_name: "Tie", probability: 0.0, source: "polymarket", observed_at: "2026-09-16T18:40:00+00:00", is_winner: false, resolution_source: "api_settlement" },
];

function payload(
  other: WireRow[] = WIRE,
  overrides: Partial<GameMarketsResponse> = {},
): GameMarketsResponse {
  return {
    event_id: 15313117,
    home_team: HOME,
    away_team: AWAY,
    home_score: 3,
    away_score: 3,
    status: "live",
    totals: [],
    player_props: [],
    team_totals: [],
    spreads: [],
    period_markets: [],
    matchups: [],
    other,
    pace: null,
    ...overrides,
  } as unknown as GameMarketsResponse;
}

const render = (data: GameMarketsResponse, eventStatus = data.status) =>
  renderToStaticMarkup(<SpecialEventMarkets data={data} eventStatus={eventStatus} />);

/** The text of each verdict row, read off the ROW ELEMENT rather than a window. */
const verdictRows = (html: string): string[] =>
  Array.from(
    html.matchAll(/<div[^>]*data-testid="special-markets-verdict"[\s\S]*?<\/div><\/div>/g),
  ).map((m) =>
    m[0]
      .replace(/<[^>]*>/g, " ")
      .replace(/&#x27;/g, "'")
      .replace(/&amp;/g, "&")
      .replace(/\s+/g, " ")
      .trim(),
  );

const visible = (html: string) =>
  html
    .replace(/<[^>]*>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();

// ─────────────────────────────────────────────────────────────────────────────

describe("SHIP: a live game's own question carries no verdict", () => {
  test("the production specimen stops printing 'New York Yankees — Won'", () => {
    // Red against the parent, which rendered exactly this string over a 3-3
    // hero. This is the screenshot, as an assertion.
    const html = render(payload());
    expect(verdictRows(html)).toEqual([]);
    expect(visible(html)).not.toMatch(/New York Yankees\s+Won/);
    expect(html).not.toContain('data-verdict="won"');
  });

  test("the row is WITHHELD, not dropped — the card and its price survive", () => {
    // The failure mode this ship must not become. A guard that deletes the card
    // passes the test above and blanks a page whose only market is this one
    // (#5540's floor, and the 12-of-19 population lane1/379 measured on the
    // sibling half). The reader keeps the venue's number; they just are not
    // told it is a result.
    const html = render(payload());
    expect(visible(html)).toContain("New York Yankees");
    expect(visible(html)).toMatch(/100%|last quote/i);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe("CONTROL: settled means settled, and narrower questions keep their verdict", () => {
  test("the SAME payload on a completed game still crowns the winner", () => {
    // The single most important control: this ship withholds on the event's
    // state, so a mutant that withholds unconditionally — deleting the #6138
    // ship entirely — must go red here. Green on both arms.
    const html = render(payload(WIRE, { status: "completed" }), "completed");
    expect(verdictRows(html).some((r) => /New York Yankees\s+Won/.test(r))).toBe(true);
  });

  test.each([
    ["colon-scoped period market", "Fulltime Result"],
    ["dash-qualified period market", "- 1st Half"],
  ])("a graded %s keeps its verdict DURING the live game", (_label, needle) => {
    // #4788/#6082's ship, which this must not undo: a sub-game market that has
    // genuinely settled states its result while the game runs. Both venue
    // grammars, because `canonicalMatchupTitle` handles them by different
    // branches and a fix that only understood colons would silently withhold
    // every Polymarket period market.
    const html = render(payload(NARROWER));
    expect(verdictRows(html).length).toBeGreaterThan(0);
    expect(visible(html)).toContain(needle);
  });

  test("the withholding is SCOPED — the live moneyline loses its crown and the narrower questions keep theirs, on ONE page", () => {
    // The two halves stated together, because either alone is passable by a
    // mutant: withhold-everything passes the SHIP tests, withhold-nothing passes
    // the controls above. On a single live payload carrying both, exactly the
    // game's own question goes quiet.
    const html = render(payload([...WIRE, ...NARROWER]));
    const rows = verdictRows(html);
    expect(rows.length).toBe(2);
    expect(rows.every((r) => /\bWon\b/.test(r))).toBe(true);
    // The crowned Yankees row of the BARE matchup is not among them, though the
    // string "New York Yankees" is (it is the winner of both narrower cards).
    expect(rows.filter((r) => r.trim() === "New York Yankees Won")).toEqual([]);
  });

  test("DIFFERENTIAL: with no team names on the wire this ship is INERT", () => {
    // `marketIsTheGamesOwnQuestion` needs both names and returns false without
    // them, so a payload carrying neither renders exactly as it did before this
    // ship — the same fail-open door `canonicalMatchupTitle` already holds for
    // a caller with no event context (#5181). `undefined`, not `null`: absent
    // from the wire is the shape the type allows and the one production sends.
    const html = render(payload(WIRE, { home_team: undefined, away_team: undefined }));
    expect(html).toContain('data-verdict="won"');
    expect(verdictRows(html).some((r) => /New York Yankees\s+Won/.test(r))).toBe(true);
  });
});

// ─────────────────────────────────────────────────────────────────────────────

describe("GUARD: marketIsTheGamesOwnQuestion is the BARE matchup and nothing else", () => {
  /* Green against the parent (the function is new, but every case below is a
     statement about `canonicalMatchupTitle`, which is not). The mutant each
     kills: returning `canonical !== null` — i.e. "the name is a matchup" rather
     than "the name is the WHOLE question" — which would withhold every
     dash-qualified period market in the table above. */
  test.each([
    ["New York Yankees vs. Minnesota Twins", true, "the bare matchup, venue spelling"],
    ["Minnesota Twins vs New York Yankees", true, "the bare matchup, our order"],
    ["New York Yankees vs. Minnesota Twins: 1st Inning Winner", false, "colon ⇒ more than the matchup"],
    ["New York Yankees vs. Minnesota Twins - 1st Half", false, "dash qualifier is kept"],
    ["New York Yankees vs. Minnesota Twins: Race to 7 Points", false, "a scoring race is narrower"],
    ["Aaron Judge: Home Runs O/U 0.5", false, "not a matchup at all"],
    ["A vs B vs C", false, "three sides is not a matchup"],
    ["", false, "empty"],
  ])("%s → %s (%s)", (name, expected) => {
    expect(marketIsTheGamesOwnQuestion(name, HOME, AWAY)).toBe(expected);
  });

  test.each([
    [null, AWAY],
    [HOME, null],
    [null, null],
  ])("half a matchup (%s / %s) can never be the game's question", (home, away) => {
    // Fail-safe direction, and the mid-deploy case: without both names we
    // cannot know, so we do not withhold.
    expect(
      marketIsTheGamesOwnQuestion("New York Yankees vs. Minnesota Twins", home, away),
    ).toBe(false);
  });
});
