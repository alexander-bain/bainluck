/**
 * #8782 — the Presidents Cup card's prop heading read ": HOLE-IN-ONE".
 *
 * `_cleanPropLabel` strips the tournament name out of the Kalshi market name
 * "Presidents Cup: Hole-in-One" and then cleaned up only a leftover "·", so the
 * colon survived and led the heading. The helper is private, so this mounts the
 * card and reads the rendered heading — through BOTH render sites: the cup
 * layout (two teams in `golfers`) and the stroke-play layout (a field).
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import TournamentCard from "../components/TournamentCard";
import type { GolfTournament } from "../lib/types";

function golfer(name: string, probability: number, rank: number) {
  return {
    name,
    probability,
    rank,
    movement_24h: null,
    movement_is_dated: false,
    sources: ["kalshi"],
    opening_probability: null,
  };
}

function prop(name: string) {
  return {
    name,
    source: "kalshi",
    outcomes: [
      { name: "Yes", probability: 0.31 },
      { name: "No", probability: 0.69 },
    ],
  };
}

const CUP_TEAMS = [golfer("Team USA", 0.815, 1), golfer("Team World", 0.145, 2)];
const FIELD = [
  golfer("Scottie Scheffler", 0.2, 1),
  golfer("Rory McIlroy", 0.1, 2),
  golfer("Xander Schauffele", 0.08, 3),
];

function tournament(
  propNames: string[],
  golfers: ReturnType<typeof golfer>[] = CUP_TEAMS,
): GolfTournament {
  return {
    key: "presidents_cup",
    slug: "presidents-cup",
    name: "Presidents Cup",
    tour: "pga",
    tour_label: "PGA Tour",
    location: "Medinah Country Club",
    venue: "Medinah Country Club",
    start_date: "2026-09-24",
    end_date: "2026-09-27",
    commence_time: "2026-09-24T12:00:00Z",
    resolution_date: null,
    is_major: false,
    is_marquee: true,
    schedule_status: "upcoming",
    source_count: 1,
    market_ids: [16757297],
    golfers,
    prop_markets: propNames.map(prop),
    h2h_matchups: [],
  } as unknown as GolfTournament;
}

/** Every prop heading the card prints, in render order. */
function headings(t: GolfTournament): string[] {
  const markup = renderToStaticMarkup(<TournamentCard tournament={t} />);
  const re = /<div class="text-\[10px\] font-semibold text-text-tertiary uppercase[^"]*">([^<]*)<\/div>/g;
  const out: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(markup)) !== null) out.push(m[1]);
  return out;
}

describe("#8782 — a stripped tournament name leaves no separator on the prop heading", () => {
  test("THE PRODUCTION SPECIMEN, cup layout: 'Presidents Cup: Hole-in-One' → 'Hole-in-One'", () => {
    expect(
      headings(tournament(["Presidents Cup: Hole-in-One", "Presidents Cup Winning Margin"])),
    ).toEqual(["Hole-in-One", "Winning Margin"]);
  });

  test("the stroke-play layout uses the same helper and reads the same", () => {
    expect(headings(tournament(["Presidents Cup: Hole-in-One"], FIELD))).toEqual([
      "Hole-in-One",
    ]);
  });

  test("dash separators, either side of the name, are cleaned too", () => {
    expect(
      headings(
        tournament([
          "Presidents Cup – Top Points Scorer",
          "Presidents Cup — Captains Picks",
          "Hole-in-One - Presidents Cup",
        ]),
      ),
    ).toEqual(["Top Points Scorer", "Captains Picks", "Hole-in-One"]);
  });

  test("the pre-existing '·' cleanup still works", () => {
    // "at the 2027 Presidents Cup" becomes " · Presidents Cup", then the name is stripped.
    expect(headings(tournament(["Hole-in-One at the 2027 Presidents Cup?"]))).toEqual([
      "Hole-in-One",
    ]);
  });

  test("a hyphen that is part of the label is kept — a sign is not a separator", () => {
    expect(headings(tournament(["Presidents Cup -3.5 Team USA"]))).toEqual(["-3.5 Team USA"]);
  });

  test("the strawman: a colon INSIDE the label survives, and the reader sees it", () => {
    // Without this, the tests above would pass for a reader that dropped
    // colons. Only a separator at an end is cleaned; one mid-label is content.
    expect(headings(tournament(["Presidents Cup: Day 1: Foursomes Leader"]))).toEqual([
      "Day 1: Foursomes Leader",
    ]);
  });
});
