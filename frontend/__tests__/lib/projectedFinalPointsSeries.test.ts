/**
 * #10239 — projected final points: what counts as a reading, and what never does.
 *
 * Fixture: an NFL game, Chicago at home to Philadelphia, kickoff 00:16Z,
 * final 03:10Z, final score 27–7. The shape follows the approved v24 replay
 * (forecast-experiment.md). A reading of 26.5 for Chicago after Chicago
 * already had 27 is withheld. The last valid pair, 27.0 / 7.5, stays apart
 * from the 27–7 result, and readings at or after the server-recorded
 * completion boundary (`completed_at`, not an observed whistle) are dropped.
 */

import {
  buildProjectedFinalPointsSeries,
  firstRecordedGameStateAt,
  inspectionInstants,
  MAX_CAPTURE_GAP_MS,
  pickProjectionSportsbook,
  projectedFinalPointsInputFromHistory,
  seriesAt,
  type ProjectedFinalPointsInput,
  type ProjectedFinalPointsSeries,
} from "@/lib/projectedFinalPointsSeries";
import type { EventHistoryResponse } from "@/lib/types";

const KICKOFF = "2026-09-29T00:16:00Z";
const FINAL = "2026-09-29T03:10:00Z";
const ms = (iso: string) => Date.parse(iso);

function nflInput(over: Partial<ProjectedFinalPointsInput> = {}): ProjectedFinalPointsInput {
  return {
    sportKey: "americanfootball_nfl",
    sourceKey: "draftkings",
    basis: "same_book_same_capture_full_game_spread_and_total",
    pairs: [
      { timestamp: "2026-09-28T21:00:00Z", home: 24.0, away: 20.5, homeProbability: 0.6 },
      { timestamp: "2026-09-28T23:30:00Z", home: 24.5, away: 20.0, homeProbability: 0.62 },
      { timestamp: "2026-09-29T00:30:00Z", home: 27.5, away: 17.0, homeProbability: 0.75 },
      { timestamp: "2026-09-29T01:00:00Z", home: null, away: null },
      { timestamp: "2026-09-29T01:20:00Z", home: 28.0, away: 13.5, homeProbability: 0.9 },
      { timestamp: "2026-09-29T01:40:00Z", home: Number.NaN, away: 12.0 },
      { timestamp: "2026-09-29T02:30:00Z", home: 27.0, away: 9.5, homeProbability: 0.97 },
      { timestamp: "2026-09-29T03:08:00Z", home: 26.5, away: 8.3, homeProbability: 0.99 },
      { timestamp: "2026-09-29T03:09:00Z", home: 27.0, away: 7.5, homeProbability: 0.99 },
      { timestamp: "2026-09-29T03:11:00Z", home: 27.0, away: 7.0, homeProbability: 0.99 },
      { timestamp: "2026-09-29T03:12:00Z", home: 27.0, away: 7.0, homeProbability: 0.99 },
    ],
    actuals: [
      // A pregame 0–0 row is not an actual score history.
      { timestamp: "2026-09-28T23:50:00Z", home_score: 0, away_score: 0 },
      { timestamp: "2026-09-29T00:24:00Z", home_score: 7, away_score: 0 },
      { timestamp: "2026-09-29T01:15:00Z", home_score: 14, away_score: 7 },
      { timestamp: "2026-09-29T02:10:00Z", home_score: 21, away_score: 7 },
      { timestamp: "2026-09-29T03:06:00Z", home_score: 27, away_score: 7 },
    ],
    kickoffAt: KICKOFF,
    finalAt: FINAL,
    asOf: "2026-09-29T04:00:00Z",
    ...over,
  };
}

function supported(input: ProjectedFinalPointsInput): ProjectedFinalPointsSeries {
  const s = buildProjectedFinalPointsSeries(input);
  if (!s.supported) throw new Error(`expected a supported series, got ${s.reason}`);
  return s;
}

const allPoints = (s: ProjectedFinalPointsSeries) => s.segments.flat();

describe("sport and source admission", () => {
  it.each([
    ["baseball_mlb"],
    ["soccer_epl"],
    ["tennis_atp_us_open"],
    ["golf_pga_championship_winner"],
    ["basketball_nba"],
    [null],
  ])("refuses %s even with well-formed pairs", (sportKey) => {
    expect(buildProjectedFinalPointsSeries(nflInput({ sportKey }))).toEqual({
      supported: false,
      reason: "sport_not_supported",
    });
  });

  it("refuses a source it cannot name to the reader", () => {
    expect(buildProjectedFinalPointsSeries(nflInput({ sourceKey: "mystery_book" }))).toEqual({
      supported: false,
      reason: "source_not_named",
    });
  });

  it("draws nothing from no pairs, or from pairs that are all unusable", () => {
    expect(buildProjectedFinalPointsSeries(nflInput({ pairs: [] }))).toEqual({
      supported: false,
      reason: "no_valid_pair",
    });
    const unusable = nflInput({
      pairs: [
        { timestamp: "2026-09-29T00:30:00Z", home: 24, away: null },
        { timestamp: "2026-09-29T00:40:00Z", home: Infinity, away: 10 },
      ],
    });
    expect(buildProjectedFinalPointsSeries(unusable)).toEqual({ supported: false, reason: "no_valid_pair" });
  });
});

describe("after the final", () => {
  const s = supported(nflInput());

  it("is the after phase and ends the window at the recorded completion boundary", () => {
    expect(s.phase).toBe("after");
    expect(s.end).toBe(ms(FINAL));
  });

  it("keeps home and away oriented as served, in points", () => {
    const first = allPoints(s).find((p) => p.at === ms("2026-09-29T00:30:00Z"));
    expect(first).toMatchObject({ home: 27.5, away: 17.0 });
  });

  it("withholds a projection below the score already recorded", () => {
    expect(s.withheld).toContainEqual({ at: ms("2026-09-29T03:08:00Z"), reason: "below_recorded_score" });
    expect(allPoints(s).some((p) => p.home === 26.5)).toBe(false);
  });

  it("never appends the 27–7 final to the forecast line", () => {
    expect(s.latest).toMatchObject({ home: 27.0, away: 7.5, at: ms("2026-09-29T03:09:00Z") });
    expect(allPoints(s).some((p) => p.home === 27 && p.away === 7)).toBe(false);
    expect(allPoints(s).every((p) => p.at < ms(FINAL))).toBe(true);
    expect(s.latestActual).toMatchObject({ home: 27, away: 7 });
  });

  it("drops readings stamped after the final, not even as gaps", () => {
    const after = [...allPoints(s).map((p) => p.at), ...s.withheld.map((w) => w.at)].filter(
      (t) => t >= ms(FINAL),
    );
    expect(after).toEqual([]);
  });

  it("does not treat a reading stamped at the completion boundary as a forecast", () => {
    const input = nflInput();
    input.pairs = [...input.pairs, { timestamp: FINAL, home: 27.0, away: 7.0, homeProbability: 0.99 }];
    const t = supported(input);
    expect(t.latest.at).toBe(ms("2026-09-29T03:09:00Z"));
    expect(allPoints(t).some((p) => p.at === ms(FINAL))).toBe(false);
  });

  it("breaks the line at a missing pair and at a non-number, and never bridges them", () => {
    expect(s.withheld).toContainEqual({ at: ms("2026-09-29T01:00:00Z"), reason: "pair_incomplete" });
    expect(s.withheld).toContainEqual({ at: ms("2026-09-29T01:40:00Z"), reason: "not_a_number" });
    for (const seg of s.segments) {
      for (const w of s.withheld) {
        expect(w.at > seg[0].at && w.at < seg[seg.length - 1].holdEnd).toBe(false);
      }
    }
  });

  it("keeps a single valid reading between two gaps as its own run", () => {
    const lone = s.segments.find((seg) => seg[0].at === ms("2026-09-29T01:20:00Z"));
    expect(lone).toHaveLength(1);
    expect(lone![0].holdEnd).toBe(lone![0].at);
  });

  it("starts actual steps at the first score after kickoff, with no invented 0–0", () => {
    expect(s.actualSteps[0]).toEqual({ at: ms("2026-09-29T00:24:00Z"), home: 7, away: 0 });
    expect(s.actualSteps.some((a) => a.at < ms(KICKOFF))).toBe(false);
  });

  it("does not flag the latest stretch when the last reading is usable and recent", () => {
    expect(s.latestIntervalUnavailable).toBe(false);
  });

  it("flags the latest stretch when the newest reading before the final was unusable", () => {
    const input = nflInput();
    input.pairs = [...input.pairs, { timestamp: "2026-09-29T03:09:30Z", home: null, away: 7 }];
    const t = supported(input);
    expect(t.latestIntervalUnavailable).toBe(true);
    expect(t.latest.at).toBe(ms("2026-09-29T03:09:00Z"));
  });

  it("uses a points grid with headroom over every drawn value", () => {
    expect(s.yTicks[0]).toBe(0);
    expect(s.yTicks[1] - s.yTicks[0]).toBe(7);
    expect(s.yMax).toBeGreaterThanOrEqual(28);
  });
});

describe("contradictions and orientation", () => {
  it("withholds a pair whose leader contradicts the same book's moneyline", () => {
    const s = supported(
      nflInput({
        pairs: [
          { timestamp: "2026-09-29T00:30:00Z", home: 20, away: 24, homeProbability: 0.8 },
          { timestamp: "2026-09-29T00:40:00Z", home: 24, away: 20, homeProbability: 0.8 },
        ],
      }),
    );
    expect(s.withheld).toEqual([{ at: ms("2026-09-29T00:30:00Z"), reason: "contradicts_moneyline" }]);
    expect(allPoints(s).map((p) => p.home)).toEqual([24]);
  });

  it("does not swap or complement a side", () => {
    const s = supported(nflInput({ pairs: [{ timestamp: "2026-09-29T00:30:00Z", home: 17, away: 23.5 }] }));
    expect(s.latest).toMatchObject({ home: 17, away: 23.5 });
  });
});

describe("before kickoff", () => {
  const s = supported(nflInput({ kickoffAt: null, finalAt: null, asOf: "2026-09-29T00:00:00Z" }));

  it("has no actual steps, even with a pregame 0–0 row in the payload", () => {
    expect(s.phase).toBe("before");
    expect(s.actualSteps).toEqual([]);
    expect(s.latestActual).toBeNull();
  });

  it("shows only readings up to now", () => {
    expect(s.latest).toMatchObject({ home: 24.5, away: 20.0 });
    expect(allPoints(s).every((p) => p.at <= ms("2026-09-29T00:00:00Z"))).toBe(true);
  });
});

describe("during the game, nothing from later leaks in", () => {
  const live = nflInput({ finalAt: null, asOf: "2026-09-29T01:30:00Z" });
  const s = supported(live);

  it("reads only what existed at now", () => {
    expect(s.phase).toBe("during");
    expect(s.latest).toMatchObject({ home: 28.0, away: 13.5 });
    expect(s.latestActual).toMatchObject({ home: 14, away: 7 });
    expect(s.actualSteps.every((a) => a.at <= ms("2026-09-29T01:30:00Z"))).toBe(true);
  });

  it("an inspected moment stops at the cursor", () => {
    const fin = supported(nflInput());
    const cursor = ms("2026-09-29T00:30:00Z");
    const at = seriesAt(nflInput(), cursor);
    if (!at.supported) throw new Error("expected supported");
    expect(at.latest).toMatchObject({ home: 27.5, away: 17.0 });
    expect(at.latestActual).toMatchObject({ home: 7, away: 0 });
    expect(allPoints(at).every((p) => p.at <= cursor)).toBe(true);
    expect(at.withheld.every((w) => w.at <= cursor)).toBe(true);
    // Same window as the full view, so the drawn x positions do not jump.
    expect(at.start).toBe(fin.start);
  });

  it("a pregame cursor keeps the full window rather than re-anchoring on itself", () => {
    const fin = supported(nflInput());
    const at = seriesAt(nflInput(), ms("2026-09-28T23:30:00Z"));
    if (!at.supported) throw new Error("expected supported");
    expect(at.start).toBe(fin.start);
    expect(at.actualSteps).toEqual([]);
  });

  it("lists every inspectable instant, gaps included, oldest first", () => {
    const fin = supported(nflInput());
    const instants = inspectionInstants(fin);
    expect(instants).toEqual([...instants].sort((a, b) => a - b));
    expect(instants).toContain(ms("2026-09-29T01:00:00Z"));
    expect(instants).toContain(ms("2026-09-29T03:08:00Z"));
    expect(instants).not.toContain(ms("2026-09-29T03:11:00Z"));
  });
});

describe("holds come from recorded captures only", () => {
  it("breaks the line when the next capture is recorded long after this one", () => {
    const s = supported(
      nflInput({
        pairs: [
          { timestamp: "2026-09-29T00:20:00Z", home: 24, away: 20 },
          { timestamp: "2026-09-29T02:30:00Z", home: 27, away: 9.5 },
        ],
      }),
    );
    expect(s.segments).toHaveLength(2);
    expect(s.segments[0][0].holdEnd).toBe(ms("2026-09-29T00:20:00Z"));
  });

  it("joins captures recorded within the gap tolerance", () => {
    const s = supported(
      nflInput({
        pairs: [
          { timestamp: "2026-09-29T00:20:00Z", home: 24, away: 20 },
          { timestamp: new Date(ms("2026-09-29T00:20:00Z") + MAX_CAPTURE_GAP_MS - 60_000).toISOString(), home: 27, away: 13 },
        ],
      }),
    );
    expect(s.segments).toHaveLength(1);
  });

  it("never carries a capture from before the window into it", () => {
    const s = supported(
      nflInput({
        pairs: [
          { timestamp: "2026-09-26T12:00:00Z", home: 23.5, away: 21 },
          { timestamp: "2026-09-29T00:30:00Z", home: 27.5, away: 17, homeProbability: 0.75 },
        ],
      }),
    );
    expect(allPoints(s).map((p) => p.at)).toEqual([ms("2026-09-29T00:30:00Z")]);
    expect(allPoints(s).some((p) => p.at < s.start)).toBe(false);
  });
});

describe("reading a served history payload", () => {
  const history = {
    completed_at: FINAL,
    // The aggregate line is never read: its buckets mix whichever books wrote that minute.
    history: [
      {
        timestamp: "2026-09-29T00:30:00Z",
        home_probability: 0.7,
        away_probability: 0.3,
        over_under: 44,
        projected_home_score: 99,
        projected_away_score: 99,
        bookmaker: "consensus",
      },
    ],
    bookmaker_history: {
      draftkings: [
        { timestamp: "2026-09-29T00:30:00Z", home_probability: 0.75, away_probability: 0.25, projected_home_score: 27.5, projected_away_score: 17, valid_until: "2026-09-29T00:50:00Z" },
        { timestamp: "2026-09-29T01:00:00Z", home_probability: 0.8, away_probability: 0.2, projected_home_score: 28, projected_away_score: 14 },
      ],
      fanduel: [
        { timestamp: "2026-09-29T00:30:00Z", home_probability: 0.75, away_probability: 0.25, projected_home_score: 27, projected_away_score: 17 },
      ],
      unnamed_book: [
        { timestamp: "2026-09-29T00:30:00Z", home_probability: 0.75, away_probability: 0.25, projected_home_score: 27, projected_away_score: 17 },
        { timestamp: "2026-09-29T00:31:00Z", home_probability: 0.75, away_probability: 0.25, projected_home_score: 27, projected_away_score: 17 },
        { timestamp: "2026-09-29T00:32:00Z", home_probability: 0.75, away_probability: 0.25, projected_home_score: 27, projected_away_score: 17 },
      ],
    },
    score_history: [{ timestamp: "2026-09-29T00:24:00Z", home_score: 7, away_score: 0 }],
  } as unknown as EventHistoryResponse;

  it("picks the named sportsbook with the most complete pairs", () => {
    expect(pickProjectionSportsbook(history)).toBe("draftkings");
    expect(pickProjectionSportsbook({ bookmaker_history: {} })).toBeNull();
  });

  it("reads one book's own series and the recorded score, never the aggregate line", () => {
    const input = projectedFinalPointsInputFromHistory(history, {
      sportKey: "americanfootball_nfl",
      sourceKey: "draftkings",
      kickoffAt: KICKOFF,
      asOf: "2026-09-29T04:00:00Z",
      cutoffAt: null,
    });
    expect(input.basis).toBe("same_book_same_capture_full_game_spread_and_total");
    expect(input.finalAt).toBe(FINAL);
    expect(input.pairs.map((p) => p.home)).toEqual([27.5, 28]);
    expect(input.pairs[0]).toMatchObject({ homeProbability: 0.75 });
    // `valid_until` is continuity, not confirmation: it never reaches the input.
    expect(input.pairs.every((p) => !("heldUntil" in p) && !("valid_until" in p))).toBe(true);
    const s = supported(input);
    expect(allPoints(s).some((p) => p.home === 99)).toBe(false);
    expect(s.sourceName).toBe("DraftKings");
  });
});

describe("the default window", () => {
  it("opens an hour before kickoff once the game has started, so the game gets the width", () => {
    const s = supported(nflInput());
    expect(s.start).toBe(ms(KICKOFF) - 60 * 60 * 1000);
    // A pregame reading from before the window is not drawn.
    expect(allPoints(s).some((p) => p.at === ms("2026-09-28T21:00:00Z"))).toBe(false);
  });

  it("looks back six hours from now before kickoff", () => {
    const s = supported(nflInput({ kickoffAt: null, finalAt: null, asOf: "2026-09-29T00:00:00Z" }));
    expect(s.start).toBe(ms("2026-09-29T00:00:00Z") - 6 * 60 * 60 * 1000);
  });
});

describe("rows the route re-stamped at its window cutoff", () => {
  const cutoffAt = "2026-09-28T23:30:00Z";
  const history = {
    completed_at: null,
    bookmaker_history: {
      draftkings: [
        // Captured days earlier, still valid at the cutoff: served AT the cutoff minute.
        { timestamp: cutoffAt, home_probability: 0.6, away_probability: 0.4, projected_home_score: 24, projected_away_score: 20.5, valid_until: "2026-09-29T00:25:00Z" },
        { timestamp: "2026-09-29T00:30:00Z", home_probability: 0.75, away_probability: 0.25, projected_home_score: 27.5, projected_away_score: 17 },
      ],
    },
    score_history: [{ timestamp: "2026-09-29T00:24:00Z", home_score: 7, away_score: 0 }],
  } as unknown as EventHistoryResponse;
  const opts = { sportKey: "americanfootball_nfl", sourceKey: "draftkings", kickoffAt: KICKOFF, asOf: "2026-09-29T01:00:00Z" };

  it("marks a row at the request cutoff synthetic and never admits it", () => {
    const input = projectedFinalPointsInputFromHistory(history, { ...opts, cutoffAt });
    expect(input.pairs.map((p) => p.kind)).toEqual(["synthetic", "recorded"]);
    const s = supported(input);
    expect(allPoints(s).map((p) => p.at)).toEqual([ms("2026-09-29T00:30:00Z")]);
  });

  it("without a cutoff (a finished game's whole series) every row is a recorded capture", () => {
    const input = projectedFinalPointsInputFromHistory(history, { ...opts, cutoffAt: null });
    expect(input.pairs.map((p) => p.kind)).toEqual(["recorded", "recorded"]);
  });
});

/**
 * The producer (`odds_polling.py::_create_or_update_snapshot`) sets the OLD
 * row's `valid_until = now` when the values CHANGE, just before writing the
 * new row. So `valid_until` on a replaced pair is the first capture of a
 * DIFFERENT pair. Recorded 00:00, replaced 03:00, old `valid_until` 03:00:
 * nothing recorded the three hours between.
 */
describe("a changed reading after a long gap (valid_until is not confirmation)", () => {
  const history = {
    completed_at: null,
    bookmaker_history: {
      draftkings: [
        { timestamp: "2026-09-29T00:20:00Z", home_probability: 0.6, away_probability: 0.4, projected_home_score: 24, projected_away_score: 20.5, valid_until: "2026-09-29T03:20:00Z" },
        { timestamp: "2026-09-29T03:20:00Z", home_probability: 0.9, away_probability: 0.1, projected_home_score: 30, projected_away_score: 14 },
      ],
    },
    score_history: [{ timestamp: "2026-09-29T00:24:00Z", home_score: 7, away_score: 0 }],
  } as unknown as EventHistoryResponse;
  const opts = { sportKey: "americanfootball_nfl", sourceKey: "draftkings", kickoffAt: KICKOFF, cutoffAt: null };

  it("does not bridge the three hours: two runs, the first ending at its own capture", () => {
    const s = supported(projectedFinalPointsInputFromHistory(history, { ...opts, asOf: "2026-09-29T03:30:00Z" }));
    expect(s.segments).toHaveLength(2);
    expect(s.segments[0]).toEqual([{ at: ms("2026-09-29T00:20:00Z"), home: 24, away: 20.5, holdEnd: ms("2026-09-29T00:20:00Z") }]);
    expect(s.segments[1][0].at).toBe(ms("2026-09-29T03:20:00Z"));
  });

  it("before the change lands, the old valid_until cannot hide that nothing usable came since", () => {
    // Reader at 02:00 sees only the 00:20 row; its served valid_until says 03:20.
    const early = {
      ...history,
      bookmaker_history: { draftkings: history.bookmaker_history!.draftkings!.slice(0, 1) },
    } as unknown as EventHistoryResponse;
    const s = supported(projectedFinalPointsInputFromHistory(early, { ...opts, asOf: "2026-09-29T02:00:00Z" }));
    expect(s.latest).toEqual({ at: ms("2026-09-29T00:20:00Z"), home: 24, away: 20.5, holdEnd: ms("2026-09-29T00:20:00Z") });
    expect(s.latestIntervalUnavailable).toBe(true);
  });

  it("a pre-window row whose valid_until reaches into the window is not pulled in", () => {
    const s = supported(
      projectedFinalPointsInputFromHistory(history, { ...opts, asOf: "2026-09-29T03:30:00Z" }),
    );
    // Window opens an hour before kickoff (23:16); fake an earlier capture held "through" it.
    const withOld = {
      ...history,
      bookmaker_history: {
        draftkings: [
          { timestamp: "2026-09-28T20:00:00Z", home_probability: 0.6, away_probability: 0.4, projected_home_score: 23, projected_away_score: 21, valid_until: "2026-09-29T00:20:00Z" },
          ...history.bookmaker_history!.draftkings!,
        ],
      },
    } as unknown as EventHistoryResponse;
    const t = supported(projectedFinalPointsInputFromHistory(withOld, { ...opts, asOf: "2026-09-29T03:30:00Z" }));
    expect(t.segments).toEqual(s.segments);
    expect(allPoints(t).some((p) => p.home === 23)).toBe(false);
  });
});

describe("the first recorded game state floors actual scores, and is not a kickoff", () => {
  // 00:20Z: an instrument's first look at the first quarter. Nobody saw the kick.
  const FLOOR = "2026-09-29T00:20:00Z";

  it("without an observed kickoff and without a floor, a finished game admits no actual scores", () => {
    const s = supported(nflInput({ kickoffAt: null }));
    expect(s.phase).toBe("after");
    expect(s.actualSteps).toEqual([]);
    expect(s.latestActual).toBeNull();
  });

  it("the floor admits recorded scores from itself on, and nothing before it", () => {
    const s = supported(nflInput({ kickoffAt: null, scoreObservationStartAt: FLOOR }));
    expect(s.actualSteps.map((a) => [a.home, a.away])).toEqual([[7, 0], [14, 7], [21, 7], [27, 7]]);
    expect(s.actualSteps.some((a) => a.at < ms(FLOOR))).toBe(false);
    expect(s.latestActual).toMatchObject({ home: 27, away: 7 });
  });

  it("an observed kickoff, when there is one, still decides the floor", () => {
    const s = supported(nflInput({ kickoffAt: KICKOFF, scoreObservationStartAt: "2026-09-29T01:30:00Z" }));
    expect(s.actualSteps[0]).toEqual({ at: ms("2026-09-29T00:24:00Z"), home: 7, away: 0 });
  });

  it("a cursor before the floor is before the game state: no actuals, and none borrowed from later", () => {
    const input = nflInput({ kickoffAt: null, scoreObservationStartAt: FLOOR });
    const v = seriesAt(input, ms("2026-09-29T00:10:00Z"));
    expect(v.supported && v.phase).toBe("before");
    expect(v.supported && v.actualSteps).toEqual([]);
    const during = seriesAt(input, ms("2026-09-29T01:20:00Z"));
    expect(during.supported && during.phase).toBe("during");
    expect(during.supported && during.latestActual).toMatchObject({ home: 14, away: 7 });
  });

  it("opens the default window an hour before the floor", () => {
    const s = supported(nflInput({ kickoffAt: null, scoreObservationStartAt: FLOOR }));
    expect(s.start).toBe(ms(FLOOR) - 60 * 60 * 1000);
  });
});

describe("firstRecordedGameStateAt", () => {
  const q1 = { timestamp: "2026-09-29T00:17:50Z", period: "1st Quarter", source: "espn_state", precision: "first_seen", not_before: "2026-09-29T00:16:50Z" };

  it("reads the observed first-quarter marker's lower bound, not its timestamp", () => {
    expect(firstRecordedGameStateAt([q1], "americanfootball_nfl")).toBe("2026-09-29T00:16:50Z");
  });

  it("takes the earliest bound when two instruments saw the first quarter", () => {
    const other = { ...q1, source: "statpal", precision: "boundary_observed", not_before: "2026-09-29T00:15:30Z" };
    expect(firstRecordedGameStateAt([q1, other], "americanfootball_nfl")).toBe("2026-09-29T00:15:30Z");
  });

  it("refuses an estimate even when it is the earliest", () => {
    const est = { ...q1, source: "estimated", not_before: "2026-09-29T00:00:00Z" };
    expect(firstRecordedGameStateAt([est, q1], "americanfootball_nfl")).toBe("2026-09-29T00:16:50Z");
    expect(firstRecordedGameStateAt([est], "americanfootball_nfl")).toBeNull();
  });

  it("refuses an unknown source, a first-score marker, a missing bound and a later quarter", () => {
    expect(firstRecordedGameStateAt([{ ...q1, source: "someone" }], "americanfootball_nfl")).toBeNull();
    expect(firstRecordedGameStateAt([{ ...q1, precision: "first_score" }], "americanfootball_nfl")).toBeNull();
    expect(firstRecordedGameStateAt([{ ...q1, not_before: null }], "americanfootball_nfl")).toBeNull();
    expect(firstRecordedGameStateAt([{ ...q1, period: "2nd Quarter" }], "americanfootball_nfl")).toBeNull();
    expect(firstRecordedGameStateAt(undefined, "americanfootball_nfl")).toBeNull();
  });
});
