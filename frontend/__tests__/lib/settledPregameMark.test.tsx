/**
 * #8315 — the settled hero's pre-game mark is the number the game's card prints.
 *
 * Specimen, production 2026-09-24 00:00Z, Nationals @ Tigers (final, away won):
 *
 *   /api/feed            prematch_odds {home .61, away .39, away_rendered 39, kalshi}
 *   /api/events/15317535 opening_odds  {home .6007, away .3993}
 *
 * Card: "Washington Nationals won as a 39% underdog". Page: "Upset · 40% pregame".
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import SettledOutcomeHero from "@/components/event/SettledOutcomeHero";
import type { SettledOutcome } from "@/lib/eventOutcome";
import { settledPregameMark } from "@/lib/settledPregameMark";

const KALSHI = {
  home_probability: 0.61,
  away_probability: 0.39,
  home_rendered_percent: 61,
  away_rendered_percent: 39,
  source: "kalshi",
};

const OPENING = { openingHomeProb: 0.6007, openingAwayProb: 0.3993 };

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

describe("#8315 — which number the settled hero prints", () => {
  it("the specimen: the card's kalshi 39, not the books median's 40", () => {
    const mark = settledPregameMark({
      winnerSide: "away",
      prematchOdds: KALSHI,
      ...OPENING,
      sport: "baseball_mlb",
    });
    expect(mark).toEqual({
      probability: 0.39,
      percent: 39,
      source: "kalshi",
      label: null,
    });
  });

  it("follows the winner's side on the served pair", () => {
    const mark = settledPregameMark({
      winnerSide: "home",
      prematchOdds: KALSHI,
      ...OPENING,
      sport: "baseball_mlb",
    });
    expect(mark?.probability).toBe(0.61);
    expect(mark?.percent).toBe(61);
  });

  it("a books-rung reading carries the card's sportsbooks label", () => {
    const mark = settledPregameMark({
      winnerSide: "away",
      prematchOdds: {
        home_probability: 0.6007,
        away_probability: 0.3993,
        home_rendered_percent: 60,
        away_rendered_percent: 40,
        source: "books",
      },
      ...OPENING,
      sport: "baseball_mlb",
    });
    expect(mark).toMatchObject({ percent: 40, source: "books", label: "sportsbooks" });
  });

  it("falls back to opening_odds, labelled, only when prematch_odds is absent", () => {
    const mark = settledPregameMark({
      winnerSide: "away",
      prematchOdds: undefined,
      ...OPENING,
      sport: "baseball_mlb",
    });
    expect(mark).toEqual({
      probability: 0.3993,
      percent: null,
      source: "books",
      label: "sportsbooks",
    });
  });

  it("no resolved side, no mark — never credit the home number to the winner", () => {
    expect(
      settledPregameMark({
        winnerSide: null,
        prematchOdds: KALSHI,
        ...OPENING,
        sport: "baseball_mlb",
      }),
    ).toBeNull();
  });

  it("the opening fallback keeps its both-legs gate", () => {
    expect(
      settledPregameMark({
        winnerSide: "home",
        prematchOdds: undefined,
        openingHomeProb: 0.6,
        openingAwayProb: null,
        sport: "soccer_epl",
      }),
    ).toBeNull();
  });

  describe("draw-priced sports (#6238 / #6614 carried onto the served pair)", () => {
    it("withholds an away winner's mark when the served away is just 1 - home", () => {
      expect(
        settledPregameMark({
          winnerSide: "away",
          prematchOdds: {
            home_probability: 0.545,
            away_probability: 0.455,
            source: "books",
          },
          ...OPENING,
          sport: "soccer_epl",
        }),
      ).toBeNull();
    });

    it("and does NOT fall through to the books pair — that is a different rung", () => {
      // A real, non-complement opening pair is sitting right there; printing it
      // would put the books median beside a card that printed the venue.
      expect(
        settledPregameMark({
          winnerSide: "away",
          prematchOdds: { home_probability: 0.5, away_probability: 0.5, source: "kalshi" },
          openingHomeProb: 0.545,
          openingAwayProb: 0.21,
          sport: "soccer_epl",
        }),
      ).toBeNull();
    });

    it("keeps a three-way venue reading that carries its draw", () => {
      const mark = settledPregameMark({
        winnerSide: "away",
        prematchOdds: { home_probability: 0.495, away_probability: 0.245, source: "kalshi" },
        ...OPENING,
        sport: "soccer_epl",
      });
      expect(mark?.probability).toBe(0.245);
    });

    it("a home winner is never withheld", () => {
      const mark = settledPregameMark({
        winnerSide: "home",
        prematchOdds: { home_probability: 0.545, away_probability: 0.455, source: "books" },
        ...OPENING,
        sport: "soccer_epl",
      });
      expect(mark?.probability).toBe(0.545);
    });
  });
});

describe("#8315 — what the hero prints from it", () => {
  const NATS: SettledOutcome = {
    winnerName: "Nationals",
    winnerSide: "away",
    authority: "score",
    resultLine: null,
    resultKind: "score",
    resultExplanation: null,
  } as unknown as SettledOutcome;

  function hero(props: {
    prob: number | null;
    percent?: number | null;
    label?: string | null;
    source?: string | null;
  }): string {
    return renderToStaticMarkup(
      <SettledOutcomeHero
        outcome={NATS}
        hasNumericScore
        winnerPregameProb={props.prob}
        winnerPregamePercent={props.percent}
        winnerPregameLabel={props.label}
        winnerPregameSource={props.source}
      />,
    );
  }

  it("prints the card's rounded percent, not a local re-rounding", () => {
    // 0.395 rounds to 40 locally; the served pair (UX-P114) said 39.
    const text = visibleText(hero({ prob: 0.395, percent: 39, source: "kalshi" }));
    expect(text).toContain("Upset · 39% pregame");
    expect(text).not.toContain("40%");
    expect(text).not.toContain("sportsbooks");
  });

  it("names the sportsbooks rung the way the card does", () => {
    const html = hero({ prob: 0.3993, percent: 40, label: "sportsbooks", source: "books" });
    expect(visibleText(html)).toContain("Upset · 40% pregame sportsbooks");
    // Its own line, not a suffix on the pregame span (the 390px column).
    expect(html).toMatch(/data-testid="event-hero-pregame-label"[^>]*>sportsbooks</);
    expect(html).toContain('data-prematch-source="books"');
  });

  it("without a served percent it rounds the probability, as before", () => {
    expect(visibleText(hero({ prob: 0.3993 }))).toContain("40% pregame");
  });
});
