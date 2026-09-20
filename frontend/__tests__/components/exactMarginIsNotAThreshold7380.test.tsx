/**
 * #7380 — AN EXACT MARGIN IS STATED, NOT HEDGED.
 *
 * Mystery-shopped on production 2026-09-19 at 390px (filed by discover/237,
 * re-shot by ux before the fix). `/events/15304450`, Boston College 28 ·
 * Rutgers 21, FINAL. The card titled "Margin: expected vs final" drew:
 *
 *     PRE-GAME  BC by 3+          FINAL  BC by 7+
 *
 * The final margin is exactly 7. "7+" means seven OR MORE, and a played margin
 * has nothing more in it. The live arm said the same thing about a scoreboard
 * the reader could see: `ACTUAL JMU by 13+` over 13–26.
 *
 * ═══ WHY THIS IS A DEFECT AND NOT A PREFERENCE ═══
 *
 * The same screen already spelled the same kind of quantity two other ways.
 * One card below the specimen, the totals card prints its settled total as
 * `49 points`; the half margin rail printed its exact margin as `NYG +14`.
 * Three sites for one idea — "here is the number that happened" — and only the
 * margin markers hedged it.
 *
 * ═══ WHAT KEEPS ITS `+`, AND WHY THIS SUITE PINS THAT TOO ═══
 *
 * A LADDER RUNG is a threshold: `gradeMarginRung` grades it `>=` precisely
 * because `NYG by 15+` claims fifteen or more. The PRE-GAME and PROJECTION
 * tiles quote a COVER LINE — a handicap, at `.5`, that nothing has settled.
 * Both are true as written and both stay. So the cheap fix — strip the `+`
 * from the card — is a different defect, and every arm below carries the
 * rung and cover-line controls that catch it.
 *
 * ═══ AND NOT `BC +7` ═══
 *
 * That is the spelling the half rail reached for, and it is the one #2442
 * removed from this page: a competitor abbreviation followed by a signed
 * number is a betting line, the first of the six gambling formats Alex counted
 * on one screen. #2442's answer was `by N` in the sport's own units. So the fix
 * brings the half markers to the full-game ones rather than the other way, and
 * the last arm asserts all four markers on both rails are spelled one way.
 *
 * Every number in the fixtures is production's, from `/events/15304450` and
 * `/events/15312078` read on 2026-09-19, except the two halftime rows, which
 * are synthetic and marked where they appear — the half rail needs a halftime
 * the specimen's own history did not carry.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x27;|&#39;|&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** How many summary tiles of this kind the section drew. */
function tileCount(html: string, key: string): number {
  return html.split(`data-tile="${key}"`).length - 1;
}

/**
 * THE INVARIANT, asked of a whole card at once: no marker whose label is a
 * measurement — `Actual`, `Final` — is allowed either hedged spelling.
 *
 * `by N+` is the rung grammar and `+N` is the handicap one; both are wrong on
 * a scoreboard and each is what the other's fix reaches for, so both are
 * banned in one place and every arm below runs it.
 */
function hedgedMeasurements(text: string): string[] {
  return [
    ...text.matchAll(/\b(Actual|Final)\s+([A-Z][A-Za-z]{1,5}\s+by\s+\d+(?:\.\d+)?\+)/g),
    ...text.matchAll(/\b(Actual|Final)\s+([A-Z][A-Za-z]{1,5}\s+\+\d+(?:\.\d+)?)/g),
  ].map((m) => `${m[1]} ${m[2]}`);
}

// ─────────────────────────────────────────────────────────────────────────────
// THE SETTLED SPECIMEN — /events/15304450, Boston College 28 · Rutgers 21.
// Home is Boston College: production's rail reads `RUTG by 18+` on the left and
// `BC by 18+` on the right, and the right-hand end of this rail is home.
// ─────────────────────────────────────────────────────────────────────────────

const BC = "Boston College";
const RUTG = "Rutgers";

const bcSpread = (team: string, threshold: number, probability: number) => ({
  market_name: `${RUTG} vs ${BC}: Spread`,
  outcome_name: `${team} wins by more than ${threshold} points`,
  threshold: null,
  probability,
  market_type: "spread",
  source: "kalshi",
  is_winner: null,
  resolution_source: null,
});

const bcTotal = (threshold: number, over: number) => ({
  threshold,
  over_probability: over,
  source: "kalshi",
  market_type: "game_total",
  market_name: `${RUTG} vs ${BC}: Total Points`,
  outcome_name: `Over ${threshold} points`,
  is_winner: over >= 1,
  resolution_source: null,
  movement: 0,
  period: null,
});

/**
 * The settled card as the finished event page mounts it — the margin rail AND
 * the totals rail, because the totals rail is the control: it is the card one
 * slot below the specimen, holding the same kind of quantity, and it has always
 * printed it plainly.
 */
function renderSettledBC(): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: 15304450,
          home_team: BC,
          away_team: RUTG,
          home_score: 28,
          away_score: 21,
          status: "completed",
          player_props: [],
          team_totals: [],
          period_markets: [],
          matchups: [],
          other: [],
          pace: null,
          props_script: [],
          spreads: [
            bcSpread(BC, 2.5, 0.72),
            bcSpread(BC, 6.5, 0.51),
            bcSpread(BC, 10.5, 0.28),
            bcSpread(RUTG, 2.5, 0.24),
          ],
          totals: [bcTotal(44.5, 1.0), bcTotal(51.5, 0.0)],
        } as never
      }
      eventStatus="completed"
      homeTeam={BC}
      awayTeam={RUTG}
      homeAbbr="BC"
      awayAbbr="RUTG"
      // Production's PRE-GAME tile read `BC by 3+`.
      openingHomeSpread={-3}
      openingOverUnder={54}
      sportKey="americanfootball_ncaaf"
    />
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// THE LIVE SPECIMEN — /events/15312078, San Diego State 13 @ James Madison 26,
// 4th quarter. The halftime row is SYNTHETIC (13–7): the half rail needs one,
// and the claim being tested is the spelling, not that number.
// ─────────────────────────────────────────────────────────────────────────────

const JMU = "James Madison";
const SDSU = "San Diego State";

const jmuSpread = (team: string, threshold: number, probability: number) => ({
  market_name: `${SDSU} vs ${JMU}: Spread`,
  outcome_name: `${team} wins by more than ${threshold} points`,
  threshold: null,
  probability,
  market_type: "spread",
  source: "kalshi",
  is_winner: null,
  resolution_source: null,
});

const jmuHalfSpread = (team: string, threshold: number, probability: number) => ({
  market_name: `${SDSU} vs ${JMU}: 2nd Half Spread`,
  outcome_name: `${team} wins the 2H by more than ${threshold} points`,
  threshold,
  probability,
  market_type: "half_spread",
  over_probability: null,
  period: "2H",
  source: "kalshi",
  is_winner: null,
  resolution_source: null,
  movement: 0,
});

const LIVE_HISTORY = [
  { period: "1st Quarter", home_score: 7, away_score: 0, timestamp: "2026-09-19T23:20:00+00:00" },
  // Synthetic, and the only synthetic number in this file.
  { period: "Halftime", home_score: 13, away_score: 7, timestamp: "2026-09-20T00:10:00+00:00" },
  { period: "3rd Quarter", home_score: 20, away_score: 13, timestamp: "2026-09-20T00:55:00+00:00" },
];

/**
 * Live, 26–13, in the second half. Two rails at once on purpose: the full game
 * is 13 ahead and the half is 7 ahead (13–6), so an assertion that passed by
 * reading the wrong rail reads the wrong number and fails.
 */
function renderLiveJMU(): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: 15312078,
          home_team: JMU,
          away_team: SDSU,
          home_score: 26,
          away_score: 13,
          status: "live",
          player_props: [],
          team_totals: [],
          period_markets: [jmuHalfSpread(JMU, 1.5, 0.55), jmuHalfSpread(SDSU, 1.5, 0.33)],
          matchups: [],
          other: [],
          pace: null,
          props_script: [],
          spreads: [
            jmuSpread(JMU, 2.5, 0.88),
            jmuSpread(JMU, 6.5, 0.71),
            jmuSpread(SDSU, 2.5, 0.09),
          ],
          totals: [],
        } as never
      }
      eventStatus="live"
      homeTeam={JMU}
      awayTeam={SDSU}
      homeAbbr="JMU"
      awayAbbr="SDSU"
      openingHomeSpread={-3.5}
      homeSpread={-10.5}
      espnHistory={LIVE_HISTORY}
      sportKey="americanfootball_ncaaf"
    />
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// THE HALF RAIL, SETTLED — /events/14637256, Giants 28 · Cowboys 20, halftime
// 14–7 (production's own history, the fixture #6169 and #6203 are built on).
// 1H margin 7, 2H margin 1.
// ─────────────────────────────────────────────────────────────────────────────

const NYG = "New York Giants";
const DAL = "Dallas Cowboys";

const SNF_HISTORY = [
  { period: "1st Quarter", home_score: 0, away_score: 0, timestamp: "2026-09-14T00:20:00+00:00" },
  { period: "Halftime", home_score: 14, away_score: 7, timestamp: "2026-09-14T01:30:00+00:00" },
  { period: "Final", home_score: 28, away_score: 20, timestamp: "2026-09-14T03:28:00+00:00" },
];

const snfHalfSpread = (period: "1H" | "2H", team: string, probability: number) => ({
  market_name: `${DAL} vs ${NYG}: ${period === "1H" ? "First" : "Second"} Half Spread`,
  outcome_name: `${team} wins the ${period} by more than 1.5 points`,
  threshold: 1.5,
  probability,
  market_type: "half_spread",
  over_probability: null,
  period,
  source: "kalshi",
  is_winner: null,
  resolution_source: null,
  movement: 0,
});

/**
 * The two half margin cards alone — no `spreads`, no `totals`, so every marker
 * in the markup belongs to a half rail. Prices are the QUOTING ones (#5488): a
 * settled ladder with no interior drops its Pre-game tile, and this suite wants
 * that tile present as the cover-line control.
 */
function renderSettledHalves(): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: 14637256,
          home_team: NYG,
          away_team: DAL,
          home_score: 28,
          away_score: 20,
          status: "completed",
          player_props: [],
          team_totals: [],
          period_markets: [
            snfHalfSpread("1H", NYG, 0.42),
            snfHalfSpread("1H", DAL, 0.33),
            snfHalfSpread("2H", NYG, 0.55),
            snfHalfSpread("2H", DAL, 0.28),
          ],
          matchups: [],
          other: [],
          pace: null,
          props_script: [],
          spreads: [],
          totals: [],
        } as never
      }
      eventStatus="completed"
      homeTeam={NYG}
      awayTeam={DAL}
      homeAbbr="NYG"
      awayAbbr="DAL"
      espnHistory={SNF_HISTORY}
      sportKey="americanfootball_nfl"
    />
  );
}

/** The specimen's own draw — Gwangju FC 1 · FC Anyang 1, which prints `Tied`. */
function renderSettledDraw(): string {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={
        {
          event_id: 15306857,
          home_team: "Gwangju FC",
          away_team: "FC Anyang",
          home_score: 1,
          away_score: 1,
          status: "completed",
          player_props: [],
          team_totals: [],
          period_markets: [],
          matchups: [],
          other: [],
          pace: null,
          props_script: [],
          spreads: [
            {
              market_name: "Gwangju vs FC Anyang: Spread",
              outcome_name: "Gwangju wins by more than 1.5 goals",
              threshold: null,
              probability: 0.18,
              market_type: "spread",
              source: "kalshi",
              is_winner: null,
              resolution_source: null,
            },
            {
              market_name: "Gwangju vs FC Anyang: Spread",
              outcome_name: "FC Anyang wins by more than 1.5 goals",
              threshold: null,
              probability: 0.21,
              market_type: "spread",
              source: "kalshi",
              is_winner: null,
              resolution_source: null,
            },
          ],
          totals: [],
        } as never
      }
      eventStatus="completed"
      homeTeam="Gwangju FC"
      awayTeam="FC Anyang"
      homeAbbr="GWJ"
      awayAbbr="ANY"
      sportKey="soccer_korea_kleague1"
    />
  );
}

describe("#7380 the FINAL marker states the margin that happened", () => {
  it("THE SPECIMEN: a 7-point win reads `BC by 7`, not `BC by 7+`", () => {
    const html = renderSettledBC();
    const text = visibleText(html);

    // The card drew at all. Without this the absence below is satisfied by a
    // card that never rendered. Two Final tiles, because this render carries
    // both rails: the margin card's and the totals card's below it.
    expect(text).toContain("Margin: expected vs final");
    expect(tileCount(html, "final")).toBe(2);

    expect(text).toMatch(/\bFinal\s+BC by 7(?![\d.+])/);
    expect(text).not.toMatch(/\bFinal\s+BC by 7\+/);
    expect(hedgedMeasurements(text)).toEqual([]);
  });

  it("CONTROL: the cover line beside it KEEPS its `+`, because nothing settled it", () => {
    // The `+` is not noise to be swept off the card. `BC by 3+` is a handicap
    // the market quoted; a fix that strips every `+` from the tiles fails here.
    const html = renderSettledBC();
    const text = visibleText(html);

    // One per rail again — the margin card's `BC by 3+` and the totals card's
    // pre-game 54, which is the other half of the contrast this ship is about.
    expect(tileCount(html, "pre")).toBe(2);
    expect(text).toMatch(/\bPre-game\s+BC by 3\+/);
  });

  it("CONTROL: the ladder rungs KEEP their `+`, because a rung IS a threshold", () => {
    // `gradeMarginRung` grades `>=` on the strength of this label. A fix that
    // respelled `marginLadderLabel` would make the rail claim exact margins it
    // was never quoting.
    const text = visibleText(renderSettledBC());

    expect(text).toContain("BC by 6.5+");
    expect(text).toContain("BC by 2.5+");
    expect(text).toContain("RUTG by 2.5+");
  });

  it("CONTROL: the totals card one slot down is unchanged — `49 points`", () => {
    // This is the card that made the defect visible: the same reader, the same
    // screen, one settled quantity stated plainly and the other hedged.
    const text = visibleText(renderSettledBC());

    expect(text).toContain("Total: expected vs final");
    expect(text).toContain("49 points");
  });

  it("a draw still reads `Tied`, on both the tile and the rail's own axis", () => {
    const html = renderSettledDraw();
    const text = visibleText(html);

    expect(tileCount(html, "final")).toBe(1);
    expect(text).toMatch(/\bFinal\s+Tied\b/);
    // Not the arithmetic answer: nobody won by zero.
    expect(text).not.toContain("by 0");
    expect(text).not.toContain("GWJ by 0");
  });
});

describe("#7380 the ACTUAL marker states the scoreboard the reader can see", () => {
  it("THE LIVE SPECIMEN: 26–13 reads `JMU by 13`, not `JMU by 13+`", () => {
    const html = renderLiveJMU();
    const text = visibleText(html);

    expect(text).toContain("Margin map");
    expect(tileCount(html, "actual")).toBeGreaterThanOrEqual(1);

    expect(text).toMatch(/\bActual\s+JMU by 13(?![\d.+])/);
    expect(text).not.toMatch(/\bActual\s+JMU by 13\+/);
    expect(hedgedMeasurements(text)).toEqual([]);
  });

  it("CONTROL: the live card's forecast tiles keep the grammar of a forecast", () => {
    // PRE-GAME and PROJECTION are cover lines on a game still being played —
    // #7380 is explicitly not about them, and they must survive the fix.
    const html = renderLiveJMU();
    const text = visibleText(html);

    expect(tileCount(html, "pre")).toBe(1);
    expect(text).toMatch(/\bPre-game\s+JMU by 3\.5\+/);
    expect(text).toMatch(/\bProjection\s+JMU by 10\.5\+/);
  });
});

describe("#7380 the half rail says it the same way the full-game rail does", () => {
  it("SETTLED: a 7-point half reads `NYG by 7` — and not the old `NYG +7`", () => {
    const html = renderSettledHalves();
    const text = visibleText(html);

    // Both cards present and still naming their rungs, so the bans below are
    // assertions rather than a description of two cards that vanished.
    expect(text).toContain("1st half margin");
    expect(text).toContain("2nd half margin");
    expect(text).toContain("NYG by 1.5+");
    expect(text).toContain("DAL by 1.5+");
    expect(tileCount(html, "final")).toBe(2);

    // 1H is 14–7 and 2H is 14–13: two different numbers, so an assertion that
    // read the wrong card reads the wrong margin.
    expect(text).toMatch(/\bFinal\s+NYG by 7(?![\d.+])/);
    expect(text).toMatch(/\bFinal\s+NYG by 1(?![\d.+])/);

    // The pre-#7380 spelling, which was this rail's own (#2442's handicap).
    expect(text).not.toContain("NYG +7");
    expect(text).not.toContain("NYG +1");
    expect(hedgedMeasurements(text)).toEqual([]);
  });

  it("LIVE: the half in progress reads `JMU by 7` beside a full game of 13", () => {
    const text = visibleText(renderLiveJMU());

    expect(text).toContain("2nd half margin");
    expect(text).toMatch(/\bActual\s+JMU by 7(?![\d.+])/);
    expect(text).not.toContain("JMU +7");
  });

  it("ALL FOUR MARKERS, ONE GRAMMAR: no measurement on either rail is hedged", () => {
    // The point of the ship, asked once over every card this file draws. Four
    // sites spelled one quantity three ways before it; a future fifth marker
    // that reaches for either wrong spelling reddens here.
    for (const html of [renderSettledBC(), renderLiveJMU(), renderSettledHalves()]) {
      expect(hedgedMeasurements(visibleText(html))).toEqual([]);
    }

    // And the grammar that is still correct is still drawn, so the line above
    // cannot be satisfied by a page with no markers on it.
    const settled = visibleText(renderSettledBC());
    expect(settled).toMatch(/\bPre-game\s+BC by 3\+/);
    expect(settled).toMatch(/\bFinal\s+BC by 7(?![\d.+])/);
  });
});
