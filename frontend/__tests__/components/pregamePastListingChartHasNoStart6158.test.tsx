/**
 * #6158 — a game the authority still reads pregame past its listed hour draws no
 * "Start" line at that hour.
 *
 * WHAT THE READER SAW (ux, production, 390px, 2026-10-01 03:14Z): `/events/15322334`,
 * Costoulas v Lansere (WTA), listed 03:10Z, row still `scheduled`, served
 * `authority_not_started: true` (#9968). The hero read "Pregame" (#9980), and the
 * win-probability card beside it pinned a vertical "Start" line at 03:10Z, a start
 * that had not happened. Alex's 9/14 ruling: a scheduled time is not automatically an
 * actual start, and markers sit at evidenced times. live saw the same on 15320695.
 *
 * The served history says `commence_time_is_kickoff: true` (fixture), so the server's
 * #8215 flag cannot decline the line by itself. The page now hands both charts and the
 * shared range the same `false` #8810 uses for a match nobody played.
 *
 * Fixture: `GET /api/events/15322334/history`, production, 2026-10-01 03:16Z.
 */

import fs from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OddsChart from "@/components/OddsChart";
import type { EventHistoryResponse } from "@/lib/types";
const { AnalyticsProvider } = require("@/components/Analytics");

const HISTORY: EventHistoryResponse & { commence_time: string; status: string } = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, "../fixtures/event-15322334-history-6158-pregame-past-listing.json"),
    "utf8",
  ),
);
const COMMENCE = HISTORY.commence_time;

/** The page's own derivation (see the source-shape arm below). */
const pageKickoffFlag = (status: string, authorityNotStarted: boolean | undefined) => {
  const stoppageFiller = false;
  const authorityHasNotStarted = status === "scheduled" && authorityNotStarted === true;
  return stoppageFiller || authorityHasNotStarted ? false : HISTORY.commence_time_is_kickoff;
};

function draw(commenceTimeIsKickoff: boolean | undefined, externalTimeRange?: "all" | "live"): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      <OddsChart
        history={HISTORY.history ?? []}
        homeTeam="Costoulas"
        awayTeam="Lansere"
        sportKey="tennis_wta"
        commenceTime={COMMENCE}
        commenceTimeIsKickoff={commenceTimeIsKickoff}
        eventStatus="scheduled"
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

describe("#6158 — the specimen, as served", () => {
  it("scheduled, past its listed hour, and the server calls that hour a kick-off", () => {
    expect(HISTORY.status).toBe("scheduled");
    expect(HISTORY.commence_time_is_kickoff).toBe(true);
    const pts = Object.values(HISTORY.win_prob_history ?? {}).flat();
    expect(pts.some((p) => Date.parse(p.timestamp) > Date.parse(COMMENCE))).toBe(true);
  });

  it("CONTROL — with the served flag the chart draws the phantom Start", () => {
    expect(startMarker(draw(HISTORY.commence_time_is_kickoff, "all"))).not.toBe("");
    expect(offersSinceStart(draw(HISTORY.commence_time_is_kickoff, "all"))).toBe(true);
  });
});

describe("#6158 — not started yet, so no Start", () => {
  const flag = pageKickoffFlag("scheduled", true);

  it("scheduled + authority_not_started ⇒ the page answers `false`", () => {
    expect(flag).toBe(false);
  });

  it("no 'Start' marker, no 'Since Start' pill", () => {
    expect(startMarker(draw(flag, "all"))).toBe("");
    expect(offersSinceStart(draw(flag, "all"))).toBe(false);
  });

  it("CONTROL — key absent, or the row no longer scheduled, keeps the served flag", () => {
    expect(pageKickoffFlag("scheduled", undefined)).toBe(true);
    expect(pageKickoffFlag("scheduled", false)).toBe(true);
    expect(pageKickoffFlag("live", true)).toBe(true);
  });
});

describe("#6158 — the event page wires it", () => {
  const src = fs.readFileSync(path.join(__dirname, "../../app/events/[id]/page.tsx"), "utf8");

  it("derives the arm from the scheduled status and the served key", () => {
    expect(src).toMatch(
      /const authorityHasNotStarted =\s*event\?\.status === "scheduled" && event\?\.authority_not_started === true;/,
    );
  });

  it("the arm feeds the one flag both charts read", () => {
    expect(src).toMatch(
      /const commenceTimeIsKickoff = heroScoreIsStoppageFiller \|\| authorityHasNotStarted\s*\?\s*false\s*:\s*historyData\?\.commence_time_is_kickoff;/,
    );
  });
});
