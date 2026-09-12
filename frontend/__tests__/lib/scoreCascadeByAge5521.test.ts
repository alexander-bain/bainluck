/**
 * #5521 — THE SCORE CASCADE RANKS BY AGE, NOT BY ARM.
 *
 * WHAT A READER GOT. Production `/events/15304937` (Athletics v Seattle
 * Mariners, MLB, `status=live`), 2026-09-12 06:02:55Z and still there at
 * 06:33Z: a hero reading **Athletics 4 — Mariners 5** on a game whose real
 * score was **6 – 5 to the Athletics**. The wrong team, shown ahead, for over
 * an hour, on a page also printing `LIVE` and a refresh countdown.
 *
 * The same `/history` response carried the right answer:
 *
 *   espn_history[-1]   04:50:54.504661Z   4 – 5
 *   score_history[-1]  04:55:24.604834Z   6 – 5   ← 4m30s newer
 *   the event row                          6 – 5
 *
 * ═══ TWO DEFECTS THAT COMPOUND, AND ONLY ONE OF THEM IS THE OBVIOUS ONE ═══
 *
 * `score_history` was never read by this cascade at all — not ranked low, not
 * consulted. And the choice between the arms it DID read was made by arm, never
 * by age: `page.tsx` stated the premise out loud (*"prefer latest ESPN history
 * (more frequent updates) over event SWR"*), an empirical claim about relative
 * freshness with nothing re-checking it at runtime.
 *
 * The findable part is that `computeRealStartTime`, forty lines up in the same
 * file, documents ITS priority as *"StatPal score_history > ESPN >
 * win_prob_history"*. Two helpers in one file ordered the same arms differently,
 * and the reader got the loser. **When a helper resolves one value from several
 * arms, ask whether it ranks by SOURCE or by RECENCY — and whether a sibling in
 * the same file answers differently.**
 *
 * ═══ WHY A SINGLE-ARM FIXTURE CANNOT SEE THIS ═══
 *
 * Every existing fixture for `computeLastChartPoint` supplies `espn_history`
 * OR an event row, never `espn_history` AND a disagreeing `score_history`. The
 * bug lives entirely in the ordering between two present arms, so a suite built
 * one arm at a time is green on the defect by construction. Rows 1 and 2 below
 * are the same payload with the two clocks swapped: the fix must follow the
 * clock in BOTH directions (gotcha #43), and a mutant that hard-codes either arm
 * fails one of them.
 *
 * ═══ THE PROHIBITION ROWS ARE THE LOAD-BEARING ONES ═══
 *
 * Rows 2, 5, 7, 8 and 9 are green on the parent as well as on the fix. That is
 * the point: they are the boundary, and the boundary is measured. Making
 * `score_history` a third FALLBACK (so it speaks wherever ESPN is silent)
 * touches 134 events in a 72-hour production window; on 132 the last snapshot
 * equals the event row, and on the 2 where it does not it is a regression on a
 * US Open final score — 15307525 (event row 3–0, last snapshot 2–0, captured 32
 * min before `completed_at`) and 15308966 (1–2 vs 1–1, 48 min). The snapshot
 * series stops before the last set; the event row is overwritten in place. So
 * the snapshot arm may ARGUE with the other series and may never REPLACE the
 * event row.
 *
 * RED-FIRST, measured on the parent `137bf299` rather than reasoned:
 * **7 failed, 5 passed of 12**. Reds: rows 1, 3, 4, 6 and all three
 * `scoreSnapshotOutranksHistory` rows (the helper does not exist on the parent,
 * so those three are a weak red and are not counted as evidence of anything but
 * their own arithmetic). Greens: rows 2, 5, 7, 8, 9.
 *
 * 🔴 Row 6 is deliberately NOT a pure prohibition and is red on the parent — it
 * asserts BOTH halves of the boundary in one payload (the side ESPN spoke for
 * moves to the newer snapshot; the side it did not falls to the event row), so
 * a mutant that fixes one half and breaks the other cannot pass it. Rows 5 and
 * 7–9 are the pure prohibitions, and they are the ones that survive the fix
 * being reverted.
 */

import {
  computeLastChartPoint,
  scoreSnapshotOutranksHistory,
} from "@/lib/eventKeyStats";
import type { EventHistoryResponse } from "@/lib/types";

/** The production specimen's clocks, to the millisecond. */
const ESPN_AT = "2026-09-12T04:50:54.504661+00:00";
const SNAP_AT = "2026-09-12T04:55:24.604834+00:00";

function history(
  partial: Partial<EventHistoryResponse>,
): EventHistoryResponse {
  return {
    event_id: 15304937,
    home_team: "Athletics",
    away_team: "Seattle Mariners",
    history: [],
    ...partial,
  } as EventHistoryResponse;
}

/** `espn_history` rows are ESPN-SHAPED, not necessarily ESPN — see #4571. */
function espnRow(at: string, home: number | null, away: number | null) {
  return {
    timestamp: at,
    home_probability: 0.45,
    away_probability: 0.55,
    home_score: home,
    away_score: away,
    game_clock: null,
    period: "Bottom 10th",
  };
}

describe("#5521 the score cascade follows the clock, not the arm", () => {
  it("1. the production specimen: a newer score_history pair beats an older ESPN pair", () => {
    const point = computeLastChartPoint(
      history({
        espn_history: [espnRow(ESPN_AT, 4, 5)],
        score_history: [{ timestamp: SNAP_AT, home_score: 6, away_score: 5 }],
      }),
      6,
      5,
    );

    // The number a reader sees.
    expect(point?.homeScore).toBe(6);
    expect(point?.awayScore).toBe(5);
    // And it is dated by the arm that supplied it (#4571's rule, unbroken).
    expect(point?.scoreStamp).toBe(SNAP_AT);
    expect(point?.scoreFrom).toBe("history");
  });

  it("2. the same payload with the clocks swapped: the ESPN pair wins", () => {
    const point = computeLastChartPoint(
      history({
        espn_history: [espnRow(SNAP_AT, 4, 5)],
        score_history: [{ timestamp: ESPN_AT, home_score: 6, away_score: 5 }],
      }),
      6,
      5,
    );

    expect(point?.homeScore).toBe(4);
    expect(point?.awayScore).toBe(5);
    expect(point?.scoreStamp).toBe(SNAP_AT);
  });

  it("3. it reads the LAST snapshot, not the first", () => {
    const point = computeLastChartPoint(
      history({
        espn_history: [espnRow(ESPN_AT, 4, 5)],
        score_history: [
          { timestamp: "2026-09-12T03:00:00+00:00", home_score: 1, away_score: 0 },
          { timestamp: SNAP_AT, home_score: 6, away_score: 5 },
        ],
      }),
      6,
      5,
    );

    expect(point?.homeScore).toBe(6);
  });

  it("4. a snapshot newer than ESPN wins even when the event row disagrees with both", () => {
    // The event row is the FALLBACK, not a competitor: it is only consulted for
    // a side no observation series spoke for.
    const point = computeLastChartPoint(
      history({
        espn_history: [espnRow(ESPN_AT, 4, 5)],
        score_history: [{ timestamp: SNAP_AT, home_score: 6, away_score: 5 }],
      }),
      99,
      99,
    );

    expect(point?.homeScore).toBe(6);
    expect(point?.awayScore).toBe(5);
  });

  // ── PROHIBITIONS: green on the parent too, and that is why they are here ──

  it("5. 🔴 with no ESPN arm the EVENT ROW still wins — the snapshot may not fill in", () => {
    // 15307525 Zverev v van de Zandschulp, US Open, completed: the snapshot
    // series stopped at 2–0 thirty-two minutes before `completed_at` while the
    // event row carried the final 3–0. 134 events in the 72h window sit in this
    // shape; letting the snapshot speak here regresses the two that matter.
    const point = computeLastChartPoint(
      history({
        score_history: [
          { timestamp: "2026-09-10T01:49:41.981862+00:00", home_score: 2, away_score: 0 },
        ],
      }),
      3,
      0,
    );

    expect(point?.homeScore).toBe(3);
    expect(point?.awayScore).toBe(0);
    expect(point?.scoreFrom).toBe("event");
  });

  it("6. 🔴 a side ESPN left null falls through to the event row, snapshot or not", () => {
    const point = computeLastChartPoint(
      history({
        espn_history: [espnRow(ESPN_AT, 4, null)],
        score_history: [{ timestamp: SNAP_AT, home_score: 6, away_score: 5 }],
      }),
      6,
      7,
    );

    expect(point?.homeScore).toBe(6); // ESPN spoke; the newer snapshot replaced it
    expect(point?.awayScore).toBe(7); // ESPN did not; the event row answers
    expect(point?.scoreFrom).toBe("mixed");
  });

  it("7. 🔴 equal clocks keep the incumbent arm", () => {
    const point = computeLastChartPoint(
      history({
        espn_history: [espnRow(ESPN_AT, 4, 5)],
        score_history: [{ timestamp: ESPN_AT, home_score: 6, away_score: 5 }],
      }),
      6,
      5,
    );

    expect(point?.homeScore).toBe(4);
  });

  it("8. 🔴 an undatable snapshot cannot move the number", () => {
    const point = computeLastChartPoint(
      history({
        espn_history: [espnRow(ESPN_AT, 4, 5)],
        score_history: [
          { timestamp: "not a date", home_score: 6, away_score: 5 },
        ],
      }),
      6,
      5,
    );

    expect(point?.homeScore).toBe(4);
    expect(point?.scoreStamp).toBe(ESPN_AT);
  });

  it("9. 🔴 no score_history at all is the untouched path", () => {
    const point = computeLastChartPoint(
      history({ espn_history: [espnRow(ESPN_AT, 4, 5)] }),
      6,
      5,
    );

    expect(point?.homeScore).toBe(4);
    expect(point?.scoreStamp).toBe(ESPN_AT);
    expect(point?.scoreFrom).toBe("history");
  });
});

describe("#5521 scoreSnapshotOutranksHistory", () => {
  it("is true only when the snapshot is strictly newer", () => {
    expect(scoreSnapshotOutranksHistory(SNAP_AT, ESPN_AT)).toBe(true);
    expect(scoreSnapshotOutranksHistory(ESPN_AT, SNAP_AT)).toBe(false);
    expect(scoreSnapshotOutranksHistory(ESPN_AT, ESPN_AT)).toBe(false);
  });

  it("refuses to rank what it cannot parse — on either side", () => {
    // "we cannot say which is newer" is not "the snapshot is newer", and only
    // the second may move a number a reader is looking at.
    expect(scoreSnapshotOutranksHistory(null, ESPN_AT)).toBe(false);
    expect(scoreSnapshotOutranksHistory(SNAP_AT, null)).toBe(false);
    expect(scoreSnapshotOutranksHistory(undefined, undefined)).toBe(false);
    expect(scoreSnapshotOutranksHistory("not a date", ESPN_AT)).toBe(false);
    expect(scoreSnapshotOutranksHistory(SNAP_AT, "not a date")).toBe(false);
    expect(scoreSnapshotOutranksHistory("", "")).toBe(false);
  });

  it("compares instants, not strings — a Z stamp and a +00:00 stamp are one clock", () => {
    // Lexical comparison is the mutant here: "2026-09-12T04:55:24.604834Z" sorts
    // BELOW "2026-09-12T04:55:24.604834+00:00" as text while naming the same
    // millisecond, and the two spellings do both reach this helper (`/history`
    // serves `+00:00`; a pushed frame can carry `Z`).
    expect(
      scoreSnapshotOutranksHistory(
        "2026-09-12T04:55:24.604834Z",
        "2026-09-12T04:55:24.604834+00:00",
      ),
    ).toBe(false);
    expect(
      scoreSnapshotOutranksHistory(
        "2026-09-12T04:55:25.000000Z",
        "2026-09-12T04:55:24.604834+00:00",
      ),
    ).toBe(true);
  });
});
