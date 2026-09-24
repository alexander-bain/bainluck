/**
 * #8474 — the playoff grid printed one move's size two different ways.
 *
 * Both renderers chose their precision from the RAW value and then printed the
 * ROUNDED one: `pct >= 1 ? Math.round(pct) : pct.toFixed(1)`. So a 1.74-point
 * move lost its decimal ("+2%") while a 0.96-point move, which rounds to the
 * same whole number, kept one ("+1.0%"). The chip row on /playoffs/ncaa-football
 * read "+2% … +1% … +1.0%" — the smallest move carried the most precision.
 *
 * The fix routes both through `formatMovementPointsLikeSentence` (one decimal,
 * trailing ".0" dropped), so the precision is decided by the printed string —
 * and, being that formatter, they now say POINTS the way the rest of its family
 * does (#5666 class scan): "+1.7 pts", "▲1.7 pts 24h". The old "%" read a
 * 1.7-point move as a 1.7% relative change.
 *
 * Specimen: `GET /api/playoffs/ncaa-football` movers, read 2026-09-24.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import SERVED_CONTROL from "./fixtures/uxp175_playoffs_nba_control.json";

jest.mock("@/hooks/useAnalytics", () => ({
  useAnalytics: () => ({ track: () => {} }),
}));

let gridPayload: unknown;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => ({
    data: key === null ? undefined : gridPayload,
    error: undefined,
    isLoading: false,
    mutate: () => undefined,
  }),
}));

jest.mock("@/hooks", () => ({
  __esModule: true,
  usePageTracking: () => undefined,
  useScrollDepth: () => undefined,
  useEngagementTime: () => undefined,
}));

jest.mock("next/navigation", () => ({
  __esModule: true,
  useRouter: () => ({ push: () => {}, replace: () => {}, prefetch: () => {} }),
  usePathname: () => "/playoffs/ncaa-football",
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ sport: "ncaa-football" }),
}));

import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import { gridCellsToProgression } from "@/lib/gridCellState";
import type { ProgressionResponse } from "@/lib/types";

// eslint-disable-next-line @typescript-eslint/no-var-requires
const PlayoffGridPage = require("@/app/playoffs/[sport]/page").default;
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

/** The served movers, as 0–1 fractions, and what each chip must print. */
const SPECIMEN: { name: string; change: number; chip: string }[] = [
  { name: "Mississippi State Bulldogs", change: 0.0174, chip: "+1.7 pts" },
  { name: "Indiana Hoosiers", change: 0.0151, chip: "+1.5 pts" },
  { name: "Texas Longhorns", change: 0.0114, chip: "+1.1 pts" },
  { name: "Ole Miss", change: -0.01, chip: "-1 pts" },
  { name: "Miami Hurricanes", change: 0.0096, chip: "+1 pts" },
  { name: "Notre Dame Fighting Irish", change: 0.0066, chip: "+0.7 pts" },
  { name: "Georgia Bulldogs", change: 0.0059, chip: "+0.6 pts" },
  { name: "Texas Tech Red Raiders", change: -0.0053, chip: "-0.5 pts" },
];

function renderPage(): string {
  gridPayload = {
    ...SERVED_CONTROL,
    movers: SPECIMEN.map((s) => ({
      name: s.name,
      short_name: s.name,
      team_id: null,
      column: "championship",
      change_24h: s.change,
      direction: s.change > 0 ? "up" : "down",
      logo_url: null,
      primary_color: "#000000",
    })),
  };
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      React.createElement(PlayoffGridPage, { params: { sport: "ncaa-football" } }),
    ),
  );
}

/** `{team: chip text}` read off the Biggest Movers row. */
function chipsByTeam(markup: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const { name } of SPECIMEN) {
    const re = new RegExp(
      `<span class="font-medium">${name}</span><span class="font-mono text-xs">([^<]*)</span>`,
    );
    const m = re.exec(markup.replace(/<!-- -->/g, ""));
    if (m) out[name] = m[1];
  }
  return out;
}

function renderGrid(): string {
  const data: ProgressionResponse = {
    sport: "americanfootball_ncaaf",
    tournament_name: "College Football Playoff",
    stages: [
      {
        key: "championship",
        label: "Champion",
        order: 1,
        market_id: null,
        market_name: null,
        resolved: false,
      },
    ],
    participants: SPECIMEN.map((s) => {
      const { probabilities, changes_24h, status, sources_data } = gridCellsToProgression({
        championship: {
          merged_probability: 0.1,
          trend_24h: s.change,
          sources: [],
          state: "live",
        },
      });
      return {
        name: s.name,
        team_id: null,
        logo_url: null,
        primary_color: null,
        conference: null,
        region: null,
        seed: null,
        record: null,
        probabilities,
        changes_24h,
        status,
        sources_data,
      };
    }),
  };
  return renderToStaticMarkup(<TournamentProgressionTable data={data} />);
}

/** `{team: {cell: "▲1.7", suffix: "pts 24h", title: "+1.7 pts in 24h"}}`. */
function cellsByTeam(
  markup: string,
): Record<string, { cell: string; suffix: string; title: string }> {
  const rows = markup.split("<tr").slice(1);
  const out: Record<string, { cell: string; suffix: string; title: string }> = {};
  for (const { name } of SPECIMEN) {
    const row = rows.find((r) => r.includes(name));
    if (!row) continue;
    const m = /title="([^"]* in 24h)">([▲▼])(?:<!-- -->)?([^<]*)<span[^>]*>([^<]*)<\/span>/.exec(row);
    if (m) out[name] = { cell: `${m[2]}${m[3]}`, suffix: m[4], title: m[1] };
  }
  return out;
}

describe("Biggest Movers chip precision (#8474)", () => {
  it("prints every served move at the same precision", () => {
    expect(chipsByTeam(renderPage())).toEqual(
      Object.fromEntries(SPECIMEN.map((s) => [s.name, s.chip])),
    );
  });

  it("never gives a sub-1-point move more digits than a larger one", () => {
    // The photographed shape: "+1%" (1.4 pt) beside "+1.0%" (0.96 pt).
    const chips = Object.values(chipsByTeam(renderPage()));
    expect(chips).toHaveLength(SPECIMEN.length);
    expect(chips.some((c) => /\.0\b/.test(c))).toBe(false);
    expect(chips.some((c) => c.includes("%"))).toBe(false);
  });
});

describe("grid 24h cell precision (#8474)", () => {
  it("prints the same magnitude the chip does, and says points", () => {
    expect(cellsByTeam(renderGrid())).toEqual(
      Object.fromEntries(
        SPECIMEN.map((s) => {
          const mag = s.chip.slice(1).replace(/ pts$/, "");
          return [
            s.name,
            {
              cell: `${s.change > 0 ? "▲" : "▼"}${mag}`,
              suffix: "pts 24h",
              title: `${s.chip} in 24h`,
            },
          ];
        }),
      ),
    );
  });
});
