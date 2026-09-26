// #8967 — THE RESTING READOUT'S PLAY IS THE ONE THAT MADE THE SCORE IT SITS BESIDE.
//
// `/events/15313791` (Iowa 20 @ Michigan 19, Final), 390px, 2026-09-26 23:07Z,
// fresh load: Iowa won on the last play. The readout under the chart, with no
// finger on it, read
//
//   Final · 19 – 20 · Passing Touchdown · 4:04 PM
//   B. Underwood pass to JJ Buchanan for 49 yds, for a TD (Two-Point Conversion failed)
//
// That is Michigan's 11:59 touchdown (3:22 PM), which made it 19–14. The page
// credited it with the final score, which means it credited Michigan's touchdown
// with Iowa's win. `scoring_plays` (box score) still ended at that play; the score
// cascade already read 19–20.
//
// ## Fixture
//
// `event-15313791-history-8967-final.json` — PRODUCTION BYTES, unedited:
// `GET /api/events/15313791/history`, 2026-09-26 ~23:07Z, `status: completed`.
// Its last scoring play is the Michigan TD (home 19, away 14); its last
// `espn_history` row is 19–20. The control arm truncates the same payload at
// 22:30Z (after that TD, before Iowa's winner), where the play IS the score's play.
//
// The real path is exercised: `computeLastChartPoint` → the real `GamePlayCard`
// as `lastPoint`, the prop the event page passes when nobody holds the chart.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import GamePlayCard from "@/components/GamePlayCard";
import { computeLastChartPoint } from "@/lib/eventKeyStats";
import type { EventHistoryResponse } from "@/lib/types";

import FINAL from "../fixtures/event-15313791-history-8967-final.json";

const specimen = FINAL as unknown as EventHistoryResponse;
const MICHIGAN_TD = "B. Underwood pass to JJ Buchanan for 49 yds, for a TD";

/** The same payload as it stood at `cutoff`: every timestamped series truncated. */
function asOf(cutoff: string): EventHistoryResponse {
  const keep = <T extends { timestamp?: string | null }>(rows: T[] | undefined | null) =>
    (rows ?? []).filter((r) => !r.timestamp || r.timestamp <= cutoff);
  const wp = (specimen.win_prob_history ?? {}) as Record<string, { timestamp?: string }[]>;
  return {
    ...specimen,
    status: "live",
    completed_at: null,
    history: keep(specimen.history),
    espn_history: keep(specimen.espn_history),
    score_history: keep(specimen.score_history as never),
    aggregate_line: keep(specimen.aggregate_line as never),
    scoring_plays: keep(specimen.scoring_plays),
    win_prob_history: Object.fromEntries(Object.entries(wp).map(([k, v]) => [k, keep(v)])),
  } as unknown as EventHistoryResponse;
}

function resting(history: EventHistoryResponse, home: number, away: number): string {
  return renderToStaticMarkup(
    <GamePlayCard
      homeTeam="Michigan Wolverines"
      awayTeam="Iowa Hawkeyes"
      sportKey="americanfootball_ncaaf"
      activePoint={null}
      lastPoint={computeLastChartPoint(history, home, away)}
    />,
  );
}

describe("#8967 the resting play must be the play that produced the score beside it", () => {
  test("the fixture holds the defect: latest play is 19–14, the score is 19–20", () => {
    const plays = specimen.scoring_plays!;
    const latest = [...plays].sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1)).at(-1)!;
    expect(latest.description).toContain(MICHIGAN_TD);
    expect([latest.home_score, latest.away_score]).toEqual([19, 14]);
    const p = computeLastChartPoint(specimen, 19, 20)!;
    expect([p.homeScore, p.awayScore]).toEqual([19, 20]);
  });

  test("specimen: the final row carries no play, so it names no winner it cannot vouch for", () => {
    expect(computeLastChartPoint(specimen, 19, 20)!.scoringPlay ?? null).toBeNull();
    const html = resting(specimen, 19, 20);
    expect(html).not.toContain(MICHIGAN_TD);
    expect(html).not.toContain("Passing Touchdown");
    expect(html).not.toContain('data-testid="game-play-card-description"');
  });

  test("control: at 22:30Z the same play IS the score's play, and it still shows", () => {
    const earlier = asOf("2026-09-26T22:30:00Z");
    const p = computeLastChartPoint(earlier, 19, 14)!;
    expect([p.homeScore, p.awayScore]).toEqual([19, 14]);
    expect(p.scoringPlay?.description).toContain(MICHIGAN_TD);
    const html = resting(earlier, 19, 14);
    expect(html).toContain(MICHIGAN_TD);
    expect(html).toContain("Passing Touchdown");
  });

  test("a play that carries no score is no evidence either way — unchanged", () => {
    const unscored = {
      ...specimen,
      scoring_plays: specimen.scoring_plays!.map((play) => ({
        ...play,
        home_score: null,
        away_score: null,
      })),
    } as EventHistoryResponse;
    expect(computeLastChartPoint(unscored, 19, 20)!.scoringPlay?.description).toContain(
      MICHIGAN_TD,
    );
  });
});
