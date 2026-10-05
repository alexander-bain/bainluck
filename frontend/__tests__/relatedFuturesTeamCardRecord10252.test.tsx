/**
 * #10252 — THE TEAM CARD PRINTS THE HERO'S RECORD.
 *
 * Production, 2026-10-05 04:5xZ, 390px, `/events/15169781` (Panthers @ Ducks,
 * Final 2-3 in overtime): the hero read "Panthers 1-0-1, #3 Atlantic, 3 pts";
 * the Bigger Picture card read "Panthers 1-0 · #3 Atlantic Division". The
 * served blob (verbatim below) carried the overtime loss as `draws: 1` and the
 * card composed W-L(-ties) only. Frame: ux worktree
 * `artifacts/ux-1005-nhl-walk/fla04.png`.
 *
 * Both directions (gotcha #43): the served record is printed when it is a
 * record, and a card with no standings still prints no record line.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import RelatedFutures from "@/components/RelatedFutures";
import { teamCardRecord } from "@/lib/teamCardRecord";
import type { RelatedFuturesResponse } from "@/lib/types";

const EVENT_ID = 15169781;

type Standings = NonNullable<
  React.ComponentProps<typeof RelatedFutures>["homeStandings"]
>;

// `/api/events/15169781` at 04:55Z on 2026-10-05, standings keys the card reads.
const DUCKS: Standings & Record<string, unknown> = {
  wins: 1, losses: 0, draws: 0, points: 2, div_rank: 4,
  division: "Pacific Division", conference: "Western Conference",
};
const PANTHERS: Standings & Record<string, unknown> = {
  wins: 1, losses: 0, draws: 1, points: 3, div_rank: 3,
  division: "Atlantic Division", conference: "Eastern Conference",
};

jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({
    data: {
      event_id: EVENT_ID,
      home_team: "Anaheim Ducks",
      away_team: "Florida Panthers",
      home_team_futures: [],
      away_team_futures: [],
      series_markets: [],
      total_count: 0,
      summary: null,
      event_status: "completed",
      box_score: null,
      league_context: null,
    } as unknown as RelatedFuturesResponse,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));

function render(opts: {
  homeStandings?: Standings;
  awayStandings?: Standings;
  homeRecord?: string | null;
  awayRecord?: string | null;
}): string {
  return renderToStaticMarkup(
    React.createElement(RelatedFutures, {
      eventId: EVENT_ID,
      homeTeam: "Anaheim Ducks",
      awayTeam: "Florida Panthers",
      homeTeamColor: "#F47A38",
      awayTeamColor: "#C8102E",
      sportKey: "icehockey_nhl",
      eventStatus: "completed",
      ...opts,
    }),
  );
}

function cardRecordLine(html: string, testId: string): string | null {
  const start = html.indexOf(`data-testid="${testId}"`);
  if (start < 0) return null;
  const m = html.slice(start).match(/font-mono tabular-nums">([^<]*)</);
  return m ? m[1].replace(/&#x27;/g, "'") : null;
}

describe("#10252: the Bigger Picture team card prints the same record as the hero", () => {
  it("THE REPORTED PAGE: the Panthers' overtime loss stays on the card", () => {
    const html = render({
      homeStandings: DUCKS,
      awayStandings: PANTHERS,
      homeRecord: "1-0-0",
      awayRecord: "1-0-1",
    });
    expect(cardRecordLine(html, "away-team-card")).toBe("1-0-1 · #3 Atlantic Division");
    expect(cardRecordLine(html, "home-team-card")).toBe("1-0-0 · #4 Pacific Division");
  });

  it("with no served record, the blob's `draws` is still the third column", () => {
    const html = render({ homeStandings: DUCKS, awayStandings: PANTHERS });
    expect(cardRecordLine(html, "away-team-card")).toBe("1-0-1 · #3 Atlantic Division");
    // A zero third column composes nothing, as the server's `_snapshot_record` does.
    expect(cardRecordLine(html, "home-team-card")).toBe("1-0 · #4 Pacific Division");
  });

  it("CONTROL: a team with no standings draws no card and no record", () => {
    const html = render({ homeStandings: DUCKS, homeRecord: "1-0-0", awayRecord: "1-0-1" });
    expect(cardRecordLine(html, "home-team-card")).toBe("1-0-0 · #4 Pacific Division");
    expect(html).not.toContain('data-testid="away-team-card"');
  });
});

describe("teamCardRecord", () => {
  it("prints a served W-L or W-L-D record verbatim", () => {
    expect(teamCardRecord("93-60", { wins: 92, losses: 60 })).toBe("93-60");
    expect(teamCardRecord(" 0-1-1 ", { wins: 0, losses: 1 })).toBe("0-1-1");
  });

  it("falls back to the blob when the served string is not a record", () => {
    expect(teamCardRecord("Last season", { wins: 5, losses: 2, draws: 3 })).toBe("5-2-3");
    expect(teamCardRecord(null, { wins: 5, losses: 2, ties: 1 })).toBe("5-2-1");
    expect(teamCardRecord(undefined, { wins: 5, losses: 2, draws: 0 })).toBe("5-2");
  });

  it("returns null without standings, whatever is served", () => {
    expect(teamCardRecord("1-0-1", undefined)).toBeNull();
    expect(teamCardRecord("1-0-1", null)).toBeNull();
  });
});
