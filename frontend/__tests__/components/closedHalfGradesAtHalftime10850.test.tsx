/**
 * #10850 — AT HALFTIME THE 1ST HALF CARDS SHOW HOW THE HALF FINISHED.
 *
 * Seen 2026-10-10 17:24Z (Army 7–3 Tulane, `15324325`): at Halftime the map
 * tabs went from `Margin map · 1st half margin · 2nd half margin · …` to
 * `Margin map · 2nd half margin · Points map`. The server stops quoting a
 * finished half until the venue grades it (#1588) — correctly — and that left
 * the half's cards with nothing to draw at the moment the half had a result.
 *
 * The contract (ux on #10850, comment 6100526979): those rows come back under
 * a NEW key, `closed_period_markets`, each with `probability: null`,
 * `window_closed: true` and the server's evidenced `period_score`. The card
 * grades every rung from that score and draws no forecast: no band, no
 * projection, no percentage. Installed builds never read the key.
 *
 * ═══ THE BYTES ═══
 *
 * The 1H rows of `15322373` (Indiana @ Nebraska, banked 16:41Z for #10830),
 * every one Polymarket, moved to the new key with their prices removed —
 * which is exactly what the server half will do. The halftime score is the
 * one the production look read at 17:56Z: Nebraska 10–3. The server half is
 * not built yet, so these closed rows are the contract applied to real rows,
 * not served bytes.
 *
 * Non-vacuous by construction: every arm renders the REAL component, and the
 * control (same payload, no new key) renders today's empty half — the card
 * is drawn by the new key and nothing else.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import { closedHalfRows, type ClosedPeriodRow } from "@/lib/marketMapUtils";

import live15322373 from "../fixtures/ux10830_game_markets_15322373.20261010T1641Z.json";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const HOME = "Nebraska Cornhuskers";
const AWAY = "Indiana Hoosiers";

type Row = (typeof live15322373.period_markets)[number];
const isFirstHalf = (r: Row) =>
  (r.market_type === "half_spread" || r.market_type === "half_total") && r.period === "1H";

/** The contract applied to a served row: no price, closed, the half's score. */
function closedRow(r: Row, score: { home: number; away: number }): ClosedPeriodRow {
  return {
    ...(r as unknown as ClosedPeriodRow),
    probability: null,
    over_probability: undefined,
    window_closed: true,
    period_score: score,
  };
}

const HALFTIME = { home: 10, away: 3 };
const HALFTIME_HISTORY = [
  { period: "1st Quarter", home_score: 3, away_score: 3, timestamp: "2026-10-10T16:41:00Z" },
  { period: "2nd Quarter", home_score: 10, away_score: 3, timestamp: "2026-10-10T17:20:00Z" },
  { period: "Halftime", home_score: 10, away_score: 3, timestamp: "2026-10-10T17:50:00Z" },
];

function payload(closed: ClosedPeriodRow[] | undefined) {
  return {
    ...live15322373,
    home_score: 10,
    away_score: 3,
    period_markets: live15322373.period_markets.filter((r) => !isFirstHalf(r)),
    ...(closed ? { closed_period_markets: closed } : {}),
  };
}

const closedAt = (score: { home: number; away: number }) =>
  live15322373.period_markets.filter(isFirstHalf).map((r) => closedRow(r, score));

function render(gameMarkets: unknown, eventStatus = "live"): string {
  const p = {
    gameMarkets,
    eventStatus,
    homeTeam: HOME,
    awayTeam: AWAY,
    homeAbbr: "NEB",
    awayAbbr: "IU",
    homeSpread: 6.4,
    openingHomeSpread: 9.0,
    sportKey: "americanfootball_ncaaf",
    // The scoreboard at the break, as the page passes it. It is what gives a
    // live half card its `Actual` tile, so the no-Actual case below can fail.
    espnHistory: HALFTIME_HISTORY,
  } as unknown as React.ComponentProps<typeof MarketMapSection>;
  return visibleText(renderToStaticMarkup(<MarketMapSection {...p} />));
}

const HEADINGS = ["Margin map", "1st half margin", "2nd half margin", "Points map", "1st half points", "2nd half points"];

/** One card's text, bounded by the next card heading after it. */
function cardBody(text: string, heading: string): string {
  const at = text.indexOf(heading);
  if (at === -1) return "";
  const rest = text.slice(at + heading.length);
  const ends = HEADINGS.filter((h) => h !== heading)
    .map((h) => rest.indexOf(h))
    .filter((i) => i >= 0);
  return heading + (ends.length ? rest.slice(0, Math.min(...ends)) : rest);
}

describe("#10850 closedHalfRows — the contract, read strictly", () => {
  const rows = closedAt(HALFTIME);

  it("hands back the half's rows and the score they grade by", () => {
    const got = closedHalfRows(rows, payload(undefined).period_markets, "half_spread", "1H");
    expect(got?.score).toEqual(HALFTIME);
    expect(got?.rows).toHaveLength(12);
  });

  it("refuses a half that still quotes — a row is never in both lists", () => {
    expect(closedHalfRows(rows, live15322373.period_markets, "half_spread", "1H")).toBeNull();
  });

  it("refuses a priced row: a closed window never carries a price", () => {
    const priced = rows.map((r, i) => (i === 0 ? { ...r, probability: 0.5 } : r));
    expect(closedHalfRows(priced, [], "half_spread", "1H")).toBeNull();
  });

  it("refuses a row with no evidenced score, rather than inferring one", () => {
    const blank = rows.map((r, i) => (i === 0 ? { ...r, period_score: null } : r));
    expect(closedHalfRows(blank, [], "half_spread", "1H")).toBeNull();
  });

  it("refuses a half whose rows disagree on the score", () => {
    const split = rows.map((r, i) => (i === 0 ? { ...r, period_score: { home: 7, away: 3 } } : r));
    expect(closedHalfRows(split, [], "half_spread", "1H")).toBeNull();
  });

  it("refuses a row that does not say its window closed", () => {
    const open = rows.map((r, i) => (i === 0 ? { ...r, window_closed: undefined } : r));
    expect(closedHalfRows(open, [], "half_spread", "1H")).toBeNull();
  });
});

describe("#10850 the live page at halftime", () => {
  it("control: without the new key the 1st half cards are gone — today's page", () => {
    const text = render(payload(undefined));
    expect(text).toContain("2nd half margin");
    expect(text).not.toContain("1st half margin");
    expect(text).not.toContain("1st half points");
  });

  it("the 1st half margin card is back with the half's FINAL, NEB by 7", () => {
    const body = cardBody(render(payload(closedAt(HALFTIME))), "1st half margin");
    expect(body).toContain("1st half margin");
    expect(body).toMatch(/Final\s+NEB by 7/);
  });

  it("every rung is graded from the score — Indiana lost the half, so none cleared", () => {
    const body = cardBody(render(payload(closedAt(HALFTIME))), "1st half margin");
    for (const line of [2.5, 4.5, 5.5, 6.5, 7.5, 9.5]) {
      expect(body).toMatch(new RegExp(`IU by ${line.toString().replace(".", "\\.")}\\+\\s+not cleared`));
    }
  });

  it("and it draws no forecast: no percentage, no projection, no live Actual tile", () => {
    const body = cardBody(render(payload(closedAt(HALFTIME))), "1st half margin");
    expect(body).toContain("Final");
    expect(body).not.toMatch(/\d%/);
    expect(body).not.toContain("Projection");
    expect(body).not.toContain("Pre-game");
    expect(body).not.toContain("Actual");
  });

  it("the grade follows the score rung by rung (invented score: IU 10–3)", () => {
    // Not the specimen's score: a half Indiana won by 7 clears its lines below
    // 7 and misses those above, so a card that graded everything one way
    // could not pass both this case and the one above.
    const body = cardBody(render(payload(closedAt({ home: 3, away: 10 }))), "1st half margin");
    expect(body).toMatch(/Final\s+IU by 7/);
    expect(body).toMatch(/IU by 6\.5\+\s+cleared/);
    expect(body).toMatch(/IU by 7\.5\+\s+not cleared/);
  });

  it("the 1st half points card is back too, graded from 13 points", () => {
    const body = cardBody(render(payload(closedAt(HALFTIME))), "1st half points");
    expect(body).toContain("1st half points");
    expect(body).toMatch(/Final\s+13/);
    expect(body).toMatch(/Over 24\.5\s+not cleared/);
    expect(body).not.toMatch(/\d%/);
    expect(body).not.toContain("O/U");
  });

  it("control: the 2nd half is still quoting and keeps its prices", () => {
    const body = cardBody(render(payload(closedAt(HALFTIME))), "2nd half margin");
    expect(body).toMatch(/\d%/);
  });

  it("a game that is not live never reads the key", () => {
    expect(render(payload(closedAt(HALFTIME)), "scheduled")).not.toContain("1st half margin");
  });
});
