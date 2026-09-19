// #6372 — A DRAW IS NOT A PERSON, SO IT DOES NOT GET A PERSON'S FACE.
//
// Sighted at 390px on production, `/events/15312629` (Club Necaxa v CF
// América), Bigger Picture → `OTHER (1)`. One tile:
//
//       ( D( )          ← a circular player-headshot avatar, initials "D("
//   Draw (Club Necaxa vs. CF América)
//         27%
//
// A reader met a footballer called "D(" — the first two characters of the
// outcome string, one of them an open parenthesis.
//
// `parseStatOutcome`'s third branch returned `playerName: outcomeName` for
// anything with no colon and no leading Over/Under, so every unparsed string
// became a person, and `PlayerHeadshot`'s last fallback draws initials for a
// name it cannot resolve. Same principle as #6210 and #6253 — a prop row's
// subject is READ from the outcome, never invented.
//
// ═══ WHAT THIS FILE ASSERTS, AND THE HALF THAT IS EASY TO FORGET ═══
//
// The fix nulls `playerName`, which is the answer to "is there a person here".
// The risk in that is deleting the row's NAME along with its face: the tile
// text, its `title` and the dedup key all read `playerName || outcomeName`, and
// one of them (`tileLabels`) fell through to an em-dash instead. So the label
// assertions below are not decoration — a fix that silenced the tile would pass
// any test that only looked for the missing avatar.
//
// BOTH DIRECTIONS PER GOTCHA #43: every case has a sibling proving an ordinary
// player name still gets its face.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

let payload: Record<string, unknown> = {};
jest.mock("swr", () => ({
  __esModule: true,
  default: () => ({ data: payload, error: undefined, isLoading: false }),
}));
jest.mock("@/lib/api", () => ({
  fetchRelatedFutures: jest.fn(),
  formatProbability: (p: number | null) =>
    p === null || p === undefined ? "--" : `${Math.round(p * 100)}%`,
}));

import RelatedFutures from "@/components/RelatedFutures";

const FIXTURE = "Club Necaxa vs. CF América";
const DRAW = `Draw (${FIXTURE})`;

/**
 * The market these rows arrive on.
 *
 * It used to be `FIXTURE` itself — and the note further down says why that mattered: the
 * section only reaches markets that name the event's own teams, so an outcome has to be
 * carried onto one of this event's markets or it renders nothing and the arm asserts over
 * an empty page.
 *
 * #4646 (ux/1349) took the BARE matchup away as a carrier. A market whose name is exactly
 * this event's two sides IS the event's own moneyline, the hero has already answered it,
 * and the rail now drops it — so every case below would have rendered zero tiles and this
 * file would have gone red for a reason that has nothing to do with #6372.
 *
 * The carrier is therefore the qualified spelling this file already uses one arm down, and
 * which #4646 deliberately keeps. NOTHING about what is being read changed: the outcome
 * strings, the grouping (no colon, so one `other` group, exactly as before) and every
 * assertion are untouched.
 */
const CARRIER = `${FIXTURE} - Halftime Result`;

function prop(
  marketName: string,
  outcomeName: string,
  probability: number,
  outcomeId: number,
) {
  return {
    market_id: 900 + outcomeId,
    outcome_id: outcomeId,
    market_name: marketName,
    outcome_name: outcomeName,
    clean_label: marketName,
    probability,
    display_category: "game_prop",
    market_tier: 5,
    source: "kalshi",
    all_sources: ["kalshi"],
    relevance_score: 1,
    resolution_date: null,
    probability_change_24h: null,
    rank: null,
    matched_player: null,
  };
}

function setPayload(futures: Array<ReturnType<typeof prop>>) {
  payload = {
    event_id: 15312629,
    home_team: "Club Necaxa",
    away_team: "CF América",
    home_team_futures: [],
    away_team_futures: futures,
    series_markets: [],
    total_count: futures.length,
    event_status: "scheduled",
    box_score: null,
  };
}

function render(): string {
  return renderToStaticMarkup(
    <RelatedFutures
      eventId={15312629}
      homeTeam="Club Necaxa"
      awayTeam="CF América"
      sportKey="soccer_mexico_ligamx"
    />,
  );
}

/** The text of every prop-tile label, in document order. */
function tileLabels(html: string): string[] {
  return Array.from(
    html.matchAll(
      /class="text-\[11px\] font-semibold text-text-primary truncate leading-tight"[^>]*>([^<]*)</g,
    ),
  ).map((m) => m[1]);
}

/**
 * How many tiles carry a face. The headshot's own wrapper is counted rather
 * than any image tag, because `PlayerHeadshot` renders three different things
 * (a roster URL, an ESPN id, or the initials fallback that produced "D(") and
 * the defect was the LAST of them — an assertion on `<img` would have been
 * green on the very case that was filed.
 */
function headshotCount(html: string): number {
  return html.split('class="flex justify-center mb-1.5"').length - 1;
}

describe("#6372 — the draw tile keeps its name and loses its face", () => {
  it("draws no headshot for an outcome that is a question, not a person", () => {
    setPayload([prop(CARRIER, DRAW, 0.27, 1)]);
    const html = render();

    // Not vacuous: the tile has to exist for its missing face to mean anything.
    expect(tileLabels(html)).toHaveLength(1);

    expect(headshotCount(html)).toBe(0);
    // The initials the reader actually met.
    expect(html).not.toContain(">D(<");
  });

  it("and still says what it is — the face goes, the name stays", () => {
    setPayload([prop(CARRIER, DRAW, 0.27, 1)]);
    const html = render();

    // THE half a face-only assertion misses: `tileLabels` fell through to an
    // em-dash once `playerName` went null, which would have traded a wrong
    // avatar for a nameless tile.
    const [label] = tileLabels(html);
    expect(label).not.toBe("—");
    expect(label.length).toBeGreaterThan(0);
    expect(DRAW.startsWith(label.replace(/…$/, ""))).toBe(true);

    // And the full text stays recoverable in the `title`, as it was before.
    expect(html).toContain(`title="${DRAW}"`);
  });

  it("nor for a team carrying a handicap or a state — the bulk of the population", () => {
    // A MUTANT FOUND THIS GAP: dropping the bracket rule entirely killed no
    // test, because the filed specimen is also caught by the fixture rule
    // ("… vs. …"). These two shapes are what the bracket rule is actually for,
    // and they are the majority of it — read on production 2026-09-16 over
    // every outcome on an event-attached market with no colon and no leading
    // Over/Under: `CA Osasuna (-1.5)`, `AC Milan (-2.5)`, `St. Thomas (MN)`,
    // `Miami (OH)`. Not one person in that population; all of them were being
    // handed a footballer's face.
    setPayload([
      prop("Handicap", "CA Osasuna (-1.5)", 0.44, 4),
      prop("Handicap", "St. Thomas (MN)", 0.31, 5),
    ]);
    const html = render();

    expect(tileLabels(html)).toHaveLength(2);
    expect(headshotCount(html)).toBe(0);
    // Still named, same as the draw.
    expect(html).toContain('title="CA Osasuna (-1.5)"');
    expect(html).toContain('title="St. Thomas (MN)"');
  });

  it("nor for a bare result word, nor for a whole fixture", () => {
    // TWO MORE MUTANT SURVIVORS, and the same lesson as the bracket rule: each
    // of the three rules needs a specimen only IT catches, or a later reader
    // deletes it as dead. Both populations read on production 2026-09-16, same
    // query as above (`truncated: true` — these are samples, not counts):
    //
    //   bare result   `Draw` on "CA Newell's Old Boys vs. CD Riestra -
    //                 Halftime Result"; `Tie` on "Mjallby vs AIK"
    //   whole fixture `San Francisco Giants vs. Los Angeles Dodgers` (the
    //                 outcome IS the market name), and the sharpest of them,
    //                 `Gable Steveson vs. Sean Sharaf` — TWO people wearing
    //                 one face, its initials taken from the first of them
    //
    // Both are carried onto THIS payload's fixture rather than pasted verbatim:
    // the section only reaches markets that name the event's own teams, so a
    // verbatim Mjallby row renders nothing at all and the arm would pass while
    // asserting over an empty page.
    //
    // One render each, because two markets fall into two stat groups and only
    // the first draws — an accident of grouping that reads as this rule failing.
    setPayload([prop(CARRIER, "Draw", 0.22, 6)]);
    const bare = render();
    expect(tileLabels(bare)).toHaveLength(1);
    expect(headshotCount(bare)).toBe(0);
    expect(bare).toContain('title="Draw"');

    setPayload([prop(CARRIER, FIXTURE, 0.5, 7)]);
    const fixture = render();
    expect(tileLabels(fixture)).toHaveLength(1);
    expect(headshotCount(fixture)).toBe(0);
    expect(fixture).toContain(`title="${FIXTURE}"`);
  });

  it("control: an ordinary player name still gets a face", () => {
    // Gotcha #43, and the arm that fails a fix which simply stops drawing
    // headshots. `Anytime Goalscorer` outcomes are bare names — the same third
    // branch of the parser, and the population that must not move.
    setPayload([
      prop("Anytime Goalscorer", "Erling Haaland", 0.42, 2),
      prop("Anytime Goalscorer", "Kylian Mbappé", 0.38, 3),
    ]);
    const html = render();

    expect(tileLabels(html)).toHaveLength(2);
    expect(headshotCount(html)).toBe(2);
  });

  it("control: a mixed group draws exactly one face, on the person", () => {
    // The two populations in one render, which is the only arm that catches a
    // fix keyed on "how many rows are in this group" rather than on the row.
    setPayload([
      prop(CARRIER, DRAW, 0.27, 1),
      prop(CARRIER, "Erling Haaland", 0.42, 2),
    ]);
    const html = render();

    expect(tileLabels(html)).toHaveLength(2);
    expect(headshotCount(html)).toBe(1);
  });
});
