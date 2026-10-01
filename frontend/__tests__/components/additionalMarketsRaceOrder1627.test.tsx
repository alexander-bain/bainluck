/**
 * #1627 — on a game page, the Race-to-N cards in Additional Markets read as one
 * ladder, lowest score first.
 *
 * Seen at 390px on production 2026-10-01 ~09:50Z, Browns @ Steelers
 * (`/events/14780550`, TNF, pregame): Other Markets read `Tie`, `Race to 35`,
 * `Race to 21`, `Race to 14`, `Race to 10`, then `+12 more` — with `Race to 28
 * Points` twenty-odd markets later in the wire and so behind the disclosure.
 * The fixture is that event's `/game-markets` → `other`, verbatim (the same
 * capture #10039's guard uses).
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import SpecialEventMarkets from "@/components/SpecialEventMarkets";
import type { GameMarketsResponse } from "@/lib/api";
import {
  buildMarketSection,
  orderScoringRaces,
  scoringRaceTarget,
} from "@/lib/otherMarketGroups";
import fixture from "../fixtures/other_14780550_1627.json";

type Rows = GameMarketsResponse["other"];
const HOME = fixture.home_team; // Cleveland Browns
const AWAY = fixture.away_team; // Pittsburgh Steelers
const OTHER = fixture.other as Rows;

/** Every card heading the section prints, in page order (shown, then disclosed). */
function headings(html: string): string[] {
  return Array.from(html.matchAll(/<div class="font-medium text-sm">([^<]*)<\/div>/g), (m) =>
    m[1].replace(/&amp;/g, "&"),
  );
}

function render(other: Rows): string {
  const data = { other, home_team: HOME, away_team: AWAY } as GameMarketsResponse;
  return renderToStaticMarkup(<SpecialEventMarkets data={data} eventStatus="scheduled" />);
}

function row(market: string, outcome: string, id: number): Rows[number] {
  return {
    market_name: market,
    outcome_name: outcome,
    probability: 0.4,
    source: "kalshi",
    is_winner: null,
    resolution_source: null,
    _market_id: id,
  };
}

describe("#1627 Browns @ Steelers: the races read 10, 14, 21, 28, 35", () => {
  const races = headings(render(OTHER)).filter((h) => /^Race to/.test(h));

  it("every race is on the page, lowest score first", () => {
    expect(races).toEqual([
      "Race to 10 Points",
      "Race to 14 Points",
      "Race to 21 Points",
      "Race to 28 Points",
      "Race to 35 Points",
    ]);
  });

  it("the ladder sits together at the first race's slot, ahead of the cards the wire sent after it", () => {
    const section = buildMarketSection(OTHER, { homeTeam: HOME, awayTeam: AWAY });
    const other = section.categories.find((c) => c.cards.some((k) => /Race to/.test(k.name)));
    const names = (other?.cards ?? []).map((c) => c.title ?? c.name);
    // In this capture the first race is the category's first card (the wire
    // sent Tie later at 08:20Z; by 09:50Z it led, and the ladder follows it).
    expect(names.slice(0, 6)).toEqual([
      "Race to 10 Points",
      "Race to 14 Points",
      "Race to 21 Points",
      "Race to 28 Points",
      "Race to 35 Points",
      "Safety?",
    ]);
  });

  it("order only: same cards, same rows, nothing withheld", () => {
    const cards = buildMarketSection(OTHER, { homeTeam: HOME, awayTeam: AWAY }).categories.flatMap(
      (c) => c.cards,
    );
    const r28 = cards.find((c) => c.name === "Pittsburgh vs Cleveland: Race to 28 Points");
    expect(r28?.outcomes.map((o) => o.label).sort()).toEqual([
      "Cleveland",
      "Neither team",
      "Pittsburgh",
    ]);
    expect(cards.filter((c) => /Race to/.test(c.name)).every((c) => c.withheld === 0)).toBe(true);
  });
});

describe("#1627 race ordering — controls", () => {
  it("reads the target off the same pattern that says it is a race", () => {
    expect(scoringRaceTarget("Pittsburgh vs Cleveland: Race to 21 Points")).toBe(21);
    expect(scoringRaceTarget("Race to 1 point")).toBe(1);
    expect(scoringRaceTarget("Race to 5 catches")).toBeNull();
    expect(scoringRaceTarget("Pittsburgh vs Cleveland: Safety")).toBeNull();
    expect(scoringRaceTarget(null)).toBeNull();
  });

  it("no races, or a single race, leaves the wire order alone", () => {
    const t = (s: string) => scoringRaceTarget(s);
    const none = ["Safety", "Tie", "1st Touchdown"];
    expect(orderScoringRaces(none, t)).toBe(none);
    const one = ["Safety", "X: Race to 35 Points", "Tie"];
    expect(orderScoringRaces(one, t)).toBe(one);
  });

  it("non-race cards keep their slots; equal targets keep wire order", () => {
    const t = (s: string) => scoringRaceTarget(s.replace(/#\d$/, ""));
    expect(
      orderScoringRaces(
        ["Tie", "A: Race to 21 Points#1", "Safety", "B: Race to 10 Points", "C: Race to 21 Points#2", "1st TD"],
        t,
      ),
    ).toEqual(["Tie", "B: Race to 10 Points", "A: Race to 21 Points#1", "C: Race to 21 Points#2", "Safety", "1st TD"]);
  });

  it("a two-race page sorts the pair and leaves the card before them first", () => {
    const rows: Rows = [
      row("Pittsburgh vs Cleveland: Safety", "Yes", 1),
      row("Pittsburgh vs Cleveland: Race to 21 Points", "Pittsburgh", 2),
      row("Pittsburgh vs Cleveland: Race to 10 Points", "Pittsburgh", 3),
    ];
    const cards = buildMarketSection(rows, { homeTeam: HOME, awayTeam: AWAY }).categories.flatMap(
      (c) => c.cards,
    );
    expect(cards.map((c) => c.title ?? c.name)).toEqual([
      "Safety",
      "Race to 10 Points",
      "Race to 21 Points",
    ]);
  });
});
