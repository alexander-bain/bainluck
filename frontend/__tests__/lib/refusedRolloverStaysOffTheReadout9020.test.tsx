// #9020 / CERT-3657 — THE READOUT UNDER THE HERO NEVER SHOWS A REFUSED CLOCK.
//
// SMU (15316003) at the 3rd–4th quarter break: ESPN publishes a rollover
// reading, `'4:38 - 4th Quarter'`, two minutes after `'End of 3rd Quarter'`.
// The ESPN writer refuses it from the events row (the hero stays on End of 3rd
// Quarter 0:00). CERT-3657 found the same pass still appended it to
// `espn_history`, and `computeLastChartPoint` reads the newest snapshot that
// carries a clock — so the readout printed 4:38 Q4 under a hero at the end of
// the 3rd: two clocks on one page.
//
// The fixture is not hand-made: its `after` tail is pinned row for row to what
// one real `_process_live_sport` pass serves
// (backend/tests/test_refused_clock_stays_off_the_chart_9020.py), and `before`
// is the first cut's output. Both go through the real `computeLastChartPoint`
// and the real `GamePlayCard`, as the event page renders them at rest.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import GamePlayCard from "@/components/GamePlayCard";
import { computeLastChartPoint } from "@/lib/eventKeyStats";
import type { EventHistoryResponse } from "@/lib/types";

import fixture from "../fixtures/refusedRolloverHistory9020.json";

type Arm = "before" | "after";

function history(arm: Arm): EventHistoryResponse {
  const partial: Partial<EventHistoryResponse> = {
    event_id: 15316003,
    home_team: "SMU Mustangs",
    away_team: "Opponent",
    history: [],
    espn_history: fixture[arm].espn_history,
  };
  return partial as EventHistoryResponse;
}

function readout(arm: Arm) {
  return computeLastChartPoint(
    history(arm),
    fixture.row.home_score,
    fixture.row.away_score,
  )!;
}

function resting(arm: Arm): string {
  return renderToStaticMarkup(
    <GamePlayCard
      homeTeam="SMU Mustangs"
      awayTeam="Opponent"
      sportKey="americanfootball_ncaaf"
      activePoint={null}
      lastPoint={readout(arm)}
    />,
  );
}

describe("#9020 a refused rollover clock stays off the resting readout", () => {
  test("after the repair the readout holds the row's position, carried and dated", () => {
    const p = readout("after");
    expect(p.period).toBe(fixture.row.period);
    expect(p.clock).toBe(fixture.row.game_clock);
    expect(p.periodApprox).toBe(true);
    expect(p.periodObservedAt).toBe("2026-09-27T03:30:32+00:00");

    const html = resting("after");
    expect(html).not.toContain("4:38");
    expect(html).not.toContain("4th");
  });

  test("the refused reading's score still reaches the readout", () => {
    // (Its probability is not read from `espn_history` at all — the readout
    // takes the blend; the backend test pins that ESPN's number still lands.)
    const p = readout("after");
    expect(p.homeScore).toBe(21);
    expect(p.awayScore).toBe(10);
  });

  test("control: the first cut's history is what put the second clock on the page", () => {
    const p = readout("before");
    expect(p.period).toBe("4:38 - 4th Quarter");
    expect(p.clock).toBe("4:38");
    expect(p.period).not.toBe(fixture.row.period);
    expect(resting("before")).toContain("4:38");
  });
});
