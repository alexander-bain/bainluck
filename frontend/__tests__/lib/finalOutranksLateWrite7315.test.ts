/**
 * #7315 — AFTER FULL TIME THERE IS NO NEWER INFORMATION, ONLY LATER WRITES.
 *
 * WHAT A READER GOT. Production, 2026-09-19, photographed at 390px AFTER
 * #7147's data repair had already corrected both event rows:
 *
 *   /events/15313231   printed  5 – 5 · FINAL · TIED     event row + ESPN: 5 – 6
 *   /events/15313146   printed  7 – 2                    event row + ESPN: 7 – 3
 *
 * An MLB regular-season game cannot end level, so the first one is visibly
 * impossible — the page printed a scoreline the sport does not have.
 *
 * ═══ THE MECHANISM IS A RANKING THAT IS RIGHT UNTIL THE WHISTLE ═══
 *
 * `page.tsx` resolves the hero score through `computeLastChartPoint`, and the
 * event row is the FALLBACK BENEATH two observation series, not an arbiter
 * above them. #5521 made the choice between those two series clock-based, which
 * is correct while a game is being played and has no notion of the game being
 * over. Measured on the specimen (`events` + `score_snapshots`, production):
 *
 *   completed_at              2026-09-16 20:34:09Z
 *   espn_history[-1]          2026-09-16 20:34Z    5 – 6   period "Final"
 *   score_history[-1]         2026-09-19 00:15:22Z 5 – 5   ← 51.7 h LATER
 *   the event row                                  5 – 6
 *
 * Newest clock wins, so a write two and a half days after the game ended beat a
 * point explicitly labelled `Final`.
 *
 * ═══ WHY THE RULE IS `completed_at` AND NOT THE WORD "FINAL" ═══
 *
 * The obvious fix reads the history point's own `period` and lets a terminal
 * label win regardless of clock. Measured, that rule is a dud:
 * `espn_snapshots.period` holds ZERO rows matching `final`/`full`/`ft` over 30
 * days — every terminal spelling that reaches a reader arrives through
 * `routes/events.py`'s MLB/`stat_model` supplement (`game_state.period`). It
 * would fire for the feeders that happen to write that English word and
 * silently never fire anywhere else, which is the worst shape a guard can have.
 * `completed_at` is one column with one meaning, it is already in this payload,
 * and it is null while a game is live — precisely when this rule must not
 * exist.
 *
 * ═══ THE GRACE IS A MEASURED GAP, NOT A ROUND NUMBER ═══
 *
 * Every event completed in the five days to 2026-09-19, counting
 * `score_snapshots` rows stamped after their own event's `completed_at`:
 *
 *   54 events   ≤ 21 minutes after   (50 of them sub-second)  ← honest tail
 *    2 events   51.7 h and 68.4 h    (15313231, 15313146)     ← this defect
 *
 * Nothing at all in between. Six hours has ~17× clearance over the honest tail
 * and ~8× under the nearest defect, so rows 3–6 below are the boundary and they
 * are the load-bearing ones: a fix that shaves the grace down to "just after the
 * game" starts adjudicating the ordinary case, which is not what this is for.
 *
 * ═══ ONLY ONE OF THE ISSUE'S TWO SPECIMENS IS THIS DEFECT — MEASURED ═══
 *
 * Run over the SERVED payloads (`artifacts/ux-1371/`, fetched 2026-09-20 01:0xZ):
 *
 *   15313231  hero 5 – 5 → **5 – 6**, axis 2026-09-19 → **2026-09-16 20:34Z**
 *   15313146  hero 7 – 2 → 7 – 2, unchanged, AND THAT IS CORRECT HERE
 *
 * On 15313146 the disagreement is not between the two observation series: the
 * `events` row itself reads **7 – 2** right now, re-poisoned at 2026-09-19
 * 23:15:07Z — four days after the game and two days after #7147's repair set it
 * to 7 – 3. The issue's table was taken before that write. A ranking rule has
 * nothing to arbitrate when the source of truth is the thing that is wrong, so
 * that specimen belongs to the data half (#7314 / #7147) and is reported there
 * rather than absorbed here. Row 2 below pins why.
 *
 * And it is still being written: 15313146 took its THIRD poisoned snapshot
 * while this was being built. Deleting today's rows cannot hold; a render rule
 * that refuses them can.
 *
 * RED-FIRST, measured on the parent `d0667c741` (this file against the parent's
 * `lib/eventKeyStats.ts`): **7 failed, 6 passed of 13**. Reds: rows 1, 2, 7, 8,
 * 11, 12, 13 — row 8 is a WEAK red and evidence of nothing but its own
 * arithmetic, because `POST_FULL_TIME_WRITE_GRACE_MS` does not exist on the
 * parent and the row errors rather than disagreeing. Greens: rows 3, 4, 5, 6, 9
 * and 10 — the prohibitions, which survive this fix being reverted and are here
 * to say what it may not touch.
 */

import {
  POST_FULL_TIME_WRITE_GRACE_MS,
  computeLastChartPoint,
  computeSharedChartDomain,
  scoreSnapshotOutranksHistory,
} from "@/lib/eventKeyStats";
import type { EventHistoryResponse } from "@/lib/types";

/** /events/15313231, to the millisecond, off `events` and `score_snapshots`. */
const COMMENCE = "2026-09-16T17:15:00+00:00";
const COMPLETED_AT = "2026-09-16T20:34:09.067524+00:00";
const FINAL_AT = "2026-09-16T20:34:00+00:00";
const LATE_WRITE_AT = "2026-09-19T00:15:22.408164+00:00";

function history(
  partial: Partial<EventHistoryResponse>,
): EventHistoryResponse {
  return {
    event_id: 15313231,
    home_team: "Chicago White Sox",
    away_team: "Cleveland Guardians",
    history: [],
    ...partial,
  } as EventHistoryResponse;
}

/** `espn_history` rows are ESPN-SHAPED, not necessarily ESPN — see #4571. */
function espnRow(
  at: string,
  home: number | null,
  away: number | null,
  period = "Final",
) {
  return {
    timestamp: at,
    home_probability: 0.5,
    away_probability: 0.5,
    home_score: home,
    away_score: away,
    game_clock: null,
    period,
  };
}

/** A sportsbook point — the series the `end` ladder falls through to. */
function bettingRow(at: string) {
  return {
    timestamp: at,
    home_probability: 0.5,
    away_probability: 0.5,
    over_under: null,
    projected_home_score: null,
    projected_away_score: null,
    bookmaker: "aggregate",
  };
}

const plus = (at: string, ms: number) =>
  new Date(Date.parse(at) + ms).toISOString();

describe("#7315 a write after full time cannot outrank the last reading", () => {
  it("1. the production specimen: the 51.7h-late 5–5 loses to the 5–6 the game ended on", () => {
    const point = computeLastChartPoint(
      history({
        completed_at: COMPLETED_AT,
        espn_history: [espnRow(FINAL_AT, 5, 6)],
        score_history: [
          { timestamp: "2026-09-16T19:40:00+00:00", home_score: 4, away_score: 5 },
          { timestamp: LATE_WRITE_AT, home_score: 5, away_score: 5 },
        ],
      }),
      5,
      6,
    );

    // The number a reader sees — and an MLB game that cannot have ended level.
    expect(point?.homeScore).toBe(5);
    expect(point?.awayScore).toBe(6);
    // Dated by the arm that actually supplied it (#4571's rule, unbroken).
    expect(point?.scoreStamp).toBe(FINAL_AT);
    expect(point?.scoreFrom).toBe("history");
  });

  it("2. the terminal point IS the event row, so the hero stops disagreeing with it", () => {
    // `routes/events.py:23768` appends a synthetic `period: "Final"` row to
    // `espn_history` on a settled event carrying `event.home_score` /
    // `event.away_score` verbatim. That is what the 20:34:00 row in the served
    // payload is — so on every settled event the history arm's last row is the
    // event row wearing a history row's shape, and what this rule restores is
    // the hero agreeing with the row #7315 says it must agree with.
    const point = computeLastChartPoint(
      history({
        completed_at: COMPLETED_AT,
        espn_history: [
          espnRow("2026-09-16T20:24:58.404904+00:00", 4, 6, "Bottom 10th"),
          espnRow(FINAL_AT, 5, 6),
        ],
        score_history: [
          { timestamp: "2026-09-16T20:31:58.356211+00:00", home_score: 5, away_score: 6 },
          { timestamp: LATE_WRITE_AT, home_score: 5, away_score: 5 },
        ],
      }),
      5,
      6,
    );

    expect(point?.homeScore).toBe(5);
    expect(point?.awayScore).toBe(6);
    expect(point?.scoreStamp).toBe(FINAL_AT);
  });

  // ── THE BOUNDARY. Green on the parent as well, and that is the point ──

  it("3. 🔴 the honest trailing write — 21 minutes after full time — still speaks", () => {
    // The whole measured population of legitimate post-completion rows sits at
    // or under 21 minutes. If this row goes red the fix has eaten the ordinary
    // case, where a score genuinely lands as the game is being marked final.
    const trailing = plus(COMPLETED_AT, 21 * 60 * 1000);
    const point = computeLastChartPoint(
      history({
        completed_at: COMPLETED_AT,
        espn_history: [espnRow("2026-09-16T20:20:00+00:00", 5, 5)],
        score_history: [{ timestamp: trailing, home_score: 5, away_score: 6 }],
      }),
      5,
      6,
    );

    expect(point?.homeScore).toBe(5);
    expect(point?.awayScore).toBe(6);
    expect(point?.scoreStamp).toBe(trailing);
  });

  it("4. 🔴 a live game has no completed_at, so #5521 is untouched to the byte", () => {
    // The #5521 specimen itself (15304937, status=live): ESPN 4–5 at 04:50:54Z,
    // a StatPal snapshot 4m30s newer saying 6–5. The snapshot must still win.
    const point = computeLastChartPoint(
      history({
        espn_history: [espnRow("2026-09-12T04:50:54.504661+00:00", 4, 5, "Bottom 10th")],
        score_history: [
          { timestamp: "2026-09-12T04:55:24.604834+00:00", home_score: 6, away_score: 5 },
        ],
      }),
      6,
      5,
    );

    expect(point?.homeScore).toBe(6);
    expect(point?.awayScore).toBe(5);
  });

  it("5. 🔴 an unparseable completed_at is not a licence to re-rank", () => {
    const point = computeLastChartPoint(
      history({
        completed_at: "not a date",
        espn_history: [espnRow(FINAL_AT, 5, 6)],
        score_history: [{ timestamp: LATE_WRITE_AT, home_score: 5, away_score: 5 }],
      }),
      5,
      6,
    );

    // "we cannot say when this game finished" is not "this game is over", and
    // only the second may move a number a reader is looking at.
    expect(point?.homeScore).toBe(5);
    expect(point?.awayScore).toBe(5);
  });

  it("6. 🔴 the event row is still the fallback, never a competitor", () => {
    // #5521's measured prohibition: with no ESPN arm the event row wins even
    // though a snapshot is present and late. Dropping the snapshot's OVERRIDE
    // must not promote it into a fill-in.
    const point = computeLastChartPoint(
      history({
        completed_at: COMPLETED_AT,
        score_history: [{ timestamp: LATE_WRITE_AT, home_score: 5, away_score: 5 }],
      }),
      5,
      6,
    );

    expect(point?.homeScore).toBe(5);
    expect(point?.awayScore).toBe(6);
    expect(point?.scoreFrom).toBe("event");
  });
});

describe("#7315 scoreSnapshotOutranksHistory takes full time as an argument", () => {
  it("7. refuses a snapshot stamped past the grace, however new it is", () => {
    expect(
      scoreSnapshotOutranksHistory(LATE_WRITE_AT, FINAL_AT, COMPLETED_AT),
    ).toBe(false);
  });

  it("8. the boundary holds in BOTH directions", () => {
    // gotcha #43: a one-sided boundary test passes for a mutant that moves the
    // threshold, so assert the last millisecond that is allowed AND the first
    // that is not.
    const atGrace = plus(COMPLETED_AT, POST_FULL_TIME_WRITE_GRACE_MS);
    const pastGrace = plus(COMPLETED_AT, POST_FULL_TIME_WRITE_GRACE_MS + 1);

    expect(scoreSnapshotOutranksHistory(atGrace, FINAL_AT, COMPLETED_AT)).toBe(true);
    expect(scoreSnapshotOutranksHistory(pastGrace, FINAL_AT, COMPLETED_AT)).toBe(false);
  });

  it("9. 🔴 without the third argument it is #5521's helper, unchanged", () => {
    expect(scoreSnapshotOutranksHistory(LATE_WRITE_AT, FINAL_AT)).toBe(true);
    expect(scoreSnapshotOutranksHistory(LATE_WRITE_AT, FINAL_AT, null)).toBe(true);
    expect(scoreSnapshotOutranksHistory(LATE_WRITE_AT, FINAL_AT, "")).toBe(true);
    expect(scoreSnapshotOutranksHistory(LATE_WRITE_AT, FINAL_AT, "not a date")).toBe(true);
  });

  it("10. 🔴 full time does not promote an OLDER snapshot", () => {
    // The grace decides whether the snapshot may argue, not who wins the
    // argument. A snapshot older than the history arm loses either way.
    expect(
      scoreSnapshotOutranksHistory("2026-09-16T19:00:00+00:00", FINAL_AT, COMPLETED_AT),
    ).toBe(false);
  });
});

describe("#7315 the chart domain ends at the game, not at the last write", () => {
  const LAST_REAL_POINT = "2026-09-16T20:30:00+00:00";

  const settled = (partial: Partial<EventHistoryResponse>) =>
    computeSharedChartDomain(
      history({ completed_at: COMPLETED_AT, ...partial }),
      "all",
      "completed",
      COMMENCE,
      "baseball_mlb",
    );

  it("11. a score row written 51.7h after full time does not stretch the axis", () => {
    const domain = settled({
      espn_history: [
        espnRow("2026-09-16T17:20:00+00:00", 0, 0, "Top 1st"),
        espnRow(LAST_REAL_POINT, 5, 6),
      ],
      score_history: [
        { timestamp: LAST_REAL_POINT, home_score: 5, away_score: 6 },
        { timestamp: LATE_WRITE_AT, home_score: 5, away_score: 5 },
      ],
    });

    // Three days of empty axis past the whistle is the 2026-09-14 chart-duration
    // ruling as well as an unreadable chart.
    expect(domain?.end).toBe("2026-09-16T20:30:00.000Z");
  });

  it("12. the ceiling is the floor's twin and applies to every game-end series", () => {
    // #6349 put `score_history` in this ladder beside ESPN and the win-prob
    // game-end sources. A ceiling only one of the three obeyed would just wait
    // for the next series to be poisoned.
    const domain = settled({
      espn_history: [
        espnRow("2026-09-16T17:20:00+00:00", 0, 0, "Top 1st"),
        espnRow(LAST_REAL_POINT, 5, 6),
      ],
      win_prob_history: {
        espn: [
          { timestamp: LAST_REAL_POINT, home_probability: 0.5, away_probability: 0.5 },
          { timestamp: LATE_WRITE_AT, home_probability: 0.5, away_probability: 0.5 },
        ],
      },
    });

    expect(domain?.end).toBe("2026-09-16T20:30:00.000Z");
  });

  it("13. when the ceiling would empty the ladder, the window still renders", () => {
    // Same remedy as the floor above it: a visible journey beats a precisely
    // trimmed empty one. If every game-end row is late — a mis-stamped
    // `completed_at`, a game that resumed — we fall through to the betting tail
    // rather than inverting the window and drawing nothing (#6349).
    const domain = settled({
      history: [
        bettingRow("2026-09-16T17:20:00+00:00"),
        bettingRow("2026-09-16T20:31:00+00:00"),
      ],
      score_history: [
        { timestamp: LATE_WRITE_AT, home_score: 5, away_score: 5 },
      ],
    });

    expect(domain).not.toBeNull();
    expect(Date.parse(domain!.end)).toBeGreaterThan(Date.parse(domain!.start));
    expect(domain?.end).toBe("2026-09-16T20:31:00.000Z");
  });
});
