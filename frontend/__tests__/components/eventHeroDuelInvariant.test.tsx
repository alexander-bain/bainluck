// #2085 — THE EVENT PAGE HERO'S TWO NUMBERS ARE ONE ANSWER, asserted against output.
//
// `routes/events.py` derives the away side from the home side at FOUR sites —
// `hero_away_prob` (`round(1 - hero_home_prob, 6)`), the no-snapshot
// `current_odds` fallback, `hero_probability_away` (`round(1 - agg, 6)`), and
// `opening_odds.away_probability` (`opening_away_probability or
// round(1 - home, 4)`). Every pair this page can put on screen is therefore an
// exact complement BY CONSTRUCTION, and rounding the two sides independently
// prints 101 whenever `home * 100` lands on a half-percent. It can print 101; it
// can never print 99.
//
// MEASURED on the feed's population 2026-08-21: 34 of 414 (8.2%) scheduled/live
// events. The event page draws from the same blend.
//
// ## 🔴 WHY THIS FILE IS NOT A COPY OF `discoverEventCardDuelInvariant`
//
// The feed card may read `current_odds.{home,away}_rendered_percent`
// unconditionally, and says so in a comment, because it only ever renders a pair
// when that pair IS `current_odds`. THE EVENT PAGE IS NOT LIKE THAT. Its hero is
// `hero_probability` / `hero_probability_away` on a live game, `opening_odds`
// when settled, and a `history[]` row when a live game has no blend — three
// pairs the server ships no rendered percents for. Pasting the feed's one-liner
// here would print `current_odds`' rounding beside the BLEND's probability: a
// mismatched pair, served confidently, on the surface the blend ruling exists to
// protect. The "used on the right branch" and "NOT used on the wrong branch"
// tests below are the load-bearing ones in this file.
//
// ## Why it renders as well as calling the resolver
//
// A pure-library guard stays green if the JSX keeps its own
// `Math.round(homeProb * 100)` and ignores what the resolver decided — the
// library half passes while the screen is still wrong. `resolveProbability` is
// driven directly for the branch coverage a render cannot reach cheaply, and
// `EventHeroProbabilityPair` is RENDERED for the half that only output can prove.
// Both are needed and neither substitutes.
//
// Guards run BOTH directions per gotcha #43: a boundary pair is forced to 100,
// and an ordinary pair — 380 of the 414 measured events — is asserted UNCHANGED.

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";

import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import { resolveProbability } from "@/lib/eventKeyStats";
import type { EventDetailResponse, EventHistoryResponse } from "@/lib/types";

const REPO_ROOT = join(__dirname, "..", "..", "..");
const CONTRACT_PATH = join(REPO_ROOT, "contracts/rendered_percent.json");

interface DuelCase {
  away: number | null;
  home: number | null;
  percents: (number | null)[];
  naive: (number | null)[];
  complement_pair: boolean;
  discriminates?: boolean;
  $why?: string;
}

const contract = JSON.parse(readFileSync(CONTRACT_PATH, "utf8")) as {
  version: number;
  duel_cases: DuelCase[];
};

// The contract file is the shared table; a path typo would otherwise read as a
// clean pass over zero rows — the unrunnable-check failure mode.
const DUEL_CASES = contract.duel_cases;
const PRICED_PAIRS = DUEL_CASES.filter(
  (c) => c.away !== null && c.home !== null,
);
const DISCRIMINATING = PRICED_PAIRS.filter((c) => c.discriminates);

// ---------------------------------------------------------------------------
// Fixtures — one event shape, four branch selectors
// ---------------------------------------------------------------------------

function makeEvent(over: Record<string, unknown> = {}): EventDetailResponse {
  return {
    id: 15200290,
    home_team: "Denver Broncos",
    away_team: "Green Bay Packers",
    sport: "americanfootball_nfl",
    commence_time: "2030-01-01T12:00:00.000Z",
    status: "scheduled",
    ...over,
  } as unknown as EventDetailResponse;
}

function currentOdds(
  home: number | null,
  away: number | null,
  extra: Record<string, unknown> = {},
) {
  return {
    captured_at: "2030-01-01T11:00:00.000Z",
    home_probability: home,
    away_probability: away,
    bookmaker_count: 3,
    ...extra,
  };
}

/** SCHEDULED — the hero reads `current_odds`. */
function scheduled(home: number, away: number, extra: Record<string, unknown> = {}) {
  return resolveProbability(
    makeEvent({ current_odds: currentOdds(home, away, extra) }),
    undefined,
    null,
    false,
    false,
  );
}

/** LIVE WITH A BLEND — the hero reads `hero_probability` / `hero_probability_away`. */
function liveBlend(
  home: number,
  away: number,
  currentOddsOver: Record<string, unknown> | null = null,
) {
  return resolveProbability(
    makeEvent({
      status: "live",
      hero_probability: home,
      hero_probability_away: away,
      hero_probability_source: "blend",
      // Deliberately present, deliberately DIFFERENT, and carrying served
      // percents of its own — this is the pair a copy of the feed card's
      // one-liner would have printed.
      current_odds: currentOddsOver ?? currentOdds(0.34, 0.66, {
        home_rendered_percent: 34,
        away_rendered_percent: 66,
      }),
    }),
    undefined,
    null,
    true,
    false,
  );
}

/** SETTLED — the hero reads `opening_odds`. */
function settled(home: number, away: number) {
  return resolveProbability(
    makeEvent({
      status: "completed",
      opening_odds: { home_probability: home, away_probability: away },
      current_odds: currentOdds(0.34, 0.66, {
        home_rendered_percent: 34,
        away_rendered_percent: 66,
      }),
    }),
    undefined,
    null,
    false,
    true,
  );
}

/** LIVE, NO BLEND, and a history row more than 5 points away — the override branch. */
function liveHistoryOverride(home: number, away: number) {
  const history = {
    history: [
      {
        timestamp: "2030-01-01T11:30:00.000Z",
        home_probability: home,
        away_probability: away,
        bookmaker_count: 2,
      },
    ],
  } as unknown as EventHistoryResponse;
  return resolveProbability(
    makeEvent({
      status: "live",
      // No `hero_probability`, so the blend branch cannot fire. `current_odds`
      // is 40 points away, so the history row wins.
      current_odds: currentOdds(0.1, 0.9, {
        home_rendered_percent: 10,
        away_rendered_percent: 90,
      }),
    }),
    history,
    null,
    true,
    false,
  );
}

/** The two percents the hero actually PRINTS, [away, home]. */
function printedPercents(resolved: {
  homeProb: number | null;
  awayProb: number | null;
  homePct: number | null;
  awayPct: number | null;
}): number[] {
  const html = renderToStaticMarkup(
    <EventHeroProbabilityPair
      homeProb={resolved.homeProb}
      awayProb={resolved.awayProb}
      homePct={resolved.homePct}
      awayPct={resolved.awayPct}
      homeColor="#111827"
      awayColor="#94A3B8"
      probSourceLabel="test"
    />,
  );
  const nums = [...html.matchAll(/tabular-nums"[^>]*>(\d+)</g)].map((m) =>
    Number(m[1]),
  );
  if (nums.length !== 2) {
    throw new Error(
      `the hero did not render two percents (${nums.length}).\n${html}`,
    );
  }
  // The component prints HOME first, then AWAY. Returned away-first to match the
  // contract's `[away, home]` ordering everywhere else in this file.
  return [nums[1], nums[0]];
}

// ---------------------------------------------------------------------------

describe("the contract table this file is driven by", () => {
  it("is version 3 or later and carries the duel rows", () => {
    expect(contract.version).toBeGreaterThanOrEqual(3);
    expect(DUEL_CASES.length).toBeGreaterThanOrEqual(10);
    expect(DISCRIMINATING.length).toBeGreaterThanOrEqual(5);
  });

  it("every discriminating row would really have printed 101 naively", () => {
    // The assertion that makes the rest of the file mean something: if the
    // `naive` column ever stopped summing to 101, these cases would pass for a
    // reason that has nothing to do with the fix.
    for (const c of DISCRIMINATING) {
      const naive = (c.naive as number[])[0] + (c.naive as number[])[1];
      expect(naive).toBe(101);
      expect(Math.round(c.away! * 100) + Math.round(c.home! * 100)).toBe(101);
    }
  });
});

describe("every branch of the hero prints a pair that sums to 100", () => {
  const BRANCHES: Array<[string, (h: number, a: number) => ReturnType<typeof resolveProbability>]> = [
    ["scheduled (current_odds)", scheduled],
    ["live with a blend (hero_probability)", liveBlend],
    ["settled (opening_odds)", settled],
    ["live, no blend, history override", liveHistoryOverride],
  ];

  for (const [branch, resolve] of BRANCHES) {
    describe(branch, () => {
      it.each(DISCRIMINATING.map((c) => [c.$why ?? "", c] as const))(
        "%s",
        (_why, c) => {
          const resolved = resolve(c.home!, c.away!);
          expect(printedPercents(resolved)).toEqual([
            c.percents[0],
            c.percents[1],
          ]);
          expect(resolved.awayPct! + resolved.homePct!).toBe(100);
        },
      );

      it("leaves an ordinary pair untouched — the other direction (gotcha #43)", () => {
        const ordinary = PRICED_PAIRS.filter((c) => !c.discriminates);
        expect(ordinary.length).toBeGreaterThan(0);
        for (const c of ordinary) {
          expect(printedPercents(resolve(c.home!, c.away!))).toEqual([
            c.percents[0],
            c.percents[1],
          ]);
        }
      });

      it("does not move the probabilities themselves", () => {
        // Rendering-only, and it must stay that way — the chart's right edge,
        // the trend delta and `data-probability` all read these.
        const resolved = resolve(0.355, 0.645);
        expect(resolved.homeProb).toBe(0.355);
        expect(resolved.awayProb).toBe(0.645);
      });
    });
  }
});

describe("🔴 the served pair is attributed to its own source and no other", () => {
  it("IS used when the hero really is current_odds", () => {
    // 🔴 THE SERVED PAIR MUST BE ONE THE LOCAL RULE WOULD NOT HAVE PRODUCED.
    // The first version of this test served 32/68 for 0.325/0.675 — which is
    // exactly what `renderedDuelPercents` derives — so it passed whether the
    // client honoured the server or ignored it entirely. The mutation that
    // deletes `fromCurrentOdds = true` from the scheduled branch SURVIVED it.
    // 30/70 can only appear on screen by being read off the payload.
    //
    // Honouring it is the point: the server decides once for four surfaces, so
    // a rule change there must reach the screen without a client release.
    const resolved = scheduled(0.675, 0.325, {
      home_rendered_percent: 70,
      away_rendered_percent: 30,
    });
    expect([resolved.awayPct, resolved.homePct]).toEqual([30, 70]);
    expect(printedPercents(resolved)).toEqual([30, 70]);
    // …and the locally derived answer, which this must NOT be.
    expect(printedPercents(scheduled(0.675, 0.325))).toEqual([32, 68]);
  });

  it("is NOT used when the hero is the BLEND — the copy-paste trap", () => {
    // `current_odds` here is 0.34/0.66 with served percents 34/66. The hero is
    // the blend at 0.675/0.325. A reader that took the served pair
    // unconditionally would print 66 – 34 beside a 67.5% probability: a
    // mismatched pair, and `data-probability` would contradict the number
    // beside it. The 32/68 below is the BLEND's own pair.
    const resolved = liveBlend(0.675, 0.325);
    expect(resolved.homeProb).toBe(0.675);
    expect([resolved.awayPct, resolved.homePct]).toEqual([32, 68]);
    expect(printedPercents(resolved)).not.toEqual([66, 34]);
    expect(printedPercents(resolved)).toEqual([32, 68]);
  });

  it("is NOT used when a history row has replaced the pair", () => {
    // The override only fires when the two differ by more than 5 points, so
    // keeping the served pair would print a number off by at least five.
    const resolved = liveHistoryOverride(0.675, 0.325);
    expect(resolved.homeProb).toBe(0.675);
    expect(printedPercents(resolved)).toEqual([32, 68]);
  });

  it("is NOT used for a settled hero, which draws opening_odds", () => {
    const resolved = settled(0.675, 0.325);
    expect(printedPercents(resolved)).toEqual([32, 68]);
  });
});

describe("🔴 both served values or neither", () => {
  // One served value beside a locally derived one re-opens the same 101 from
  // the other direction, and an older deploy can carry one field and not the
  // other. 0.505/0.495 is the row where it shows: served home 51 with a naive
  // away of 50 sums to 101, which is the exact bug.
  it("falls back whole when only the home percent is served", () => {
    const resolved = scheduled(0.505, 0.495, { home_rendered_percent: 51 });
    expect(printedPercents(resolved)).toEqual([49, 51]);
    expect(resolved.awayPct! + resolved.homePct!).toBe(100);
  });

  it("falls back whole when only the away percent is served", () => {
    const resolved = scheduled(0.505, 0.495, { away_rendered_percent: 49 });
    expect(printedPercents(resolved)).toEqual([49, 51]);
    expect(resolved.awayPct! + resolved.homePct!).toBe(100);
  });

  it("falls back whole when neither is served — the pre-deploy payload", () => {
    const resolved = scheduled(0.505, 0.495);
    expect(printedPercents(resolved)).toEqual([49, 51]);
  });
});

describe("the opening line gets the same treatment", () => {
  // "Opened 50 – 51" was the same defect one line lower, and `opening_odds`
  // carries no served pair at any deploy, so it is always decided locally.
  it.each(DISCRIMINATING.map((c) => [c.$why ?? "", c] as const))(
    "%s",
    (_why, c) => {
      const resolved = resolveProbability(
        makeEvent({
          status: "live",
          hero_probability: 0.6,
          hero_probability_away: 0.4,
          hero_probability_source: "blend",
          opening_odds: { home_probability: c.home, away_probability: c.away },
        }),
        undefined,
        null,
        true,
        false,
      );
      expect([resolved.openingAwayPct, resolved.openingHomePct]).toEqual([
        c.percents[0],
        c.percents[1],
      ]);
      expect(resolved.openingAwayPct! + resolved.openingHomePct!).toBe(100);
    },
  );
});

describe("the states that have no pair still have no pair", () => {
  it("an unpriced side stays null rather than becoming a derived complement", () => {
    const resolved = resolveProbability(
      makeEvent({ current_odds: currentOdds(0.6, null) }),
      undefined,
      null,
      false,
      false,
    );
    expect(resolved.awayProb).toBeNull();
    expect(resolved.awayPct).toBeNull();
    expect(resolved.homePct).toBe(60);
  });

  it("a pair whose total is outside the band is not forced to one", () => {
    // sum 0.9. A game hero should never produce this, but the rule must not
    // invent a total for a pair that is not a pair.
    const resolved = scheduled(0.5, 0.4);
    expect([resolved.awayPct, resolved.homePct]).toEqual([40, 50]);
  });

  it("a withheld probability renders an em-dash, not a coin flip", () => {
    // UX-P042 (#1640): the whole evidence base is an untraded placeholder.
    const resolved = resolveProbability(
      makeEvent({
        status: "scheduled",
        current_odds: currentOdds(0.5, 0.5, { source: "aggregate", bookmaker_count: 0 }),
        win_probability_sources: {
          polymarket: {
            value: 0.5,
            display_name: "Polymarket",
            type: "prediction_market",
            color: "#000",
          },
        },
      }),
      undefined,
      null,
      false,
      false,
    );
    expect(resolved.homeProb).toBeNull();
    expect(resolved.homePct).toBeNull();
    const html = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={resolved.homeProb}
        awayProb={resolved.awayProb}
        homePct={resolved.homePct}
        awayPct={resolved.awayPct}
      />,
    );
    expect(html).toContain("—");
    expect(html).not.toMatch(/tabular-nums"[^>]*>\d/);
  });
});

describe("the component refuses to re-round on its own", () => {
  // The guard against the fix being quietly undone by a caller that stops
  // passing the decided percents: it must print an em-dash, not fall back to
  // `Math.round(prob * 100)`.
  it("prints an em-dash when a percent is missing even though the probability is not", () => {
    const html = renderToStaticMarkup(
      <EventHeroProbabilityPair
        homeProb={0.675}
        awayProb={0.325}
        homePct={null}
        awayPct={null}
      />,
    );
    expect(html).not.toContain("68");
    expect(html).not.toContain("33");
    expect(html).toContain("—");
  });
});
