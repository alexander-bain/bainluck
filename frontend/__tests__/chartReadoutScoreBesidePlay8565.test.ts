/**
 * #8565 — a touchdown on the chart must print the score it produced.
 *
 * Specimen: /events/15315984 (Liberty at Coastal Carolina, final 17–34), served
 * /history banked after #8501 went live. #8501 stamps each scoring play at the
 * first served sighting of its post-play score across `espn_history` AND
 * `score_history`. The readout took its score from ESPN rows (and the win-prob
 * `game_state` echo) only, and attached a play to the NEAREST point: the 17–34
 * touchdown, stamped 03:28:17 from `score_history`, sat on the 03:28 point
 * carrying 17–27 (ESPN was not captured between 03:27:17 and 03:31:17).
 *
 * This runs the chart's own sequence — `makeEnsurePoint` over the price
 * minutes, `stampObservedGameState`, `attachScoringPlays`, `fillMinuteGaps`,
 * `foldScoreObservations`, `carryGameStateForward` — on the banked rows, in the
 * order `OddsChart`'s data memo calls them.
 */

import fixture from "./fixtures/chartReadoutScoreHistory8565.json";
import { fillMinuteGaps, makeEnsurePoint } from "@/lib/chartTimeline";
import {
  attachScoringPlays,
  carryGameStateForward,
  foldScoreObservations,
  stampObservedGameState,
  type CarriedGameStateRow,
  type ScoreObservation,
} from "@/lib/chartGameState";

interface Play {
  timestamp: string;
  description: string;
  home_score: number | null;
  away_score: number | null;
}

interface Row extends CarriedGameStateRow {
  time: string;
  _scoringPlay?: Play | null;
}

interface Options {
  foldScoreHistory: boolean;
  attach: (points: Row[], plays: Play[]) => void;
}

/** The pre-#8565 rule, kept here only as the strawman the guard must catch. */
function attachNearest(points: Row[], plays: Play[]): void {
  for (const play of plays) {
    const t = Date.parse(play.timestamp);
    let best = 0;
    let bestDist = Infinity;
    points.forEach((p, i) => {
      const dist = Math.abs(Date.parse(p.timestamp) - t);
      if (dist < bestDist) {
        bestDist = dist;
        best = i;
      }
    });
    if (bestDist < 120000) points[best]._scoringPlay = play;
  }
}

function buildChart(opts: Options): Row[] {
  const dataMap = new Map<string, Row>();
  const ensurePoint = makeEnsurePoint<Row>(dataMap, () => ({}));
  for (const minute of fixture.price_minutes) ensurePoint(minute);

  stampObservedGameState(dataMap, fixture.espn_history, Object.values(fixture.win_prob_game_state));

  const dataPoints = Array.from(dataMap.values()).sort(
    (a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp),
  );
  opts.attach(dataPoints, fixture.scoring_plays as Play[]);

  fillMinuteGaps(
    new Date(fixture.time_domain.start),
    new Date(fixture.time_domain.end),
    ensurePoint,
  );

  const sorted = Array.from(dataMap.values()).sort(
    (a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp),
  );
  if (opts.foldScoreHistory) {
    foldScoreObservations(sorted, fixture.score_history as ScoreObservation[]);
  }
  carryGameStateForward(sorted);
  return sorted;
}

function playRows(rows: Row[]) {
  return rows
    .filter((r) => r._scoringPlay)
    .map((r) => ({
      point: r.timestamp,
      play: r._scoringPlay!.timestamp,
      shown: `${r._homeScore}-${r._awayScore}`,
      produced: `${r._scoringPlay!.home_score}-${r._scoringPlay!.away_score}`,
    }));
}

const FIXED: Options = {
  foldScoreHistory: true,
  attach: (points, plays) => attachScoringPlays(points, plays),
};

describe("#8565 — the score beside a scoring play is the score it produced (15315984)", () => {
  it("the fixture is the specimen: nine plays, the 17–34 TD stamped from score_history at 03:28:17", () => {
    expect(fixture.scoring_plays).toHaveLength(9);
    const last = fixture.scoring_plays[8];
    expect(last.timestamp).toBe("2026-09-25T03:28:17.016443+00:00");
    expect([last.home_score, last.away_score]).toEqual([17, 34]);
    // No ESPN row saw 17–34 before 03:31 — only score_history did.
    const espnFirst = fixture.espn_history.find((r) => r.home_score === 17 && r.away_score === 34);
    expect(espnFirst?.timestamp.startsWith("2026-09-25T03:31")).toBe(true);
  });

  it("every one of the nine plays lands on a point that shows its post-play score", () => {
    const rows = playRows(buildChart(FIXED));
    expect(rows).toHaveLength(9);
    for (const r of rows) expect(r.shown).toBe(r.produced);
  });

  it("the specimen touchdown sits on the 03:28 point, which reads 17–34 dated by the sighting", () => {
    const sorted = buildChart(FIXED);
    const pt = sorted.find((r) => r._scoringPlay?.timestamp === "2026-09-25T03:28:17.016443+00:00")!;
    expect(pt.timestamp).toBe("2026-09-25T03:28:00.000Z");
    expect([pt._homeScore, pt._awayScore]).toEqual([17, 34]);
    expect(pt._scoreObservedAt).toBe("2026-09-25T03:28:17.016443+00:00");
    expect(pt._scoreApprox).toBe(false);
  });

  // Strawmen: each half of the fix is load-bearing on the real rows.
  it("STRAWMAN — the pre-#8565 chart (no score_history, nearest point) prints 17–27 beside the 17–34 TD", () => {
    const rows = playRows(buildChart({ foldScoreHistory: false, attach: attachNearest }));
    const wrong = rows.filter((r) => r.shown !== r.produced);
    expect(wrong).toEqual([
      {
        point: "2026-09-25T03:28:00.000Z",
        play: "2026-09-25T03:28:17.016443+00:00",
        shown: "17-27",
        produced: "17-34",
      },
    ]);
  });

  it("STRAWMAN — at-or-after attachment alone does not fix it: score_history must join the carry", () => {
    const rows = playRows(
      buildChart({ foldScoreHistory: false, attach: (p, pl) => attachScoringPlays(p, pl) }),
    );
    expect(rows.some((r) => r.shown !== r.produced)).toBe(true);
  });
});

describe("#8565 — foldScoreObservations and attachScoringPlays, rule by rule", () => {
  const mk = (timestamp: string, extra: Partial<Row> = {}): Row => ({ timestamp, time: "", ...extra });

  it("inside one minute the LATER observation wins, whichever series it came from", () => {
    const pts = [
      mk("2026-01-01T00:05:00.000Z", {
        _homeScore: 17,
        _awayScore: 27,
        _scoreObservedAt: "2026-01-01T00:05:05.000Z",
      }),
    ];
    foldScoreObservations(pts, [{ timestamp: "2026-01-01T00:05:17.000Z", home_score: 17, away_score: 34 }]);
    expect([pts[0]._homeScore, pts[0]._awayScore]).toEqual([17, 34]);
    expect(pts[0]._scoreObservedAt).toBe("2026-01-01T00:05:17.000Z");

    // …and an older sighting never overwrites a newer ESPN row.
    const newer = [
      mk("2026-01-01T00:05:00.000Z", {
        _homeScore: 17,
        _awayScore: 34,
        _scoreObservedAt: "2026-01-01T00:05:40.000Z",
      }),
    ];
    foldScoreObservations(newer, [{ timestamp: "2026-01-01T00:05:17.000Z", home_score: 17, away_score: 27 }]);
    expect([newer[0]._homeScore, newer[0]._awayScore]).toEqual([17, 34]);
    expect(newer[0]._scoreObservedAt).toBe("2026-01-01T00:05:40.000Z");
  });

  it("an observation in a minute with no point is dropped, like an ESPN row", () => {
    const pts = [mk("2026-01-01T00:05:00.000Z")];
    foldScoreObservations(pts, [{ timestamp: "2026-01-01T00:06:10.000Z", home_score: 1, away_score: 0 }]);
    expect(pts[0]._homeScore).toBeUndefined();
  });

  it("a play attaches in its own minute bucket, even though the bucket starts before the stamp", () => {
    const pts = [mk("2026-01-01T00:04:00.000Z"), mk("2026-01-01T00:05:00.000Z"), mk("2026-01-01T00:06:00.000Z")];
    const play = { timestamp: "2026-01-01T00:05:40.000Z" }; // nearest is 00:06 (20s); its own bucket is 00:05
    attachScoringPlays(pts, [play]);
    expect(pts[1]._scoringPlay).toBe(play);
    expect(pts[2]._scoringPlay).toBeUndefined();
  });

  it("skips a nearer point in an earlier minute and takes the first at/after inside two minutes", () => {
    const pts = [mk("2026-01-01T00:04:00.000Z"), mk("2026-01-01T00:07:00.000Z")];
    const play = { timestamp: "2026-01-01T00:05:05.000Z" }; // 65s after 00:04 (nearest), 115s before 00:07
    attachScoringPlays(pts, [play]);
    expect(pts[1]._scoringPlay).toBe(play);
    expect(pts[0]._scoringPlay).toBeUndefined();
  });

  it("falls back to the nearest earlier point only when nothing at/after is inside the window", () => {
    const pts = [mk("2026-01-01T00:04:00.000Z"), mk("2026-01-01T00:08:00.000Z")];
    const play = { timestamp: "2026-01-01T00:05:10.000Z" };
    attachScoringPlays(pts, [play]);
    expect(pts[0]._scoringPlay).toBe(play);
    expect(pts[1]._scoringPlay).toBeUndefined();

    const none = [mk("2026-01-01T00:01:00.000Z"), mk("2026-01-01T00:09:00.000Z")];
    attachScoringPlays(none, [play]);
    expect(none.some((p) => p._scoringPlay)).toBe(false);
  });
});
