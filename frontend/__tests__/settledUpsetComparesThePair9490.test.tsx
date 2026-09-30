/**
 * #9490 — the settled hero calls a win an "Upset" only when the winner was
 * priced BELOW the side it beat, on the pair the hero prints.
 *
 * The filed specimen, production 2026-09-28: `/events/15304745`, Turkey 1–4
 * Italy (Nations League). Served `prematch_odds` (Kalshi) Turkey 0.325 / Italy
 * 0.395, rendered 33 / 40, the draw taking the rest. The hero read "Italy WON ·
 * Upset · 40% pregame" — the favourite's win, in amber — because the rule was a
 * fixed `winner < 0.40` cut that never looked at the loser. The number it
 * printed (40) did not even meet its own threshold.
 *
 * Every specimen below goes through `settledPregameMark` and into the hero, the
 * page's own path, so a rule that is right in the helper but dropped on the way
 * to the component still fails here.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import SettledOutcomeHero, { pregameUpset } from "@/components/event/SettledOutcomeHero";
import type { SettledOutcome } from "@/lib/eventOutcome";
import { settledPregameMark } from "@/lib/settledPregameMark";

type Prematch = Parameters<typeof settledPregameMark>[0]["prematchOdds"];

function outcome(winnerName: string, winnerSide: "home" | "away"): SettledOutcome {
  return {
    winnerName,
    winnerSide,
    authority: "score",
    resultLine: null,
    resultKind: "score",
    resultExplanation: null,
  } as unknown as SettledOutcome;
}

/** Page path: the mark from the served pair, then the hero with its fields. */
function hero(args: {
  winnerName: string;
  winnerSide: "home" | "away";
  prematch: Prematch;
  sport: string;
}): string {
  const mark = settledPregameMark({
    winnerSide: args.winnerSide,
    prematchOdds: args.prematch,
    openingHomeProb: null,
    openingAwayProb: null,
    sport: args.sport,
  });
  return renderToStaticMarkup(
    <SettledOutcomeHero
      outcome={outcome(args.winnerName, args.winnerSide)}
      hasNumericScore
      winnerPregameProb={mark?.probability ?? null}
      winnerPregamePercent={mark?.percent ?? null}
      winnerPregameSource={mark?.source ?? null}
      winnerPregameLabel={mark?.label ?? null}
      loserPregameProb={mark?.loserProbability ?? null}
      loserPregamePercent={mark?.loserPercent ?? null}
    />,
  );
}

/**
 * The text of the pregame line alone — the one span this ship is about, so a
 * stray "Upset" or "40%" elsewhere cannot satisfy an assertion. The span holds
 * text nodes only; React's `<!-- -->` separators are removed as literals.
 */
function pregameLine(html: string): string {
  const at = html.indexOf('data-testid="event-hero-pregame"');
  if (at === -1) return "";
  const open = html.indexOf(">", at) + 1;
  const close = html.indexOf("</span>", open);
  return html.slice(open, close).split("<!-- -->").join("").split("&#x27;").join("'");
}

const SOCCER = "soccer_uefa_nations_league";

describe("#9490 — a three-way favourite's win is not an upset", () => {
  it("THE SPECIMEN 15304745: Italy 0.395 over Turkey 0.325 reads '40% pregame', no Upset", () => {
    const html = hero({
      winnerName: "Italy",
      winnerSide: "away",
      prematch: {
        home_probability: 0.325,
        away_probability: 0.395,
        home_rendered_percent: 33,
        away_rendered_percent: 40,
        source: "kalshi",
      },
      sport: SOCCER,
    });
    const line = pregameLine(html);
    expect(line).toBe("40% pregame");
    expect(line).not.toContain("Upset");
    expect(html).not.toContain("text-amber-600");
  });

  it("the second specimen 15317178: Montenegro 0.375 over Armenia 0.325, no Upset", () => {
    const line = pregameLine(
      hero({
        winnerName: "Montenegro",
        winnerSide: "away",
        prematch: {
          home_probability: 0.325,
          away_probability: 0.375,
          home_rendered_percent: 33,
          away_rendered_percent: 38,
          source: "kalshi",
        },
        sport: SOCCER,
      }),
    );
    expect(line).toBe("38% pregame");
  });

  it("A REAL THREE-WAY UPSET still reads Upset: away 0.335 over home 0.425", () => {
    const html = hero({
      winnerName: "Portugal",
      winnerSide: "away",
      prematch: {
        home_probability: 0.425,
        away_probability: 0.335,
        home_rendered_percent: 43,
        away_rendered_percent: 34,
        source: "kalshi",
      },
      sport: SOCCER,
    });
    expect(pregameLine(html)).toBe("Upset · 34% pregame");
    expect(html).toContain("text-amber-600");
  });

  it("a draw-priced home winner whose away leg is only `1 − home` is never called an upset", () => {
    // The away figure carries the draw, so it is no price for the loser.
    const line = pregameLine(
      hero({
        winnerName: "Turkey",
        winnerSide: "home",
        prematch: {
          home_probability: 0.45,
          away_probability: null,
          source: "kalshi",
        } as unknown as Prematch,
        sport: SOCCER,
      }),
    );
    expect(line).toBe("45% pregame");
  });
});

describe("#9490 — two-way sports are unchanged", () => {
  it("THE CONTROL: the Nationals at 39 over 61 still read Upset", () => {
    const html = hero({
      winnerName: "Nationals",
      winnerSide: "away",
      prematch: {
        home_probability: 0.61,
        away_probability: 0.39,
        home_rendered_percent: 61,
        away_rendered_percent: 39,
        source: "kalshi",
      },
      sport: "baseball_mlb",
    });
    expect(pregameLine(html)).toBe("Upset · 39% pregame");
  });

  it("a two-way favourite's win is not", () => {
    const line = pregameLine(
      hero({
        winnerName: "Tigers",
        winnerSide: "home",
        prematch: {
          home_probability: 0.61,
          away_probability: 0.39,
          home_rendered_percent: 61,
          away_rendered_percent: 39,
          source: "kalshi",
        },
        sport: "baseball_mlb",
      }),
    );
    expect(line).toBe("61% pregame");
  });
});

describe("#9490 — the label agrees with the number printed beside it", () => {
  it("compares the percents the pair renders, not the raw probabilities", () => {
    // 0.502 < 0.504, but both print 50: the reader sees no underdog.
    expect(
      pregameUpset({ winnerProb: 0.502, winnerPercent: 50, loserProb: 0.504, loserPercent: 50 }),
    ).toBe(false);
    // Without served percents it rounds both locally, the same way.
    expect(pregameUpset({ winnerProb: 0.502, loserProb: 0.504 })).toBe(false);
    expect(pregameUpset({ winnerProb: 0.44, loserProb: 0.56 })).toBe(true);
  });

  it("no loser number, no comparison, no label — however low the winner", () => {
    expect(pregameUpset({ winnerProb: 0.12, winnerPercent: 12 })).toBe(false);
    expect(pregameUpset({ winnerProb: null, loserProb: 0.5 })).toBe(false);
  });
});
