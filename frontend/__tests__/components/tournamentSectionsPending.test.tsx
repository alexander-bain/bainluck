/**
 * latency/135 — "still coming" and "not there" are different sentences.
 *
 * The hub's payload now arrives in two requests. For the second or so between them the two sections
 * `rest` carries have no data, and both of their existing empty states say something a reader would
 * read as a fact about the tournament rather than about the network:
 *
 *   Bracket tab   "Who gets how far fills in here once the draw is made."
 *                 The draw was made on 2026-08-27. This sentence would tell a reader, mid-tournament,
 *                 that the tournament had not started — the exact class of defect UX-P145 fixed when
 *                 a hard-coded weekday went stale the afternoon it shipped.
 *   Finished      "Results are not loaded."  True, and reads as a fault.
 *
 * Every assertion here reads the RENDERED markup (the plant rule): a guard over the props would stay
 * green the day a component stops printing the state it was given.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentBracket from "@/components/tournament/TournamentBracket";
import TournamentResults from "@/components/tournament/TournamentResults";
import type { PlayoffGrid as GridModel } from "@/lib/playoffGrid";

const DRAW_SENTENCE = "fills in here once the draw is made";

function gridWithOneRow(): GridModel {
  return {
    draw: "mens-singles",
    label: "Men's Singles",
    columns: [{ name: "title", label: "Title" }],
    rows: [
      {
        entityKey: "carlos-alcaraz",
        displayName: "Carlos Alcaraz",
        seed: 1,
        image: null,
        rank: 1,
        onBoard: true,
        cells: {
          title: {
            state: "live",
            probability: 0.435,
            probability_is_live: true,
            sources: [{ source: "kalshi", probability: 0.435 }],
          },
        },
      },
    ],
    counts: {},
    totalCells: 1,
    pricedCells: 1,
    noMarketCells: 0,
    alarmCells: 0,
    columnSums: [],
    monotonicityViolations: [],
  } as unknown as GridModel;
}

describe("the Bracket tab while the grid is still in flight", () => {
  it("says it is loading, and does NOT say the draw has not happened", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket grid={null} pending drawReleased mainDrawLabel="Sunday 30 August" />
    );
    expect(html).toContain("bracket-pending");
    expect(html).not.toContain("bracket-unreleased");
    expect(html).not.toContain(DRAW_SENTENCE);
  });

  it("CONTROL — with the request finished and no grid, the old empty is unchanged", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket grid={null} pending={false} drawReleased={false} />
    );
    expect(html).toContain("bracket-unreleased");
    expect(html).toContain(DRAW_SENTENCE);
    expect(html).not.toContain("bracket-pending");
  });

  it("a grid that HAS arrived is never hidden by a stale pending flag", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket grid={gridWithOneRow()} pending drawReleased />
    );
    expect(html).toContain("Carlos Alcaraz");
    expect(html).not.toContain("bracket-pending");
  });

  it("pending defaults to false, so no other caller is changed by this prop", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket grid={null} drawReleased={false} />
    );
    expect(html).toContain("bracket-unreleased");
  });
});

describe("the finished list while its half is still in flight", () => {
  it("says it is loading rather than that results are not loaded", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={undefined} pending draw="mens-singles" />
    );
    expect(html).toContain("Loading finished matches");
    expect(html).not.toContain("Results are not loaded");
  });

  it("CONTROL — with the request finished and nothing there, the old sentence stands", () => {
    const html = renderToStaticMarkup(
      <TournamentResults results={undefined} pending={false} draw="mens-singles" />
    );
    expect(html).toContain("Results are not loaded");
    expect(html).not.toContain("Loading finished matches");
  });

  it("a results payload that HAS arrived is never described as loading", () => {
    const html = renderToStaticMarkup(
      <TournamentResults
        results={
          {
            matches: [],
            count: 0,
            source_errors: [],
            source_competitions: 0,
            unregistered_pairs: 0,
          } as never
        }
        pending
        draw="mens-singles"
      />
    );
    expect(html).not.toContain("Loading finished matches");
  });
});
