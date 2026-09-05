/**
 * #3330 — THE LIVE TENNIS HERO STOPS PRINTING TWO ZEROES OVER A MATCH IT
 * ALREADY HOLDS THE GAMES FOR.
 *
 * Alex, phone-width LOOK of `/events/15304419` (Zheng v Gea, badge LIVE, 5-5 in
 * the first set):
 *
 *   >  MZ          49% – 51%          AG
 *   > Zheng                          Gea
 *   >  0                              0
 *
 * Zero sets each is TRUE. It is also the least informative true statement
 * available and is indistinguishable from a match that has not started — while
 * the Games map four sections down the same page drew `ACTUAL 11 games`.
 *
 * ── THE FIXTURES ARE PRODUCTION ROWS, NOT INVENTED ONES ─────────────────────
 *
 * Both lines below were read from the production `events` table on 2026-09-05
 * (`box_score_data->'tennis'`) while the matches were in play, and each one is
 * kept with the set score its own row carried, because the pairing of the two
 * is the thing under test.
 *
 * `15304420` is the sharper exhibit and the reason this is worth shipping
 * rather than merely worth having: the hero printed `1 – 0` for Bergs — ahead
 * on sets — while he was LOSING the second set 1-4. The two big numbers were
 * not just thin, they pointed the wrong way about where the match was heading.
 */
import {
  liveHeroGamesLine,
  resolveEventOutcome,
} from "@/lib/eventOutcome";

/** Bergs v van de Zandschulp, LIVE: home won set 1 6-3, trails set 2 1-4. */
const BERGS_LIVE = {
  sets: [
    [6, 3],
    [1, 4],
  ] as [number, number][],
};

/** Zheng v Gea, LIVE: home lost set 1 6-7, leads set 2 5-3. Home 0 sets, away 1. */
const ZHENG_LIVE = {
  sets: [
    [6, 7],
    [5, 3],
  ] as [number, number][],
};

/** Bucsa v Gauff, COMPLETED 0–2: the settled arm's fixture. */
const GAUFF_DONE = {
  sets: [
    [3, 6],
    [4, 6],
  ] as [number, number][],
};

const LIVE = { isFinished: false, isLive: true, hasStarted: true };

describe("#3330 — the games, while it is still being played", () => {
  it("prints the line a live hero was hiding", () => {
    expect(liveHeroGamesLine({ ...LIVE, linescore: BERGS_LIVE })).toBe("6-3, 1-4");
  });

  it("answers the exhibit: two zeroes become a match at 5-3 in the second", () => {
    // The hero's own numbers here are `0` and `1` — SETS. Neither of them is
    // any part of this string, which is the whole point: the line is not the
    // two numbers again, it is the answer to the question they raise.
    expect(liveHeroGamesLine({ ...LIVE, linescore: ZHENG_LIVE })).toBe("6-7, 5-3");
  });

  /**
   * THE ORIENTATION GUARD. `sets` is stated in OUR home/away order and the hero
   * renders home in the left column, so home's games are printed first.
   *
   * Asserted against the REVERSED string explicitly, and on a fixture where
   * reversing is visible: `6-3, 1-4` and `3-6, 4-1` are both plausible-looking
   * tennis lines, so a positional flip here would not announce itself in a
   * screenshot — it would just credit the wrong player with the set. This is
   * the one failure the whole feature has to avoid.
   */
  it("puts HOME first, and a flipped read is caught", () => {
    // BOTH directions asserted on purpose. A bare `not.toBe(reversed)` is
    // satisfied by the empty string, so on its own it would stay green for a
    // hero that had stopped rendering entirely — which is the very bug this
    // suite exists for. Verified by mutation: with the helper stubbed to `""`
    // the negative assertions alone still passed.
    expect(liveHeroGamesLine({ ...LIVE, linescore: BERGS_LIVE })).toBe("6-3, 1-4");
    expect(liveHeroGamesLine({ ...LIVE, linescore: BERGS_LIVE })).not.toBe("3-6, 4-1");
    expect(liveHeroGamesLine({ ...LIVE, linescore: ZHENG_LIVE })).toBe("6-7, 5-3");
    expect(liveHeroGamesLine({ ...LIVE, linescore: ZHENG_LIVE })).not.toBe("7-6, 3-5");
  });

  /**
   * THE CONTROL THAT PINS WHY `orientLinescore` IS NOT USED HERE.
   *
   * `lib/linescore.ts`'s `orientLinescore` re-points a line by entity key and
   * REFUSES when it cannot — correct for the tournament slate, which re-orders
   * its sides. This payload carries no entity keys at all, so routing the hero
   * through that helper would refuse every row and print nothing.
   *
   * This test states the contract as a fixture: a line with NO entity keys must
   * still render. If someone "adds orientation" for safety, this goes red and
   * says why, instead of the hero silently going blank on production.
   */
  it("renders a line that carries no entity keys — it must not require them", () => {
    const bare = { sets: [[6, 4]] as [number, number][] };
    expect(Object.keys(bare)).not.toContain("home_entity_key");
    expect(liveHeroGamesLine({ ...LIVE, linescore: bare })).toBe("6-4");
  });

  describe("when the hero must not print one", () => {
    it("refuses a FINISHED match — the settled hero already prints it", () => {
      expect(
        liveHeroGamesLine({
          isFinished: true,
          isLive: false,
          hasStarted: true,
          linescore: GAUFF_DONE,
        })
      ).toBe("");
    });

    /**
     * And the settled hero really does print it, WINNER-first — so the refusal
     * above is not a gap, it is the two heroes not printing the same games
     * twice in two different orders.
     *
     * Gauff is away and won 2–0, so her games lead: `6-3, 6-4`, which is the
     * REVERSE of the stored home-first `[[3,6],[4,6]]`. That both orders are
     * correct on their own surface is exactly why one function may not serve
     * both.
     */
    it("...because the settled one does, winner-first — the control", () => {
      const settled = resolveEventOutcome({
        isFinished: true,
        homeTeam: "Cristina Bucsa",
        awayTeam: "Coco Gauff",
        homeScore: 0,
        awayScore: 2,
        linescore: GAUFF_DONE,
      });
      expect(settled?.resultLine).toBe("6-3, 6-4");
    });

    it("refuses a match that has not started", () => {
      expect(
        liveHeroGamesLine({
          isFinished: false,
          isLive: false,
          hasStarted: false,
          linescore: BERGS_LIVE,
        })
      ).toBe("");
    });

    /**
     * The every-other-sport control. An NBA hero prints 112 and 108 and carries
     * no linescore; this must be byte-for-byte what it was, which for the hero
     * means an empty string and no element rendered at all.
     */
    it("says nothing when the event carries no line", () => {
      expect(liveHeroGamesLine({ ...LIVE })).toBe("");
      expect(liveHeroGamesLine({ ...LIVE, linescore: null })).toBe("");
    });

    /**
     * A line with no sets in it is an absence wearing a shape — the same rule
     * `playedUnits` states for the same payload. `0 – 0` under a live hero is
     * the bug this issue is about; an empty chip under it would be worse.
     */
    it("says nothing for a line with no sets", () => {
      expect(liveHeroGamesLine({ ...LIVE, linescore: { sets: [] } })).toBe("");
    });
  });
});
