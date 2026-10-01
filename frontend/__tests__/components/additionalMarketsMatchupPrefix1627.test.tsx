/**
 * #1627 — on a game page, an Additional Markets card is headed by its question,
 * not by the venue's restatement of the game.
 *
 * Seen at 390px on production 2026-10-01 ~08:20Z, Browns @ Steelers
 * (`/events/14780550`, TNF, pregame): seventeen Kalshi cards headed
 * `Pittsburgh vs Cleveland: Race to 35 Points`, `… : Safety`, `… : 1st
 * Touchdown`, and Polymarket's `Steelers vs. Browns: Safety?`, one screen under
 * a hero that already names the game. The fixture is that event's
 * `/game-markets` → `other`, verbatim.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import SpecialEventMarkets from "@/components/SpecialEventMarkets";
import type { GameMarketsResponse } from "@/lib/api";
import { buildMarketSection, matchupPrefixedQuestion } from "@/lib/otherMarketGroups";
import fixture from "../fixtures/other_14780550_1627.json";

type Rows = GameMarketsResponse["other"];
const HOME = fixture.home_team; // Cleveland Browns
const AWAY = fixture.away_team; // Pittsburgh Steelers
const OTHER = fixture.other as Rows;

/** Every card heading the section prints, in page order. */
function headings(html: string): string[] {
  return Array.from(html.matchAll(/<div class="font-medium text-sm">([^<]*)<\/div>/g), (m) =>
    m[1].replace(/&amp;/g, "&"),
  );
}

function render(other: Rows, home = HOME, away = AWAY): string {
  const data = { other, home_team: home, away_team: away } as GameMarketsResponse;
  return renderToStaticMarkup(<SpecialEventMarkets data={data} eventStatus="scheduled" />);
}

describe("#1627 Browns @ Steelers: card headings drop the game's own matchup", () => {
  const html = render(OTHER);
  const shown = headings(html);

  it("no card heading restates the matchup", () => {
    expect(shown.length).toBeGreaterThan(10);
    for (const h of shown) {
      expect(h).not.toMatch(/^Pittsburgh vs Cleveland:/);
      expect(h).not.toMatch(/^Steelers vs\. Browns:/);
    }
  });

  it("the question survives as the heading", () => {
    expect(shown).toEqual(
      expect.arrayContaining([
        "Race to 35 Points",
        "Race to 10 Points",
        "Safety?",
        "Safety",
        "1st Touchdown",
        "1st Half / Fulltime Result",
      ]),
    );
  });

  it("display only: the same cards, keyed and filled exactly as the wire names them", () => {
    const section = buildMarketSection(OTHER, { homeTeam: HOME, awayTeam: AWAY });
    const cards = section.categories.flatMap((c) => c.cards);
    const race = cards.find((c) => c.name === "Pittsburgh vs Cleveland: Race to 35 Points");
    expect(race?.title).toBe("Race to 35 Points");
    expect(race?.outcomes.map((o) => o.label).sort()).toEqual(
      ["Cleveland", "Neither team", "Pittsburgh"],
    );
    // Two venues' safety questions stay two cards: no merge, no withholding.
    const safety = cards.filter((c) => /Safety/.test(c.name));
    expect(safety.map((c) => c.title).sort()).toEqual(["Safety", "Safety?"]);
    expect(safety.every((c) => c.withheld === 0)).toBe(true);
  });
});

describe("#1627 controls — headings the rule must leave alone", () => {
  it("a matchup that is not this game keeps the venue's whole string", () => {
    expect(matchupPrefixedQuestion("Chicago vs Detroit: Safety", HOME, AWAY)).toBeNull();
    const rows: Rows = [
      { market_name: "Chicago vs Detroit: Safety", outcome_name: "Safety", probability: 0.05, source: "kalshi", is_winner: null, resolution_source: null, _market_id: 1 },
    ];
    expect(headings(render(rows))).toEqual(["Chicago vs Detroit: Safety"]);
  });

  it("a side naming neither or both teams keeps the venue's string", () => {
    // `New York` is both teams on a Yankees–Mets page.
    expect(
      matchupPrefixedQuestion("New York vs Boston: Safety", "New York Mets", "New York Yankees"),
    ).toBeNull();
    // Both sides the same team is not this matchup.
    expect(matchupPrefixedQuestion("Pittsburgh vs Steelers: Tie", HOME, AWAY)).toBeNull();
    // One side this game's, the other not: still not this game.
    expect(matchupPrefixedQuestion("Pittsburgh vs Detroit: Safety", HOME, AWAY)).toBeNull();
    expect(matchupPrefixedQuestion("Chicago vs Cleveland: Safety", HOME, AWAY)).toBeNull();
  });

  it("a card already titled by its statistic keeps that title", () => {
    const rows: Rows = [
      { market_name: "Pittsburgh vs Cleveland: Player Props", outcome_name: "DK Metcalf: Receiving Yards O/U 40.5", probability: 0.56, source: "kalshi", is_winner: null, resolution_source: null, _market_id: 2 },
    ];
    const cards = buildMarketSection(rows, { homeTeam: HOME, awayTeam: AWAY }).categories.flatMap(
      (c) => c.cards,
    );
    expect(cards.map((c) => c.title ?? c.name)).toEqual(["Receiving Yards"]);
  });

  it("question-first, bare and empty-remainder names are untouched", () => {
    expect(matchupPrefixedQuestion("Set 1 Winner: Pittsburgh vs Cleveland", HOME, AWAY)).toBeNull();
    expect(matchupPrefixedQuestion("Pittsburgh vs Cleveland", HOME, AWAY)).toBeNull();
    expect(matchupPrefixedQuestion("Pittsburgh vs Cleveland:", HOME, AWAY)).toBeNull();
  });

  it("either venue's spelling and either order of the two teams is recognised", () => {
    expect(matchupPrefixedQuestion("Steelers vs. Browns: Safety?", HOME, AWAY)).toBe("Safety?");
    expect(matchupPrefixedQuestion("Cleveland vs Pittsburgh: Tie", HOME, AWAY)).toBe("Tie");
    expect(
      matchupPrefixedQuestion(
        "Boston vs New York Yankees: First Inning Run",
        "New York Yankees",
        "Boston Red Sox",
      ),
    ).toBe("First Inning Run");
  });

  it("without the event's team names nothing is rewritten", () => {
    expect(matchupPrefixedQuestion("Pittsburgh vs Cleveland: Safety", null, null)).toBeNull();
  });
});
