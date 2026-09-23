// #3348 — AN ESTIMATED PERIOD BOUNDARY IS DRAWN AS AN ESTIMATE.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// The server places a tier-4 `period_markers` entry by arithmetic on
// `commence_time` and labels it `source: "estimated"` (live/066, PR #3368).
// `derivePeriodBoundaries` mapped every marker to `{timestamp, label}`, so by
// the time a marker reached `<ReferenceLine>` a guess and an observed transition
// were byte-identical. ux/1319 measured it on production 2026-09-17: 46 of 60
// completed soccer charts drew confident `1H`/`2H` rules nobody observed, and
// `/events/15307941` ruled `Q1 Q2 Q3 Q4` over an event with no game-state row
// at all.
//
// ── SPECIMEN ─────────────────────────────────────────────────────────────────
//
// `GET /api/events/15196980/history` (Raiders 14 – Cardinals 27, 2026-08-13,
// the #1833 web specimen), fetched 2026-09-23 against production `0411e045`
// and saved verbatim for the in-game window. Its two markers are
//   `{"1st Quarter", 00:00:00Z, source: "estimated"}`
//   `{"2nd Quarter", 00:45:00Z, source: "estimated"}`
// — kickoff and kickoff + 45 min, with `espn_history: []`, `scoring_plays: []`
// and no `game_state` on any `win_prob_history` row. Nobody saw either.
//
// ── THE CONTRACT (codex, 2026-09-22) ─────────────────────────────────────────
//
// "No estimate silently becomes an observed boundary. Preserve source,
// precision and not_before; a first observed state is not automatically exact
// period start. Unknown stays unknown; a clearly labelled estimate is distinct
// from a measured one." Estimates are NOT dropped — that is a product call
// ux/1319 declined to make on 77% of soccer charts — they are LABELLED.
//
// ── CONTROLS ─────────────────────────────────────────────────────────────────
//
// Every arm below is red on the parent (`83a20bc74`) and green on the
// candidate, except the "observed markers render exactly as before" arm, which
// is green on both and is the regression control.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

import OddsChart from "@/components/OddsChart";
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import { AnalyticsProvider } from "@/components/Analytics";
import {
  derivePeriodBoundaries,
  isEstimatedBoundary,
  periodBoundaryChipLabel,
  CLIENT_SOURCE_WIN_PROB_HISTORY,
  CLIENT_SOURCE_ESPN_HISTORY,
  CLIENT_PRECISION_FIRST_SEEN,
} from "@/lib/periodMarkers";
import type { WinProbHistoryPoint, ESPNHistoryPoint } from "@/lib/types";

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 390, height: 300 }),
  };
});

const ESTIMATED = JSON.parse(
  readFileSync(join(__dirname, "fixtures/estimatedMarkers.15196980.nfl-preseason.json"), "utf8"),
);
const OBSERVED = JSON.parse(
  readFileSync(join(__dirname, "fixtures/priorGameAxis.15192596.mlb-final.json"), "utf8"),
);

/** Every `<tspan>` inside a labelled reference line, in document order. */
function chipTexts(markup: string): string[] {
  const out: string[] = [];
  const re = /<g class="[^"]*recharts-reference-line[^"]*">[\s\S]*?<text[^>]*class="[^"]*recharts-label[^"]*"[^>]*>[\s\S]*?<tspan[^>]*>([^<]*)<\/tspan>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(markup)) !== null) out.push(m[1].trim());
  return out;
}

/** The `<line>` elements of every reference line, with their dash pattern. */
function referenceLineDashes(markup: string): string[] {
  const out: string[] = [];
  const re = /<g class="[^"]*recharts-reference-line[^"]*">[\s\S]*?<line([^>]*)>/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(markup)) !== null) {
    const dash = m[1].match(/stroke-dasharray="([^"]*)"/);
    out.push(dash ? dash[1] : "");
  }
  return out;
}

function renderOdds(wire: typeof ESTIMATED, sport: string): string {
  const boundaries = derivePeriodBoundaries(
    wire.espn_history,
    wire.win_prob_history,
    wire.scoring_plays,
    wire.period_markers,
    sport,
  );
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(OddsChart, {
        history: wire.history,
        homeTeam: wire.home_team,
        awayTeam: wire.away_team,
        commenceTime: wire.commence_time,
        espnHistory: wire.espn_history,
        winProbHistory: wire.win_prob_history,
        winProbSources: wire.win_prob_sources,
        aggregateLine: wire.aggregate_line,
        scoringPlays: wire.scoring_plays,
        eventStatus: wire.status,
        periodBoundaries: boundaries,
      } as never),
    ),
  );
}

function renderSdc(wire: typeof ESTIMATED, sport: string): string {
  const boundaries = derivePeriodBoundaries(
    wire.espn_history,
    wire.win_prob_history,
    wire.scoring_plays,
    wire.period_markers,
    sport,
  );
  return renderToStaticMarkup(
    React.createElement(ScoreDifferentialChart, {
      history: wire.history,
      homeTeam: wire.home_team,
      awayTeam: wire.away_team,
      commenceTime: wire.commence_time,
      scoreHistory: wire.score_history,
      espnHistory: wire.espn_history,
      eventStatus: wire.status,
      sportKey: sport,
      periodBoundaries: boundaries,
    } as never),
  );
}

describe("#3348 — provenance rides on the derived boundary", () => {
  it("the specimen's two markers are estimates, and the derivation says so", () => {
    const b = derivePeriodBoundaries(
      ESTIMATED.espn_history,
      ESTIMATED.win_prob_history,
      ESTIMATED.scoring_plays,
      ESTIMATED.period_markers,
      "americanfootball_nfl",
    );
    expect(b.map((x) => x.label)).toEqual(["Q1", "Q2"]);
    // Positions are unchanged — the estimate is not moved, only named.
    expect(b.map((x) => x.timestamp)).toEqual([
      "2026-08-13T00:00:00+00:00",
      "2026-08-13T00:45:00+00:00",
    ]);
    expect(b.map(isEstimatedBoundary)).toEqual([true, true]);
    expect(b.map(periodBoundaryChipLabel)).toEqual(["~Q1", "~Q2"]);
  });

  it("an observed server marker keeps its source and prints a plain chip (control)", () => {
    const b = derivePeriodBoundaries(
      OBSERVED.espn_history,
      OBSERVED.win_prob_history,
      OBSERVED.scoring_plays,
      OBSERVED.period_markers,
      "baseball_mlb",
    );
    expect(b.length).toBeGreaterThan(0);
    for (const x of b) {
      expect(x.source).toBe("win_prob");
      expect(isEstimatedBoundary(x)).toBe(false);
      expect(periodBoundaryChipLabel(x)).toBe(x.label);
    }
  });

  it("the transition tier's precision and not_before survive the derivation", () => {
    const markers = [
      {
        timestamp: "2026-09-15T00:54:43+00:00",
        period: "2nd Quarter",
        source: "espn_state",
        precision: "boundary_observed",
        not_before: "2026-09-15T00:53:43+00:00",
      },
      {
        timestamp: "2026-09-15T02:10:00+00:00",
        period: "4th Quarter",
        source: "espn_state",
        precision: "first_seen",
        not_before: "2026-09-15T01:58:00+00:00",
      },
    ];
    const b = derivePeriodBoundaries(undefined, undefined, undefined, markers, "americanfootball_nfl");
    expect(b.map((x) => [x.label, x.source, x.precision, x.notBefore])).toEqual([
      ["Q2", "espn_state", "boundary_observed", "2026-09-15T00:53:43+00:00"],
      ["Q4", "espn_state", "first_seen", "2026-09-15T01:58:00+00:00"],
    ]);
  });

  it("a marker with no source is neither promoted nor demoted (unknown stays unknown)", () => {
    const b = derivePeriodBoundaries(
      undefined,
      undefined,
      undefined,
      [{ timestamp: "2026-09-15T00:54:43+00:00", period: "2nd Quarter" }],
      "americanfootball_nfl",
    );
    expect(b).toHaveLength(1);
    expect(b[0].source).toBeUndefined();
    expect(isEstimatedBoundary(b[0])).toBe(false);
    expect(periodBoundaryChipLabel(b[0])).toBe("Q2");
  });
});

describe("#3348 — a client-derived boundary is a FIRST OBSERVATION, not a start", () => {
  const wp: Record<string, WinProbHistoryPoint[]> = {
    espn: [
      // Late first observation: the feed joined in the 2nd quarter. Q2 has
      // nothing bounding it from below — the log never showed an earlier
      // state — so `notBefore` is null, not kickoff.
      { timestamp: "2026-09-15T01:05:00+00:00", home_probability: 0.6, game_state: { period: "2nd Quarter" } },
      { timestamp: "2026-09-15T01:06:00+00:00", home_probability: 0.6, game_state: { period: "2nd Quarter" } },
      { timestamp: "2026-09-15T01:40:00+00:00", home_probability: 0.6, game_state: { period: "3rd Quarter" } },
    ] as unknown as WinProbHistoryPoint[],
  };

  it("names the log, calls itself first_seen, and brackets from the previous observation", () => {
    const b = derivePeriodBoundaries(undefined, wp, undefined, undefined, "americanfootball_nfl");
    expect(b.map((x) => [x.label, x.timestamp, x.source, x.precision, x.notBefore])).toEqual([
      ["Q2", "2026-09-15T01:05:00+00:00", CLIENT_SOURCE_WIN_PROB_HISTORY, CLIENT_PRECISION_FIRST_SEEN, null],
      ["Q3", "2026-09-15T01:40:00+00:00", CLIENT_SOURCE_WIN_PROB_HISTORY, CLIENT_PRECISION_FIRST_SEEN, "2026-09-15T01:06:00+00:00"],
    ]);
    expect(b.map(isEstimatedBoundary)).toEqual([false, false]);
  });

  it("the ESPN log is named as such", () => {
    const espn: ESPNHistoryPoint[] = [
      { timestamp: "2026-09-15T00:30:00+00:00", home_probability: 0.5, period: "1st Quarter" },
      { timestamp: "2026-09-15T00:58:00+00:00", home_probability: 0.5, period: "2nd Quarter" },
    ] as unknown as ESPNHistoryPoint[];
    const b = derivePeriodBoundaries(espn, undefined, undefined, undefined, "americanfootball_nfl");
    expect(b.map((x) => [x.label, x.source, x.notBefore])).toEqual([
      ["Q1", CLIENT_SOURCE_ESPN_HISTORY, null],
      ["Q2", CLIENT_SOURCE_ESPN_HISTORY, "2026-09-15T00:30:00+00:00"],
    ]);
  });
});

describe("#3348 — an observation beats an estimate of the same period", () => {
  it("an observed Q2 replaces the estimated Q2 at kickoff+45 (observed vs estimated)", () => {
    const observedQ2 = "2026-08-13T00:52:30+00:00"; // 7.5 min after the guess
    const wp: Record<string, WinProbHistoryPoint[]> = {
      espn: [
        { timestamp: "2026-08-13T00:20:00+00:00", home_probability: 0.5, game_state: { period: "1st Quarter" } },
        { timestamp: observedQ2, home_probability: 0.5, game_state: { period: "2nd Quarter" } },
      ] as unknown as WinProbHistoryPoint[],
    };
    const b = derivePeriodBoundaries(undefined, wp, undefined, ESTIMATED.period_markers, "americanfootball_nfl");
    const q2 = b.find((x) => x.label === "Q2")!;
    expect(q2.timestamp).toBe(observedQ2);
    expect(isEstimatedBoundary(q2)).toBe(false);
    expect(q2.source).toBe(CLIENT_SOURCE_WIN_PROB_HISTORY);
    // Q1 was also observed — at 00:20, not at the scheduled 00:00.
    const q1 = b.find((x) => x.label === "Q1")!;
    expect(q1.timestamp).toBe("2026-08-13T00:20:00+00:00");
    expect(isEstimatedBoundary(q1)).toBe(false);
    expect(b.map((x) => x.label)).toEqual(["Q1", "Q2"]);
  });

  it("an OBSERVED server marker is never moved by the fallback (#7917 regression control)", () => {
    const served = [
      { timestamp: "2026-08-13T00:50:00+00:00", period: "2nd Quarter", source: "espn_state", precision: "boundary_observed", not_before: "2026-08-13T00:49:00+00:00" },
    ];
    const wp: Record<string, WinProbHistoryPoint[]> = {
      espn: [
        { timestamp: "2026-08-13T00:52:30+00:00", home_probability: 0.5, game_state: { period: "2nd Quarter" } },
      ] as unknown as WinProbHistoryPoint[],
    };
    const b = derivePeriodBoundaries(undefined, wp, undefined, served, "americanfootball_nfl");
    expect(b).toHaveLength(1);
    expect(b[0].timestamp).toBe("2026-08-13T00:50:00+00:00");
    expect(b[0].source).toBe("espn_state");
  });
});

describe("#3348 — the rendered chip says it is an estimate", () => {
  it("OddsChart prints ~Q1 ~Q2 on the estimated specimen, dotted", () => {
    const markup = renderOdds(ESTIMATED, "americanfootball_nfl");
    const chips = chipTexts(markup);
    expect(chips).toEqual(expect.arrayContaining(["~Q1", "~Q2"]));
    expect(chips).not.toEqual(expect.arrayContaining(["Q1", "Q2"]));
    // The period rules are the dotted ones; the `y=50` guide and the Final rule
    // keep their own patterns, so "at least two `2 4` rules" is the claim.
    expect(referenceLineDashes(markup).filter((d) => d === "2 4").length).toBeGreaterThanOrEqual(2);
  });

  it("ScoreDifferentialChart prints the same ~ chips", () => {
    const markup = renderSdc(ESTIMATED, "americanfootball_nfl");
    const chips = chipTexts(markup);
    // The score chart bounds markers against its own drawn score line; if it
    // draws any period chip on this specimen, every one of them is an estimate.
    for (const c of chips) expect(c.startsWith("~")).toBe(true);
    if (chips.length > 0) {
      expect(referenceLineDashes(markup).filter((d) => d === "2 4").length).toBeGreaterThanOrEqual(chips.length);
    }
  });

  it("observed markers render exactly as before — no ~, dashed 6 4 (control)", () => {
    const markup = renderOdds(OBSERVED, "baseball_mlb");
    const chips = chipTexts(markup);
    expect(chips.length).toBeGreaterThan(0);
    for (const c of chips) expect(c.startsWith("~")).toBe(false);
    expect(referenceLineDashes(markup).filter((d) => d === "2 4")).toHaveLength(0);
  });
});
