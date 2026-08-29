/**
 * Q441 (#1495) — a finished game's tab title, link preview and Google result lead
 * with the RESULT instead of publishing the losing team as the favorite.
 *
 * RED-FIRST against master: the two production specimens below are the exact
 * strings bainluck.com served on 2026-08-29, both verified against ESPN.
 */

import {
  buildEventShareCopy,
  isSettledForShare,
  withSiteSuffix,
  type EventShareMetaInput,
} from "@/lib/eventShareMeta";

/**
 * Production, 2026-08-29. `before` is the description the site actually served;
 * it is kept verbatim so this file fails loudly if anyone reverts the copy.
 */
const PRODUCTION_SPECIMENS = [
  {
    id: 15294037,
    event: {
      home_team: "Villanova Wildcats",
      away_team: "William and Mary Tribe",
      home_score: 32,
      away_score: 35,
      status: "completed",
      hero_probability_source: "settled",
      hero_settled_result: "away",
      current_odds: { home_probability: 0.8199, away_probability: 0.1801 },
    } as EventShareMetaInput,
    before:
      "Final. Bain Luck gives Villanova Wildcats a 82% win probability and William and Mary Tribe a 18% win probability.",
    winner: "William and Mary Tribe",
    loser: "Villanova Wildcats",
  },
  {
    id: 15291335,
    event: {
      home_team: "Carolina Panthers",
      away_team: "Houston Texans",
      home_score: 16,
      away_score: 13,
      status: "completed",
      hero_probability_source: "settled",
      hero_settled_result: "home",
      current_odds: { home_probability: 0.4859, away_probability: 0.5141 },
    } as EventShareMetaInput,
    before:
      "Final. Bain Luck gives Carolina Panthers a 49% win probability and Houston Texans a 51% win probability.",
    winner: "Carolina Panthers",
    loser: "Houston Texans",
  },
];

describe("settled events lead with the result", () => {
  it.each(PRODUCTION_SPECIMENS)(
    "$id names the winner instead of a probability",
    ({ event, before, winner, loser }) => {
      const copy = buildEventShareCopy(event);

      expect(copy.settled).toBe(true);
      expect(copy.description).not.toBe(before);
      expect(copy.description).toContain(winner);
      expect(copy.description).toContain(loser);
      // the whole defect in one assertion
      expect(copy.description).not.toMatch(/win probability/);
      expect(copy.title).not.toMatch(/%/);
      expect(copy.title).toContain(winner);
    },
  );

  it.each(PRODUCTION_SPECIMENS)(
    "$id prints the winner's score first",
    ({ event, winner }) => {
      const copy = buildEventShareCopy(event);
      const hs = event.home_score as number;
      const as_ = event.away_score as number;
      const hi = Math.max(hs, as_);
      const lo = Math.min(hs, as_);
      expect(copy.description).toBe(
        `Final: ${winner} beat ${
          winner === event.home_team ? event.away_team : event.home_team
        } ${hi}-${lo}.`,
      );
    },
  );

  it("never leads with a probability for a settled game", () => {
    for (const { event } of PRODUCTION_SPECIMENS) {
      expect(buildEventShareCopy(event).description).not.toMatch(/\d+%/);
    }
  });
});

describe("the kill — a probability is still the right answer when nothing settled", () => {
  const unsettled: EventShareMetaInput = {
    home_team: "Celtics",
    away_team: "76ers",
    status: "scheduled",
    commence_time: "2026-09-02T23:00:00Z",
    hero_probability_source: "blend",
    current_odds: { home_probability: 0.65, away_probability: 0.35 },
  };

  it("keeps the probability copy verbatim for a scheduled game", () => {
    const copy = buildEventShareCopy(unsettled);
    expect(copy.settled).toBe(false);
    expect(copy.title).toBe("76ers vs Celtics: Celtics 65%, 76ers 35%");
    expect(copy.description).toContain("win probability");
  });

  it("keeps the probability copy for a live game", () => {
    const copy = buildEventShareCopy({ ...unsettled, status: "live" });
    expect(copy.settled).toBe(false);
    expect(copy.description).toContain("Live now.");
  });

  it("a `closed` event is NOT settled for share purposes", () => {
    // closed scores are frozen mid-game and invert the winner; the backend
    // withholds the "settled" source for exactly that reason, and this module
    // must not second-guess it from `status` alone.
    const closed: EventShareMetaInput = {
      ...unsettled,
      status: "closed",
      home_score: 3,
      away_score: 1,
      hero_probability_source: "blend",
    };
    expect(isSettledForShare(closed)).toBe(false);
    expect(buildEventShareCopy(closed).settled).toBe(false);
  });

  it("a settled source with no score does not claim a result", () => {
    expect(
      isSettledForShare({
        hero_probability_source: "settled",
        home_score: null,
        away_score: null,
      }),
    ).toBe(false);
  });

  it("falls back cleanly when there is no probability at all", () => {
    const copy = buildEventShareCopy({
      home_team: "Celtics",
      away_team: "76ers",
      status: "scheduled",
      commence_time: "2026-09-02T23:00:00Z",
      current_odds: null,
    });
    expect(copy.title).toBe("76ers vs Celtics Odds");
    expect(copy.description).toContain("probability-first odds");
  });
});

describe("draws are explicit (criterion 4)", () => {
  it("says drew, and names neither team a winner", () => {
    const copy = buildEventShareCopy({
      home_team: "Watford",
      away_team: "Peterborough United",
      home_score: 2,
      away_score: 2,
      status: "completed",
      hero_probability_source: "settled",
      hero_settled_result: "draw",
      current_odds: { home_probability: 0.6492, away_probability: 0.3508 },
    });
    expect(copy.settled).toBe(true);
    expect(copy.description).toBe("Final: Watford and Peterborough United drew 2-2.");
    expect(copy.description).not.toMatch(/beat|won/);
    expect(copy.title).toContain("a draw");
  });
});

describe("the doubled site suffix (#1495 secondary)", () => {
  it("the page title carries NO suffix — the root template adds it", () => {
    for (const { event } of PRODUCTION_SPECIMENS) {
      expect(buildEventShareCopy(event).title).not.toMatch(/\| Bain Luck/);
    }
    expect(
      buildEventShareCopy({
        home_team: "Celtics",
        away_team: "76ers",
        status: "scheduled",
        current_odds: { home_probability: 0.65, away_probability: 0.35 },
      }).title,
    ).not.toMatch(/\| Bain Luck/);
  });

  it("withSiteSuffix adds exactly one, and is idempotent", () => {
    expect(withSiteSuffix("Celtics vs 76ers")).toBe("Celtics vs 76ers | Bain Luck");
    expect(withSiteSuffix("Celtics vs 76ers | Bain Luck")).toBe(
      "Celtics vs 76ers | Bain Luck",
    );
  });
});
