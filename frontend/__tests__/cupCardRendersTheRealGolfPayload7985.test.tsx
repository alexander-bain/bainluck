/**
 * #7985 — the Presidents Cup card, MOUNTED, from the payload the route serves.
 *
 * ═══ WHY THIS EXISTS WHEN #7985 IS ALREADY GUARDED ═══
 *
 * The backend suite
 * (`backend/tests/test_golf_team_match_play_has_no_individual_markets_7985.py`)
 * proves the SERVED side: the five phantom DataGolf markets are withheld, the
 * Presidents Cup card survives on its Kalshi team market, and the team pair is
 * promoted into `golfers` as `[("Team USA", 81.5), ("Team World", 14.5)]`.
 *
 * Its `TestTheCardContractMatchesTheFrontend` class then reaches across the tier
 * and asserts this component's SOURCE TEXT — `"tournament.golfers.length === 2"`,
 * `"const [teamA, teamB] = tournament.golfers;"`. Those are substring reads of a
 * file that lane does not own. They catch a deletion; they cannot catch a
 * component that still contains both lines and renders the wrong thing — a
 * swapped pair, a dropped `* 100`, a `toFixed(0)`, a colour-map lookup that
 * throws on an unknown team name.
 *
 * Nothing mounted the card. That was CERT-3293's named nonblocking follow-up
 * (`7985-MOUNT-CUPCARD-WITH-REAL-GOLF-PAYLOAD`) and it is what this file is.
 *
 * ═══ THE DEFECT, RESTATED AS WHAT A READER SAW ═══
 *
 * production `/golf`, before the fix: the PGA Tour card led
 *
 *     6.1%   Jackson Koivun
 *            Leader
 *
 * for the Presidents Cup — a 132-player stroke-play field minted for a 24-player
 * team match-play event, with Kalshi's real Team USA 81.5% v Team World 14.5%
 * sitting unled in the same payload. Koivun is not in the event.
 *
 * ═══ THE FIXTURE IS THE SERVED SHAPE, NOT A CONVENIENT ONE ═══
 *
 * `teamEntry` carries every field the backend's
 * `test_a_promoted_team_carries_every_field_a_golfer_entry_carries` pins
 * (name, probability, rank, movement_24h, movement_is_dated, sources,
 * opening_probability), because a short entry is how a hand-built fake passes a
 * render test that production would fail. The two probabilities are the wire
 * values (0.815 / 0.145), not the rendered percentages — the `* 100` is the
 * component's job and therefore this file's subject.
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

/** One `golfers[]` entry in the shape `routes/golf.py` promotes a team into. */
function teamEntry(name: string, probability: number, rank: number) {
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

/**
 * The Presidents Cup card as `GET /api/golf` serves it after the fix: no
 * individual golfers, the Kalshi team pair promoted into `golfers`, the real
 * matchup still carried in `h2h_matchups`.
 */
function presidentsCup(
  golfers = [teamEntry("Team USA", 0.815, 1), teamEntry("Team World", 0.145, 2)],
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
    prop_markets: [],
    h2h_matchups: [
      {
        market_id: 16757297,
        source: "kalshi",
        golfer_a: { name: "Team USA", probability: 0.815 },
        golfer_b: { name: "Team World", probability: 0.145 },
      },
    ],
  } as unknown as GolfTournament;
}

const render = (t: GolfTournament) =>
  renderToStaticMarkup(<TournamentCard tournament={t} />);

/**
 * Every `<name, percentage>` pair the cup layout prints, IN RENDER ORDER.
 *
 * Order is part of the assertion: `CupCard` draws `teamA` left and `teamB`
 * right, so a promotion that swapped the sides would put the 14.5% underdog in
 * the leading position and no unordered check would see it.
 */
function renderedPairs(markup: string): Array<[string, string]> {
  const re =
    /<div class="text-xs font-semibold[^"]*">([^<]+)<\/div><div class="text-\[22px\][^"]*">([\d.]+)<span/g;
  const out: Array<[string, string]> = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(markup)) !== null) out.push([m[1], m[2]]);
  return out;
}

// ---------------------------------------------------------------------------

describe("#7985 — the mounted card leads with the two teams", () => {
  test("THE PRODUCTION SPECIMEN: Team USA 81.5 v Team World 14.5, in that order", () => {
    expect(renderedPairs(render(presidentsCup()))).toEqual([
      ["Team USA", "81.5"],
      ["Team World", "14.5"],
    ]);
  });

  test("no person is on the card — the defect, as the thing that cannot return", () => {
    const markup = render(presidentsCup());

    expect(markup).not.toContain("Koivun");
    // Not just the one name: the stroke-play hero caption itself is absent, so a
    // future arm that leads with ANY individual fails here too.
    expect(markup).not.toContain("Leader");
  });

  test("the strawman: a person in golfers[0] WOULD reach the hero", () => {
    // Without this, the two tests above pass for a card that renders nothing at
    // all. This proves the assertions are wired to real output: feed the
    // pre-fix shape and the person appears.
    const markup = render(
      presidentsCup([
        teamEntry("Jackson Koivun", 0.061, 1),
        teamEntry("Scottie Scheffler", 0.058, 2),
      ]),
    );

    expect(markup).toContain("Jackson Koivun");
    expect(renderedPairs(markup)).toEqual([
      ["Jackson Koivun", "6.1"],
      ["Scottie Scheffler", "5.8"],
    ]);
  });

  test("the card is still on the page — withholding must not delete it", () => {
    expect(render(presidentsCup())).toContain("Presidents Cup");
  });

  test("an unknown team name renders rather than throwing on the colour map", () => {
    // The colour lookup falls back rather than throwing. Names invented on
    // purpose: as of #8028 the production pair ("Team USA" / "Team World") is
    // RECOGNISED — that filing was precisely that it was not — so this case
    // needs sides no vocabulary holds to still exercise the fallback.
    // What the fallback PAINTS is #8028's subject, guarded in
    // `cupBarDifferentiatesItsTwoSides8028.test.tsx`; here it is only that an
    // unknown side renders its name and number at all.
    const pairs = renderedPairs(
      render(presidentsCup([
        teamEntry("Team Atlantis", 0.5, 1),
        teamEntry("Team Pacifica", 0.5, 2),
      ])),
    );

    expect(pairs).toEqual([
      ["Team Atlantis", "50.0"],
      ["Team Pacifica", "50.0"],
    ]);
  });
});
