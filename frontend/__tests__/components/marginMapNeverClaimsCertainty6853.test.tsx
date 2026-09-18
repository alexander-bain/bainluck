/**
 * #6853 — A LIVE MARGIN MAP PRINTED `BUF 100%` UNDER A HERO THAT SAID `>99%`.
 *
 * ═══ THE SPECIMEN ═══
 *
 * Production, 2026-09-18 03:16Z, `/events/14638444` (Lions @ Bills) at 390px,
 * during the notice-42 live-marquee shop. `2:50 - 4th Quarter`, 41 – 24, status
 * still `live` (`artifacts/ux-1324/notice42-0316Z-live-top-390.png`):
 *
 *     hero        >99%  –  <1%        Bills 68% → >99% since open
 *     ⋮
 *     MARGIN MAPS
 *     Margin map  — Where it's heading vs what was expected —   BUF 100%
 *
 * One served probability, one page, two renderings:
 *
 *     GET /api/events/14638444
 *       current_odds.home_probability 0.999 / away_probability 0.001
 *       home_rendered_percent 100        / away_rendered_percent 0
 *
 * ═══ WHY THE HERO IS RIGHT AND THIS CARD WAS NOT ═══
 *
 * `probabilityParts` applies the boundary rule to the PROBABILITY, and says why
 * in its own docstring: "A served 100 over a probability of 0.996 is still
 * `>99%`, because 'rounding may never move a probability across a boundary it is
 * not on' is a claim about the value, not about which arithmetic produced the
 * integer." So the hero prints `>99%` even though the SERVER's rendered integer
 * is 100.
 *
 * This card did `${Math.round(favoredProb * 100)}%` inline and skipped all of
 * that — so it announced certainty about a game that was still being played, and
 * the page contradicted itself one screen apart.
 *
 * Population: the closing stretch of any one-sided game, which is exactly the
 * window a reader is most likely to have the live page open.
 *
 * ═══ WHAT EACH TEST IS FOR ═══
 *
 * The first is the ship clause. The rest are controls, because "never print 100"
 * is also satisfied by dropping the headline, by capping at 99, or by rounding
 * everything down:
 *
 *   - `an ordinary live favourite is unchanged` is the one that matters: this
 *     must move the two ends and nothing else. A cap would print `99%` here.
 *   - `the badge still names the favoured side` keeps the other half of the
 *     string, which a "just use formatProbability" edit could drop.
 *   - `a settled card still prints no headline` pins #5206's arm, which is
 *     upstream of this change and must stay upstream of it.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;/g, "'")
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * A spread rung exactly as production serves it — the Kalshi cover ladder, whose
 * numbers live in `outcome_name`.
 *
 * 🪤 This is not cosmetic fidelity. `parseSpreadOutcome` reads the SPREAD OUT OF
 * `outcome_name`, not out of `market_name`, so the Polymarket rows on the same
 * payload (`market_name: "Spread: Bills (-19.5)"`, `outcome_name: "Bills"`) parse
 * to nothing. A first draft of this file used that shape and the whole section
 * rendered `""` — `parsed.length === 0` returns null at the margin block and, with
 * no totals either, the component returns null. Every assertion then "failed"
 * against an empty string, which looks exactly like a broken fix.
 *
 * Real rows from `GET /api/events/14638444/game-markets`, read 02:44Z.
 */
const coverRung = (line: number, pBuffalo: number, pDetroit: number) => [
  {
    market_name: "Detroit vs Buffalo: Spread",
    outcome_name: `Buffalo wins by over ${line} points`,
    threshold: null,
    probability: pBuffalo,
    source: "kalshi",
    is_winner: null,
    resolution_source: null,
  },
  {
    market_name: "Detroit vs Buffalo: Spread",
    outcome_name: `Detroit wins by over ${line} points`,
    threshold: null,
    probability: pDetroit,
    source: "kalshi",
    is_winner: null,
    resolution_source: null,
  },
];

function lionsAtBills(overrides: Record<string, unknown> = {}) {
  return {
    event_id: 14638444,
    home_team: "Buffalo Bills",
    away_team: "Detroit Lions",
    home_score: 41,
    away_score: 24,
    status: "live",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    props_script: [],
    totals: [],
    spreads: [
      ...coverRung(1.5, 0.93, 0.08),
      ...coverRung(2.5, 0.88, 0.08),
      ...coverRung(3.5, 0.84, 0.04),
      ...coverRung(9.5, 0.62, 0.02),
      ...coverRung(16.5, 0.35, 0.01),
    ],
    pace: null,
    ...overrides,
  };
}

/**
 * `homeWinProb` is the input under test — it is what the headline is built from.
 * Everything else is held at the shop's own reading.
 */
function renderCard(homeWinProb: number, eventStatus = "live") {
  return visibleText(
    renderToStaticMarkup(
      <MarketMapSection
        gameMarkets={lionsAtBills({ status: eventStatus }) as never}
        eventStatus={eventStatus}
        homeTeam="Buffalo Bills"
        awayTeam="Detroit Lions"
        homeAbbr="BUF"
        awayAbbr="DET"
        homeWinProb={homeWinProb}
        awayWinProb={1 - homeWinProb}
        overUnder={54.1}
        openingOverUnder={55}
        openingHomeSpread={-5.5}
        homeSpread={-15}
        sportKey="americanfootball_nfl"
      />
    )
  );
}

describe("#6853 — a live margin map never claims certainty", () => {
  it("🔴 SHIP: the photographed 0.999 prints >99%, not 100%", () => {
    const text = renderCard(0.999);

    expect(text).toMatch(/BUF >99%/);
    expect(text).not.toMatch(/BUF 100%/);
  });

  it("CONTROL: an ordinary live favourite is unchanged", () => {
    // The whole point is that this moves the two ENDS and nothing else. A cap at
    // 99, or a floor-instead-of-round, would show up right here.
    expect(renderCard(0.73)).toMatch(/BUF 73%/);
    expect(renderCard(0.5049)).toMatch(/BUF 50%/);
    expect(renderCard(0.99)).toMatch(/BUF 99%/);
  });

  it("CONTROL: the badge still names the favoured side", () => {
    // The abbreviation is the other half of the string and an edit that swapped
    // the whole expression for a bare percent would pass the clause above.
    const text = renderCard(0.999);
    expect(text).toMatch(/BUF/);
    expect(text).not.toMatch(/DET >99%/);
  });

  it("CONTROL: a settled card still prints no headline here", () => {
    // #5206's arm, upstream of this change and required to stay upstream: the
    // result is already on a settled card twice, so a third voice is noise.
    const text = renderCard(0.999, "completed");
    expect(text).not.toMatch(/BUF >99%/);
    expect(text).not.toMatch(/BUF 100%/);
  });
});
