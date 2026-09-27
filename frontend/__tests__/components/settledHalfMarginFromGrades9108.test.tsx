/**
 * #9108 — A SETTLED HALF MARGIN MAP DRAWS ITS RESULT FROM THE ROWS' GRADES
 * WHEN IT HAS NO HALFTIME ROW.
 *
 * Mystery-shopped on production at 390px, 2026-09-27 ~09:30Z (shopper pass
 * 0081), `/events/15315795`, Cruz Azul 3-3 Toluca, Liga MX, FINAL:
 *
 *   1st half margin   1st half margin distribution   (a blue block, nothing else)
 *   2nd half margin   2nd half margin distribution   (a blue block, nothing else)
 *   1st half goals    FINAL 2 goals
 *   2nd half goals    FINAL 4 goals
 *
 * The margin card's FINAL marker and its grades (#6203) were gated on a half
 * score derived ONLY from an ESPN halftime row, and this match has no ESPN
 * history. The goals cards had #5527's grade fallback; the margin cards had
 * none, so one page called the halves over in one card and unplayed in the next.
 *
 * The fixture is the served `period_markets` verbatim. Every render arm asserts
 * the card is still there by title, so "no Final" cannot pass on a card that
 * vanished.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { settledHalfScoresFromGrades, type PeriodTotalRow } from "@/lib/marketMapUtils";
import specimen from "../fixtures/settledHalfMarginCruzAzulToluca9108.json";

const ROWS = specimen.period_markets as unknown as PeriodTotalRow[];
const HOME = specimen.home_team;
const AWAY = specimen.away_team;

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
          home_team: HOME,
          away_team: AWAY,
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
      homeTeam={HOME}
      awayTeam={AWAY}
      homeAbbr="AZU"
      awayAbbr="TOL"
      espnHistory={espnHistory as never}
      sportKey="soccer_mexico_ligamx"
    />
  );
}

/** One card's text: from its title to the next card title that follows it. */
function card(html: string, title: string, next: string): string {
  const text = visibleText(html);
  const at = text.indexOf(title);
  expect(at).toBeGreaterThanOrEqual(0);
  const end = text.indexOf(next, at + title.length);
  return text.slice(at, end > at ? end : undefined);
}
const firstHalf = (html: string) => card(html, "1st half margin", "2nd half margin");
const secondHalf = (html: string) => card(html, "2nd half margin", "goals map");

/** Rewrites grade fields on the rows `pick` selects, leaving the rest untouched. */
function regrade(
  pick: (row: PeriodTotalRow) => boolean,
  patch: Partial<PeriodTotalRow>
): PeriodTotalRow[] {
  return ROWS.map((r) => (pick(r) ? { ...r, ...patch } : r));
}

const scores = (rows: PeriodTotalRow[], status = "completed") =>
  settledHalfScoresFromGrades(rows, status, specimen.home_score, specimen.away_score, HOME, AWAY, "goals");

describe("#9108 the Cruz Azul 3-3 Toluca half margin cards, as served", () => {
  const html = renderSection(ROWS);

  it("the fixture is the specimen: completed 3-3, graded half rows", () => {
    expect(specimen.status).toBe("completed");
    expect([specimen.home_score, specimen.away_score]).toEqual([3, 3]);
    expect(ROWS.filter((r) => r.market_type === "half_spread" && r.is_winner === true)).toHaveLength(2);
  });

  it("draws the 1st half's result — Cruz Azul by 2 — and grades its lines", () => {
    const first = firstHalf(html);
    expect(first).toMatch(/Final AZU by 2\b/);
    expect(first).toMatch(/AZU by 1\.5\+ cleared/);
    expect(first).toMatch(/TOL by 1\.5\+ not cleared/);
    expect(first).not.toMatch(/\d+%/);
  });

  it("draws the 2nd half's result — Toluca by 2 — and grades its lines", () => {
    const second = secondHalf(html);
    expect(second).toMatch(/Final TOL by 2\b/);
    expect(second).toMatch(/TOL by 1\.5\+ cleared/);
    expect(second).toMatch(/AZU by 1\.5\+ not cleared/);
    expect(second).not.toMatch(/\d+%/);
  });

  it("agrees with the goals cards below it: 2-0 is 2 goals, 1-3 is 4", () => {
    const text = visibleText(html);
    expect(text).toMatch(/1st half goals map.*Final 2 goals/i);
    expect(text).toMatch(/2nd half goals map.*Final 4 goals/i);
  });

  it("the pure helper returns the one split the grades allow", () => {
    expect(scores(ROWS)).toEqual({ h1Home: 2, h1Away: 0, h2Home: 1, h2Away: 3 });
  });
});

describe("#9108 controls: the grades must decide it, and agree", () => {
  it("contradicting grades draw no result (#6169's all-true rows)", () => {
    // Both sides "won the 1H by more than 1.5" — no split of 3-3 allows it.
    const rows = regrade((r) => r.market_type === "half_spread" && r.period === "1H", {
      is_winner: true,
    });
    expect(scores(rows)).toBeNull();
    const first = firstHalf(renderSection(rows));
    expect(first).not.toMatch(/Final/);
  });

  it("grades that leave two splits open draw no result", () => {
    // Without the margin and winner rows, a 2-goal 1st half could be 2-0, 1-1
    // or 0-2, and nothing else on the page separates them.
    const rows = ROWS.filter((r) => r.market_type === "half_total");
    expect(scores(rows)).toBeNull();
  });

  it("a served null source abstains, so a half with only such rows decides nothing", () => {
    const rows = regrade((r) => r.market_type !== "half_total", { resolution_source: null });
    expect(scores(rows)).toBeNull();
  });

  it("an integer line abstains — a push, where > and >= disagree", () => {
    const totals = ROWS.filter((r) => r.market_type === "half_total");
    const line = (n: string): PeriodTotalRow => ({
      market_name: "Cruz Azul vs Toluca: First Half Spread",
      outcome_name: `Cruz Azul wins the 1H by more than ${n} goals`,
      threshold: 1,
      probability: null,
      market_type: "half_spread",
      period: "1H",
      is_winner: true,
      resolution_source: "api_settlement",
    });
    // Counted, "by more than 1" won would leave only 2-0 — so the null below
    // is the integer rule, not a ladder too thin to decide.
    expect(scores([...totals, line("1.5")])).toEqual({ h1Home: 2, h1Away: 0, h2Home: 1, h2Away: 3 });
    expect(scores([...totals, line("1")])).toBeNull();
  });

  it("the ESPN halftime row wins wherever it exists", () => {
    const html = renderSection(ROWS, "completed", [
      { period: "Halftime", home_score: 1, away_score: 0 },
    ]);
    expect(firstHalf(html)).toMatch(/Final AZU by 1\b/);
    expect(firstHalf(html)).not.toMatch(/Final AZU by 2\b/);
  });

  it("a game that is not final draws nothing from grades", () => {
    expect(scores(ROWS, "in_progress")).toBeNull();
    expect(scores(ROWS, "scheduled")).toBeNull();
  });
});
