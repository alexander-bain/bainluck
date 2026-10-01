/**
 * #8810 — a postponed match's chart stops drawing a "Start" that never happened.
 *
 * WHAT THE READER SAW (ux, production, 390px, 2026-09-27 08:35Z): `/events/15315470`,
 * Crawley Town v Barnet, League Two, postponed (ESPN `period='Postponed'`, row
 * `suspended`, 0-0 filler). The hero already read "Postponed" (#9025), but the
 * win-probability card opened on "Since Start", drew a vertical "Start" line at
 * 7:30 AM PDT — the SCHEDULED kick-off — and ran a flat line 17 hours to 1:35 AM.
 * Alex's 9/14 ruling: in-game charts are confined to the actual game; a match
 * nobody played has none, and a scheduled time is not automatically a start.
 *
 * The served history says `commence_time_is_kickoff: true` (fixture below), so the
 * server's #8215 flag cannot decline the cut on its own. The page already knows
 * the match was not played (`heroScoreIsStoppageFiller`, #8810/#8960) and now
 * hands both charts and the shared range the same `false` #8370 reads.
 *
 * Fixture: `GET /api/events/15315470/history`, production, 2026-09-27 08:37Z.
 */

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OddsChart from "@/components/OddsChart";
import { defaultChartTimeRange } from "@/lib/eventKeyStats";
import { scoresShowPlay } from "@/lib/eventState";
import { authorityStoppageLabel } from "@/lib/gameTimeLabel";
import type { EventHistoryResponse } from "@/lib/types";
const { AnalyticsProvider } = require("@/components/Analytics");

/** The served body carries `commence_time` and `status` beside the typed fields. */
const HISTORY: EventHistoryResponse & { commence_time: string; status: string } = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, "../fixtures/event-15315470-history-8810-postponed.json"),
    "utf8",
  ),
);
const COMMENCE = HISTORY.commence_time;

/** The page's own derivation, spelled from the same helpers it calls. */
const pageKickoffFlag = (period: string | null, away: number | null, home: number | null) => {
  const stoppageFiller = authorityStoppageLabel(period) !== null && !scoresShowPlay(away, home);
  return stoppageFiller ? false : HISTORY.commence_time_is_kickoff;
};

function draw(commenceTimeIsKickoff: boolean | undefined, externalTimeRange?: "all" | "live"): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      <OddsChart
        history={HISTORY.history ?? []}
        homeTeam="Crawley Town"
        awayTeam="Barnet"
        sportKey="soccer_england_league2"
        commenceTime={COMMENCE}
        commenceTimeIsKickoff={commenceTimeIsKickoff}
        eventStatus="suspended"
        winProbHistory={HISTORY.win_prob_history as never}
        winProbSources={HISTORY.win_prob_sources as never}
        aggregateLine={HISTORY.aggregate_line ?? undefined}
        externalTimeRange={externalTimeRange}
      />,
    ),
  );
}

const startMarker = (html: string): string => {
  const m = html.match(/data-start-marker="([^"]*)"/);
  if (!m) throw new Error("the wrapper lost its data-start-marker attribute");
  return m[1];
};
const offersSinceStart = (html: string) => />Since Start</.test(html);

describe("#8810 — the specimen, as served", () => {
  it("the server calls the scheduled hour a kick-off, and the series runs past it", () => {
    expect(HISTORY.status).toBe("suspended");
    expect(HISTORY.commence_time_is_kickoff).toBe(true);
    // Without the page's answer, the shared range opens on "Since Start" — the defect.
    expect(defaultChartTimeRange(HISTORY, COMMENCE)).toBe("live");
  });

  it("CONTROL — without the page's `false` the chart draws the phantom Start", () => {
    expect(startMarker(draw(HISTORY.commence_time_is_kickoff, "all"))).not.toBe("");
    expect(offersSinceStart(draw(HISTORY.commence_time_is_kickoff))).toBe(true);
  });
});

describe("#8810 — a match nobody played has no Start", () => {
  const flag = pageKickoffFlag("Postponed", 0, 0);

  it("Postponed with ESPN's 0-0 filler ⇒ the page answers `false`", () => {
    expect(flag).toBe(false);
  });

  it("no 'Start' marker, no 'Since Start' pill", () => {
    expect(startMarker(draw(flag, "all"))).toBe("");
    expect(offersSinceStart(draw(flag, "all"))).toBe(false);
  });

  it("CONTROL — a stopped match WITH a score, or no stoppage word, keeps the served flag", () => {
    expect(pageKickoffFlag("Postponed", 1, 0)).toBe(true);
    expect(pageKickoffFlag(null, 0, 0)).toBe(true);
    expect(pageKickoffFlag("2nd Half", 0, 0)).toBe(true);
  });
});

describe("#8810 — the event page wires it", () => {
  const src = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");

  it("derives the flag from the stoppage filler, passing the served value through otherwise", () => {
    expect(src).toMatch(
      // #6158 adds one `||` arm (a game the authority still reads pregame); the
      // stoppage filler stays the first operand.
      /const commenceTimeIsKickoff = heroScoreIsStoppageFiller(?:\s*\|\|\s*authorityHasNotStarted)?\s*\?\s*false\s*:\s*historyData\?\.commence_time_is_kickoff;/,
    );
  });

  it("the shared range opens on 'All' when it is `false`", () => {
    expect(src).toMatch(
      /commenceTimeIsKickoff === false\s*\?\s*"all"\s*:\s*defaultChartTimeRange\(historyData, event\?\.commence_time\)/,
    );
  });

  it("both OddsChart instances read the page's flag, never the raw served one", () => {
    expect(src.match(/commenceTimeIsKickoff=\{commenceTimeIsKickoff\}/g)?.length).toBe(2);
    expect(src).not.toContain("commenceTimeIsKickoff={historyData?.commence_time_is_kickoff}");
  });
});
