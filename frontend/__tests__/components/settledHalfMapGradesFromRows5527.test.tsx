/**
 * #5527 — A SETTLED HALF GOALS MAP GRADES FROM THE ROWS WHEN IT HAS NO HALF SCORE.
 *
 * Mystery-shopped on production at 390px, 2026-09-25 ~07:40Z (shopper pass
 * 0049), `/events/15194200`, Norway 3-2 Denmark, UEFA Nations League, FINAL:
 *
 *   1st half goals map   Two lines quoted   LAST QUOTE FOR GOING OVER
 *                        Over 0.5 100%   Over 3.5 0%
 *   2nd half goals map   Two lines quoted   LAST QUOTE FOR GOING OVER
 *                        Over 0.5 100%   Over 1.5 100%
 *
 * Every one of those rows was already graded on the payload the card reads
 * (`is_winner` on the Over leg, `resolution_source: "clean_resolution"`), and
 * the same page's Additional Markets printed `Halftime Result: Norway — Won`
 * off rows of that shape. The card graded ONLY against a half score derived
 * from ESPN's play history (#6169), and this match has none (`espn_history`
 * empty), so it could only ever quote.
 *
 * Two defects, one card:
 *   1. no row grade was consulted — the tense is wrong on both halves;
 *   2. team-only half totals (`"Norway vs. Denmark: Denmark 1st Half O/U 1.5"`)
 *      shared the game's pool, and at 1.5 and 2.5 their prices disagreed with
 *      the game's, so the collapse withheld both rungs — the 1H card showed two
 *      of the four lines it was served.
 *
 * The fixture is the served `period_markets` verbatim. Every arm renders the
 * REAL `MarketMapSection`, and each defect arm asserts the card is still there
 * by title, so "no LAST QUOTE" cannot pass on a card that vanished.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import {
  halfRungRowGrade,
  halfTotalPinnedByGrades,
  isTeamScopedHalfTotal,
  selectHalfTotalRungs,
  settledHalfTotalsFromGrades,
  type PeriodTotalRow,
} from "@/lib/marketMapUtils";
import specimen from "../fixtures/settledHalfMapNorwayDenmark5527.json";

const ROWS = specimen.period_markets as unknown as PeriodTotalRow[];

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;|&#39;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function renderSection(
  periodMarkets: PeriodTotalRow[],
  eventStatus: string = "completed",
  espnHistory?: Array<{ period: string; home_score: number; away_score: number }>
): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: specimen.event_id,
          home_team: specimen.home_team,
          away_team: specimen.away_team,
          home_score: specimen.home_score,
          away_score: specimen.away_score,
          status: eventStatus,
          player_props: [],
          team_totals: [],
          period_markets: periodMarkets,
          matchups: [],
          other: [],
          pace: null,
          props_script: [],
          spreads: [],
          totals: [],
        } as never
      }
      eventStatus={eventStatus}
      homeTeam={specimen.home_team}
      awayTeam={specimen.away_team}
      homeAbbr="NOR"
      awayAbbr="DEN"
      espnHistory={espnHistory as never}
      sportKey="soccer_uefa_nations_league"
    />
  );
}

/** The markup of one half's card: from its title to the next card's title. */
function card(html: string, half: "1H" | "2H"): string {
  const text = visibleText(html);
  const h1 = text.indexOf("1st half goals map");
  const h2 = text.indexOf("2nd half goals map");
  if (half === "1H") {
    expect(h1).toBeGreaterThanOrEqual(0);
    return text.slice(h1, h2 > h1 ? h2 : undefined);
  }
  expect(h2).toBeGreaterThanOrEqual(0);
  return text.slice(h2);
}

/** Rewrites every row's grade fields, leaving prices and names untouched. */
function regrade(
  rows: PeriodTotalRow[],
  patch: (row: PeriodTotalRow) => Partial<PeriodTotalRow>
): PeriodTotalRow[] {
  return rows.map((r) => ({ ...r, ...patch(r) }));
}

describe("#5527 the Norway 3-2 Denmark half cards, as served", () => {
  const html = renderSection(ROWS);

  it("grades the 1st half against the rows and names all four served lines", () => {
    const first = card(html, "1H");
    // The subtitle is the band's own (#3210): with the two rungs the team rows
    // had withheld restored, this ladder paints a shape. What it must not say
    // is that the lines were quoted.
    expect(first).toContain("Each line vs the final");
    expect(first).not.toMatch(/last quote/i);
    expect(first).not.toMatch(/lines quoted/i);
    // 3 goals in the half: 0.5 / 1.5 / 2.5 in, 3.5 not.
    expect(first).toMatch(/Over 0\.5 cleared Over 1\.5 cleared Over 2\.5 cleared Over 3\.5 not cleared/);
    expect(first).not.toMatch(/\d+%/);
  });

  it("draws the half's total where the grades pin it — 2.5 in, 3.5 out is 3", () => {
    const first = card(html, "1H");
    expect(first).toMatch(/Final 3 goals/i);
    expect(first).not.toMatch(/Pre-game/i);
  });

  it("grades the 2nd half against the final minus the pinned 1st half — 5 − 3 = 2", () => {
    // The 2H rows alone pin nothing (0.5 and 1.5 both in: "at least 2"). The
    // game's 5 less the 1H's 3 does, and those rows agree with it.
    const second = card(html, "2H");
    expect(second).toContain("Two lines settled");
    expect(second).toContain("Each line vs the final");
    expect(second).not.toMatch(/last quote/i);
    expect(second).toMatch(/Over 0\.5 cleared Over 1\.5 cleared/);
    expect(second).toMatch(/Final 2 goals/i);
  });

  it("the before-state: the same payload without the fix's two inputs is the screenshot", () => {
    // Strip the grades and put the team rows back in play the way the old
    // selector saw them: the card quotes, over two rungs, exactly as shot.
    const ungraded = regrade(ROWS, () => ({ is_winner: null }));
    const first = card(renderSection(ungraded), "1H");
    expect(first).toMatch(/last quote for going over/i);
    expect(first).toMatch(/\d+%/);
  });
});

describe("#5527 the grade comes only from rows the shared rule would crown", () => {
  it("a SERVED null source abstains (#4788) — the card keeps quoting", () => {
    const html = renderSection(regrade(ROWS, () => ({ resolution_source: null })));
    expect(card(html, "1H")).toMatch(/last quote for going over/i);
    expect(card(html, "2H")).toMatch(/last quote for going over/i);
  });

  it("the retraction abstains — `ungradeable_result` is not a grade", () => {
    const html = renderSection(
      regrade(ROWS, () => ({ resolution_source: "ungradeable_result" }))
    );
    expect(card(html, "1H")).toMatch(/last quote for going over/i);
  });

  it("an unfinished game is untouched: no settled heading on a live card", () => {
    const html = renderSection(ROWS, "live");
    expect(html).not.toMatch(/Each line vs the final/);
    expect(html).not.toMatch(/lines settled/);
  });

  it("grades that contradict across the ladder are withheld from every rung", () => {
    // Over 1.5 called missed while Over 2.5 is called cleared: impossible.
    const contradicted = regrade(ROWS, (r) =>
      r.threshold === 1.5 && r.outcome_name === "Over" && r.market_name.endsWith(": 1st Half O/U 1.5")
        ? { is_winner: false }
        : {}
    );
    const first = card(renderSection(contradicted), "1H");
    expect(first).toMatch(/last quote for going over/i);
    expect(first).not.toMatch(/Final \d/i);
  });

  it("#6169's production shape — every Over row crowned — pins nothing and quotes", () => {
    // `/events/14637256` served eight 2H rows all `is_winner: true`, including a
    // rung the half never reached. A ladder that cleared everything states no
    // number, so the card has nothing to grade against.
    const crowned = regrade(ROWS, (r) => (r.outcome_name === "Over" ? { is_winner: true } : {}));
    const html = renderSection(crowned);
    expect(card(html, "1H")).toMatch(/last quote for going over/i);
    expect(card(html, "2H")).toMatch(/last quote for going over/i);
    expect(html).not.toMatch(/Final \d/i);
  });

  it("a pinned half that the game's final contradicts draws nothing", () => {
    // Same rows, a final of 2: a 3-goal 1st half cannot fit inside it.
    const html = renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={{ ...specimen, home_score: 1, away_score: 1, player_props: [], team_totals: [], matchups: [], other: [], pace: null, props_script: [], spreads: [], totals: [] } as never}
        eventStatus="completed"
        homeTeam={specimen.home_team}
        awayTeam={specimen.away_team}
        sportKey="soccer_uefa_nations_league"
      />
    );
    expect(card(html, "1H")).toMatch(/last quote for going over/i);
    expect(html).not.toMatch(/Final \d/i);
  });

  it("the half SCORE still wins where ESPN has one (#6169 unchanged)", () => {
    // A halftime entry of 1-0 says one goal: 0.5 in, 1.5 / 2.5 / 3.5 out —
    // against rows that say three. The score decides, as it did before.
    const html = renderSection(ROWS, "completed", [
      { period: "Halftime", home_score: 1, away_score: 0 },
    ]);
    const first = card(html, "1H");
    expect(first).toMatch(/Over 0\.5 cleared Over 1\.5 not cleared Over 2\.5 not cleared Over 3\.5 not cleared/);
    expect(first).toMatch(/Final 1 goal/i);
  });
});

describe("#5527 team-only half totals stay out of the game's ladder", () => {
  it.each([
    ["Norway vs. Denmark: Denmark 1st Half O/U 1.5", true],
    ["Norway vs. Denmark: Norway 2nd Half O/U 0.5", true],
    ["Norway vs. Denmark: 1st Half O/U 1.5", false],
    ["Norway vs. Denmark: 2nd Half O/U 0.5", false],
    ["Stade Rennais vs Marseille: First Half Total", false],
    ["First Half Total Goals", false],
    ["", false],
  ])("%s → %s", (name, expected) => {
    expect(isTeamScopedHalfTotal(name)).toBe(expected);
  });

  it("the selector keeps the four game rungs of the 1st half, not two", () => {
    expect(selectHalfTotalRungs(ROWS, "1H", "completed").map((r) => r.threshold)).toEqual([
      0.5, 1.5, 2.5, 3.5,
    ]);
    expect(selectHalfTotalRungs(ROWS, "1H", "completed").map((r) => r.rowGrade)).toEqual([
      "cleared", "cleared", "cleared", "missed",
    ]);
  });

  it("without an event status no rung carries a grade", () => {
    expect(selectHalfTotalRungs(ROWS, "1H").every((r) => r.rowGrade === undefined)).toBe(true);
  });
});

describe("#5527 settledHalfTotalsFromGrades", () => {
  const r = (threshold: number, is_winner: boolean, period: "1H" | "2H") =>
    ({ market_name: `A vs. B: ${period === "1H" ? "1st" : "2nd"} Half O/U ${threshold}`, outcome_name: "Over", threshold, probability: null, market_type: "half_total", over_probability: is_winner ? 0.99 : 0.01, period, is_winner, resolution_source: "clean_resolution" }) as PeriodTotalRow;

  it("reads the specimen as 3 and 2", () => {
    expect(settledHalfTotalsFromGrades(ROWS, "completed", 5)).toEqual({ "1H": 3, "2H": 2 });
  });
  it("needs a finished game and a final", () => {
    expect(settledHalfTotalsFromGrades(ROWS, "live", 5)).toEqual({ "1H": null, "2H": null });
    expect(settledHalfTotalsFromGrades(ROWS, "completed", null)).toEqual({ "1H": null, "2H": null });
  });
  it("two pins must sum to the final", () => {
    const rows = [r(0.5, true, "1H"), r(1.5, false, "1H"), r(0.5, false, "2H"), r(1.5, false, "2H")];
    expect(settledHalfTotalsFromGrades(rows, "completed", 1)).toEqual({ "1H": 1, "2H": 0 });
    expect(settledHalfTotalsFromGrades(rows, "completed", 2)).toEqual({ "1H": null, "2H": null });
  });
  it("the derived half counts only where its own graded rungs agree", () => {
    const rows = [r(0.5, true, "1H"), r(1.5, false, "1H"), r(0.5, true, "2H"), r(1.5, true, "2H")];
    // final 2 ⇒ 2H = 1, but the 2H rows say Over 1.5 went in.
    expect(settledHalfTotalsFromGrades(rows, "completed", 2)).toEqual({ "1H": 1, "2H": null });
    expect(settledHalfTotalsFromGrades(rows, "completed", 3)).toEqual({ "1H": 1, "2H": 2 });
  });
});

describe("#5527 the two pure helpers", () => {
  const over = (is_winner: boolean | null, resolution_source: string | null = "clean_resolution") =>
    ({ market_name: "A vs. B: 1st Half O/U 1.5", outcome_name: "Over", threshold: 1.5, probability: null, market_type: "half_total", is_winner, resolution_source }) as PeriodTotalRow;
  const under = (is_winner: boolean | null) =>
    ({ ...over(is_winner), outcome_name: "Under" }) as PeriodTotalRow;

  it("an Under leg votes the other way; abstainers do not vote; disagreement is no verdict", () => {
    expect(halfRungRowGrade([over(true), under(null)], true)).toBe("cleared");
    expect(halfRungRowGrade([under(true)], true)).toBe("missed");
    expect(halfRungRowGrade([over(true), under(true)], true)).toBeUndefined();
    expect(halfRungRowGrade([over(null)], true)).toBeUndefined();
    expect(halfRungRowGrade([{ ...over(true), outcome_name: "Yes" } as PeriodTotalRow], true)).toBeUndefined();
  });

  it("pins a total only between adjacent rungs one unit apart", () => {
    const r = (threshold: number, rowGrade: "cleared" | "missed") => ({ threshold, rowGrade });
    expect(halfTotalPinnedByGrades([r(0.5, "cleared"), r(1.5, "missed")])).toBe(1);
    expect(halfTotalPinnedByGrades([r(0.5, "cleared"), r(2.5, "missed")])).toBeNull();
    expect(halfTotalPinnedByGrades([r(0.5, "cleared"), r(1.5, "cleared")])).toBeNull();
    // Over 0.5 not cleared is a goalless half — Rennes 1-0 Marseille's 1H,
    // this issue's first specimen.
    expect(halfTotalPinnedByGrades([r(0.5, "missed"), r(1.5, "missed")])).toBe(0);
    expect(halfTotalPinnedByGrades([r(1.5, "missed"), r(2.5, "missed")])).toBeNull();
    expect(halfTotalPinnedByGrades([{ threshold: 0.5 }, r(1.5, "missed")])).toBeNull();
  });
});
