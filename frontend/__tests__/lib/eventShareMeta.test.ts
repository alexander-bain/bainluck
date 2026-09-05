/**
 * Q441 (#1495) — a finished game's tab title, link preview and Google result lead
 * with the RESULT instead of publishing the losing team as the favorite.
 *
 * RED-FIRST against master: the two production specimens below are the exact
 * strings bainluck.com served on 2026-08-29, both verified against ESPN.
 */

import {
  buildEventShareCopy,
  isFinishedForShare,
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

/**
 * CERT-1938's block — the SECOND authority.
 *
 * The first cut of this module gated on the score alone, so a decided tennis match
 * still published a forecast. Specimen read off production 2026-09-05:
 *
 *   /events/15293846  <title>… Matteo Berrettini 84%, Stan Wawrinka 16% …</title>
 *
 * Berrettini had won it 7-6, 7-6, 6-0 on 2026-08-30. The row is `closed`, so the
 * score rung correctly declines it — and `/api/tournaments/by-event/15293846`
 * named the winner all along.
 */
describe("the tournament rung (CERT-1938) — a decided match with no trusted score", () => {
  // The event exactly as production serves it: `closed`, scores present but NOT
  // trusted (the backend withholds the "settled" source), blend still on the row.
  const BERRETTINI_EVENT: EventShareMetaInput = {
    home_team: "Matteo Berrettini",
    away_team: "Stan Wawrinka",
    home_score: 3,
    away_score: 0,
    status: "closed",
    hero_probability_source: "blend",
    current_odds: { home_probability: 0.8411, away_probability: 0.1589 },
  };

  // What `resolveEventOutcome` returns for it once the container answers.
  const TOURNAMENT_OUTCOME = {
    winnerName: "Berrettini",
    winnerSide: "home" as const,
    resultLine: "7-6, 7-6, 6-0",
    resultExplanation: "7-6, 7-6, 6-0, winner's games first.",
    resultKind: "score" as const,
    authority: "tournament" as const,
  };

  it("leads with the winner and the set line, not the 84%", () => {
    const copy = buildEventShareCopy(BERRETTINI_EVENT, TOURNAMENT_OUTCOME);
    expect(copy.settled).toBe(true);
    expect(copy.title).toBe(
      "Stan Wawrinka vs Matteo Berrettini: Matteo Berrettini won 7-6, 7-6, 6-0",
    );
    expect(copy.description).toBe(
      "Final: Matteo Berrettini beat Stan Wawrinka 7-6, 7-6, 6-0.",
    );
    // The exact string production served, and the shape of it.
    expect(copy.title).not.toMatch(/84%|16%/);
    expect(copy.description).not.toMatch(/win probability/);
  });

  it("names the winner with the EVENT's full name, not the hero's short one", () => {
    // The hero prints "Berrettini" in a badge; a page title and a shared link get
    // the whole name. `winnerName` is the fallback, not the first choice.
    const copy = buildEventShareCopy(BERRETTINI_EVENT, TOURNAMENT_OUTCOME);
    expect(copy.title).toContain("Matteo Berrettini won");
    expect(copy.title).not.toContain("Berrettini won 7-6, 7-6, 6-0 |");
  });

  it("does NOT read the untrusted `closed` scores back in under the tournament rung", () => {
    // The row carries 3 and 0. The score rung refused them (frozen mid-game
    // scores invert the winner in 2 of 8 sampled rows); wording the tournament's
    // answer with them would smuggle them back in.
    const copy = buildEventShareCopy(BERRETTINI_EVENT, TOURNAMENT_OUTCOME);
    expect(copy.title).not.toContain("3-0");
    expect(copy.description).not.toContain("3-0");
  });

  it("still names a winner the ladder could not place on a side", () => {
    // An unmatched winner gets named, but nobody gets called the loser.
    const copy = buildEventShareCopy(BERRETTINI_EVENT, {
      ...TOURNAMENT_OUTCOME,
      winnerSide: null,
      winnerName: "Berrettini",
    });
    expect(copy.settled).toBe(true);
    expect(copy.title).toContain("Berrettini won 7-6, 7-6, 6-0");
    expect(copy.description).toBe("Final: Berrettini won 7-6, 7-6, 6-0.");
    expect(copy.description).not.toContain("beat");
  });

  it("a winner with no score line says so rather than inventing one", () => {
    const copy = buildEventShareCopy(BERRETTINI_EVENT, {
      ...TOURNAMENT_OUTCOME,
      resultLine: null,
    });
    expect(copy.title).toBe(
      "Stan Wawrinka vs Matteo Berrettini: Matteo Berrettini won",
    );
    expect(copy.description).toBe("Final: Matteo Berrettini beat Stan Wawrinka.");
  });

  it("the score rung's wording is unchanged by the new rung existing", () => {
    // Regression on the OTHER specimen: passing a score-authority outcome must
    // produce byte-for-byte what the no-outcome call already produces, or adding
    // the tournament rung silently restyled every settled team game.
    const { event } = PRODUCTION_SPECIMENS[0];
    const viaLadder = buildEventShareCopy(event, {
      winnerName: "Tribe",
      winnerSide: "away",
      resultLine: null,
      resultExplanation: null,
      resultKind: null,
      authority: "score",
    });
    expect(viaLadder).toEqual(buildEventShareCopy(event));
  });
});

describe("finished with NO authority — explicit no-result, never a stale forecast", () => {
  const FINISHED_UNKNOWN: EventShareMetaInput = {
    home_team: "Matteo Berrettini",
    away_team: "Stan Wawrinka",
    home_score: 3,
    away_score: 0,
    status: "closed",
    hero_probability_source: "blend",
    current_odds: { home_probability: 0.8411, away_probability: 0.1589 },
  };

  it("says Final and states we do not hold the result", () => {
    const copy = buildEventShareCopy(FINISHED_UNKNOWN, null);
    expect(copy.settled).toBe(false);
    expect(copy.title).toBe("Stan Wawrinka vs Matteo Berrettini: Final");
    expect(copy.description).toBe(
      "Final. Bain Luck does not have a confirmed result for Stan Wawrinka vs Matteo Berrettini yet.",
    );
  });

  it("publishes NO probability on a finished game — the whole point", () => {
    const copy = buildEventShareCopy(FINISHED_UNKNOWN, null);
    expect(copy.title).not.toMatch(/\d+%/);
    expect(copy.description).not.toMatch(/\d+%/);
    expect(copy.description).not.toMatch(/win probability/);
  });

  it("a `completed` game with no scores and no container gets it too", () => {
    const copy = buildEventShareCopy({
      home_team: "Celtics",
      away_team: "76ers",
      status: "completed",
      home_score: null,
      away_score: null,
      hero_probability_source: "blend",
      current_odds: { home_probability: 0.65, away_probability: 0.35 },
    });
    expect(copy.settled).toBe(false);
    expect(copy.description).not.toMatch(/win probability/);
    expect(copy.description).toContain("does not have a confirmed result");
  });

  it("does NOT touch a scheduled or live game", () => {
    // The kill for this rung: withholding a forecast is only right once the
    // question is closed.
    for (const status of ["scheduled", "live"]) {
      const copy = buildEventShareCopy({
        home_team: "Celtics",
        away_team: "76ers",
        status,
        commence_time: "2026-09-02T23:00:00Z",
        current_odds: { home_probability: 0.65, away_probability: 0.35 },
      });
      expect(copy.description).toContain("win probability");
    }
  });

  it("isFinishedForShare is wider than the score gate, and knows it", () => {
    expect(isFinishedForShare({ status: "completed" })).toBe(true);
    expect(isFinishedForShare({ status: "closed" })).toBe(true);
    expect(isFinishedForShare({ status: "live" })).toBe(false);
    expect(isFinishedForShare({ status: "scheduled" })).toBe(false);
    expect(isFinishedForShare({})).toBe(false);
  });
});
