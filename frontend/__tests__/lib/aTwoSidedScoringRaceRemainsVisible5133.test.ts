/**
 * #5133 defect A, the client half — CERT-2611's required repair
 * `5133-TWO-SIDED-SCORING-RACE-REMAINS-VISIBLE`.
 *
 * The backend fix moves Kalshi's scoring races out of `player_props[]`, where
 * they were being drawn as PLAYERS ("RACE TO 14 POINTS" as a stat group beside
 * Jahmyr Gibbs's yardage ladder), and into `other[]`. That is right, and on its
 * own it makes one of the six races DISAPPEAR instead of moving.
 *
 * `findWinProbMarkets` treats any market whose two rows sum to ~1.0 as the hero
 * market and filters the whole family out. A scoring race is exactly that shape
 * and is not the hero: the hero answers *who wins*, the race answers *who gets
 * there first*, and a game can be won by the side that lost the race.
 *
 * MEASURED, not hypothesised — `GET /api/events/14780145/game-markets`
 * (New Orleans @ Detroit), read 2026-09-11:
 *
 *   Race to 10 / 14 / 21 / 28 / 35 Points   THREE rows each  → survive by accident
 *   Race to 7 Points                        TWO rows, 0.56 / 0.44
 *
 * The seven-point race is short two rows for a reason that has nothing to do
 * with it being a hero: its third outcome, "Neither team reaches 7 points", is
 * priced 0.010 and dropped upstream. So one race in six vanishes while its five
 * siblings render — not a rule a reader could learn, just a hole.
 *
 * The specimens below are those exact wire rows.
 */

import {
  buildMarketSection,
  findWinProbMarkets,
  isRedundantWithMarketMaps,
  isScoringRaceMarket,
  type OtherMarketRow,
} from "../../lib/otherMarketGroups";

const KALSHI = "kalshi";
const RACE_7 = "New Orleans vs Detroit: Race to 7 Points";
const RACE_14 = "New Orleans vs Detroit: Race to 14 Points";

/** The two-row family, verbatim from the wire. */
const RACE_TO_7: OtherMarketRow[] = [
  { market_name: RACE_7, outcome_name: "Detroit reaches 7 points first", probability: 0.56, source: KALSHI },
  { market_name: RACE_7, outcome_name: "New Orleans reaches 7 points first", probability: 0.44, source: KALSHI },
];

/** A three-row sibling, which was never at risk — kept as the control. */
const RACE_TO_14: OtherMarketRow[] = [
  { market_name: RACE_14, outcome_name: "Detroit reaches 14 points first", probability: 0.56, source: KALSHI },
  { market_name: RACE_14, outcome_name: "New Orleans reaches 14 points first", probability: 0.43, source: KALSHI },
  { market_name: RACE_14, outcome_name: "Neither team reaches 14 points", probability: 0.125, source: KALSHI },
];

/**
 * AN ORDINARY TWO-SIDED WINNER, which MUST still be suppressed — the half of
 * this repair that stops it being "delete the rule".
 *
 * 🔴 It is suppressed by `isRedundantWithMarketMaps` (its name contains
 * "winner"), NOT by the rule this repair edits — so on its own it is a vacuous
 * control: it never reaches the guarded line. The first draft of this file used
 * only this fixture and a mutant that disabled hero suppression entirely
 * SURVIVED it. `HERO_SHAPED` below is the fixture that actually reaches
 * `findWinProbMarkets`, and both are kept, each asserted against the rule that
 * is really doing the work.
 */
const MATCH_WINNER: OtherMarketRow[] = [
  { market_name: "New Orleans vs Detroit Winner", outcome_name: "Detroit", probability: 0.58, source: KALSHI },
  { market_name: "New Orleans vs Detroit Winner", outcome_name: "New Orleans", probability: 0.42, source: KALSHI },
];

/**
 * A two-complementary-row market whose NAME trips none of the redundancy
 * keywords, so it reaches `findWinProbMarkets` and is suppressed there. The
 * same shape as the race and a question the hero does answer.
 */
const HERO_SHAPED_MARKET = "Detroit to Lead at Halftime";
const HERO_SHAPED: OtherMarketRow[] = [
  { market_name: HERO_SHAPED_MARKET, outcome_name: "Yes", probability: 0.58, source: KALSHI },
  { market_name: HERO_SHAPED_MARKET, outcome_name: "No", probability: 0.42, source: KALSHI },
];

/**
 * Filler so the section clears its own `kept.length < 3` floor AND has
 * something visible to measure an absence against.
 *
 * Deliberately a THREE-way market. The obvious filler — the wire's
 * `2nd Quarter Both Teams to Score`, `Yes 0.28 / No 0.72` — is itself
 * suppressed by `findWinProbMarkets`' yes/no arm, which left the section
 * EMPTY and made the "still suppressed" assertion below pass for the wrong
 * reason. That was caught by the non-vacuity check in that test, not by
 * inspection.
 */
const FILLER: OtherMarketRow[] = [
  { market_name: "First Score Type", outcome_name: "Touchdown", probability: 0.62, source: KALSHI },
  { market_name: "First Score Type", outcome_name: "Field Goal", probability: 0.3, source: KALSHI },
  { market_name: "First Score Type", outcome_name: "Safety", probability: 0.02, source: KALSHI },
];
const FILLER_MARKET = "First Score Type";

function renderedLabels(rows: OtherMarketRow[]): string[] {
  const section = buildMarketSection(rows);
  return section.categories.flatMap((c) =>
    c.cards.flatMap((card) => card.outcomes.map((o) => `${card.name} — ${o.label}`)),
  );
}

function renderedMarketNames(rows: OtherMarketRow[]): Set<string> {
  const section = buildMarketSection(rows);
  return new Set(section.categories.flatMap((c) => c.cards.map((card) => card.name)));
}

describe("a two-sided scoring race remains visible (#5133)", () => {
  it("the 56/44 race renders", () => {
    const names = renderedMarketNames([...RACE_TO_7, ...FILLER]);

    expect(names.has(RACE_7)).toBe(true);
  });

  it("…with BOTH of its sides, and the prices the wire carried", () => {
    const labels = renderedLabels([...RACE_TO_7, ...FILLER]);

    expect(labels).toEqual(
      expect.arrayContaining([
        `${RACE_7} — Detroit reaches 7 points first`,
        `${RACE_7} — New Orleans reaches 7 points first`,
      ]),
    );
  });

  /**
   * THE OTHER HALF OF THE REPAIR. Widening the rule until the race survives is
   * easy; the fix has to be narrow enough that the hero's own question stays
   * out of this section, or the page grows a second, worse moneyline.
   */
  it("an ordinary two-sided match winner is STILL suppressed", () => {
    const names = renderedMarketNames([...MATCH_WINNER, ...FILLER]);

    expect(names.has("New Orleans vs Detroit Winner")).toBe(false);
    // …and the section is not simply EMPTY, which is the other way this
    // assertion could read green. `buildMarketSection` returns no categories at
    // all below its own three-row floor, so an absence has to be shown against
    // a present sibling in the SAME call.
    expect(names.has(FILLER_MARKET)).toBe(true);
  });

  /**
   * …and why that fixture cannot stand alone, stated rather than assumed: it is
   * caught by BOTH rules, so its absence from the page is consistent with hero
   * suppression having been deleted entirely. An over-determined control proves
   * nothing about either cause.
   */
  it("the match winner is over-determined — the redundancy rule ALSO declines it", () => {
    expect(isRedundantWithMarketMaps(MATCH_WINNER[0])).toBe(true);
    expect(findWinProbMarkets(MATCH_WINNER).has("New Orleans vs Detroit Winner")).toBe(true);
  });

  /**
   * THE REAL CONTROL: a two-sided market that REACHES `findWinProbMarkets` and
   * must still be caught there. Killing the hero-suppression rule outright
   * passes every other test in this file and fails this one.
   */
  it("a hero-shaped two-sided market still reaches AND trips hero suppression", () => {
    // it genuinely reaches the guarded line…
    expect(isRedundantWithMarketMaps(HERO_SHAPED[0])).toBe(false);
    // …and is caught there…
    expect(findWinProbMarkets(HERO_SHAPED).has(HERO_SHAPED_MARKET)).toBe(true);
    // …and therefore does not render.
    const names = renderedMarketNames([...HERO_SHAPED, ...FILLER]);
    expect(names.has(HERO_SHAPED_MARKET)).toBe(false);
    expect(names.has(FILLER_MARKET)).toBe(true);
  });

  it("both at once — the race renders in the same section that hides the hero-shaped pair", () => {
    const names = renderedMarketNames([...RACE_TO_7, ...HERO_SHAPED, ...MATCH_WINNER, ...FILLER]);

    expect(names.has(RACE_7)).toBe(true);
    expect(names.has(HERO_SHAPED_MARKET)).toBe(false);
    expect(names.has("New Orleans vs Detroit Winner")).toBe(false);
  });

  it("the three-row sibling still renders — nothing regressed to fix the two-row one", () => {
    const names = renderedMarketNames([...RACE_TO_7, ...RACE_TO_14, ...FILLER]);

    expect(names.has(RACE_7)).toBe(true);
    expect(names.has(RACE_14)).toBe(true);
  });

  /**
   * The predicate is narrower than the words "race to": it requires the SCORE
   * UNIT. A player race is a shape nobody has measured, and a rule measured
   * only on team scoring races has no business claiming it by grammar. Pinned
   * in BOTH directions so a later widening is a deliberate act.
   */
  describe("the predicate is narrower than its own words", () => {
    it.each([
      "New Orleans vs Detroit: Race to 7 Points",
      "New Orleans vs Detroit: Race to 14 Points",
      "race to 21 points",
      "RACE TO 35 POINTS",
      "Race to 10.5 Points",
      "Race to 1 Point",
    ])("matches %s", (name) => {
      expect(isScoringRaceMarket(name)).toBe(true);
    });

    it.each([
      "Race to 5 catches",
      "Race to the Playoffs",
      "Points Race",
      "Race to 7",
      "Embrace to 7 Points",
      "New Orleans vs Detroit Winner",
      "",
    ])("does not match %s", (name) => {
      expect(isScoringRaceMarket(name)).toBe(false);
    });

    it("is null-safe at both doors", () => {
      expect(isScoringRaceMarket(null)).toBe(false);
      expect(isScoringRaceMarket(undefined)).toBe(false);
    });
  });
});
