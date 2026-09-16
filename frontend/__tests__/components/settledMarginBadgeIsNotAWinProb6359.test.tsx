/**
 * #6359 — A SETTLED MARGIN CARD STOPS PRINTING AN UNLABELLED WIN PROBABILITY.
 *
 * `/events/15306857` (Gwangju FC 1 – 1 FC Anyang, FINAL), production, 390px:
 * the "Margin: expected vs final" card printed **`ANY 62%`** in its top-right,
 * directly above its own `PRE-GAME Tied` / `FINAL Tied` tiles and four rungs
 * that all read `not cleared`. Anyang did not win. Nothing on the badge said
 * which tense it was in.
 *
 * ── THE ROUTED DIAGNOSIS WAS WRONG, AND CHECKING IT IS WHY THIS FIXTURE IS
 *    SHAPED THE WAY IT IS ──────────────────────────────────────────────────
 *
 * The issue said the number was a stale pre-match snapshot ("captured 2 h
 * before kickoff"). Measured against production before building:
 *
 *     /api/events/15306857   commence_time  2026-09-13T10:00:00Z
 *                            captured_at    2026-09-13T11:51:27Z
 *                            completed_at   2026-09-13T11:56:44Z
 *                            home 0.3784 / away 0.6216   (sum exactly 1.0)
 *
 * The capture is IN-PLAY, five minutes from full time — the freshest reading
 * the match ever had. So this is not a staleness defect and no amount of
 * fresher data fixes it: on a DRAW neither side's probability can converge, so
 * the last honest reading is whatever the market thought while the result was
 * still a question, and the card publishes it as if it were the answer.
 *
 * That is why the fixture below is a draw with a MID-RANGE probability rather
 * than a stale one. A fixture built from the issue's story — an old capture —
 * would have passed against a fix that gated on capture age and let the real
 * defect through.
 *
 * ── WHY THE DEFECT IS ALMOST INVISIBLE, WHICH IS WHAT MAKES IT WORTH A GUARD ─
 *
 * On a decisive result the last capture converges to ~100% for the winner, so
 * the badge coincidentally reads as a result:
 *
 *     15307041 Braga–Estoril     1–0   BRA 100%   (captured at full time)
 *     15299176 Como–Parma        2–1   COM  99%
 *     15306857 Gwangju–Anyang    1–1   ANY  62%   ← the one a reader cannot age
 *
 * A draw is ~25% of soccer fixtures, so the badge is right-looking nearly
 * everywhere and wrong exactly where nothing else on the card contradicts it.
 * ARM 3 below is the decisive control: the fix must drop the badge there too,
 * because `BRA 100%` is the same unlabelled win probability and is only
 * *coincidentally* indistinguishable from a result. A fix that special-cased
 * draws would pass ARM 1 and leave the class open.
 *
 * ── THE CONTROLS ARE THE SUITE ──────────────────────────────────────────────
 *
 * `live` and `pre` must KEEP the badge. There it is a current reading of an
 * open question, and a tense fix that fired on every status would pass every
 * settled assertion here while blanking the badge on every in-play and
 * scheduled card on the site. That is the mutant this file exists to catch.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const HOME = "Gwangju FC";
const AWAY = "FC Anyang";
const H_ABBR = "GWA";
const A_ABBR = "ANY";

/**
 * Event 15306857's own spread rows, verbatim from production (market 60672667)
 * — the four legs #6312's backend half readmitted. All four lost, which is what
 * puts `not cleared` under a badge claiming 62%.
 */
const SERVED_SPREADS = [
  { market_name: "Gwangju vs FC Anyang: Spread", outcome_name: "FC Anyang wins by more than 1.5 goals", probability: 0.0, source: "kalshi", market_type: "spread" },
  { market_name: "Gwangju vs FC Anyang: Spread", outcome_name: "FC Anyang wins by more than 2.5 goals", probability: 0.0, source: "kalshi", market_type: "spread" },
  { market_name: "Gwangju vs FC Anyang: Spread", outcome_name: "Gwangju wins by more than 1.5 goals", probability: 0.0, source: "kalshi", market_type: "spread" },
  { market_name: "Gwangju vs FC Anyang: Spread", outcome_name: "Gwangju wins by more than 2.5 goals", probability: 0.0, source: "kalshi", market_type: "spread" },
];

function markets(homeScore: number, awayScore: number, status: string) {
  return {
    event_id: 15306857,
    home_team: HOME,
    away_team: AWAY,
    home_score: homeScore,
    away_score: awayScore,
    status,
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: SERVED_SPREADS,
    totals: [],
  };
}

function renderMaps(
  eventStatus: string,
  homeWinProb: number,
  awayWinProb: number,
  homeScore = 1,
  awayScore = 1,
) {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={markets(homeScore, awayScore, eventStatus) as never}
      eventStatus={eventStatus}
      homeTeam={HOME}
      awayTeam={AWAY}
      homeAbbr={H_ABBR}
      awayAbbr={A_ABBR}
      homeWinProb={homeWinProb}
      awayWinProb={awayWinProb}
      sportKey="soccer_korea_kleague1"
    />
  );
}

/** The badge's exact shape: an abbreviation and a rounded percent, together. */
function badgeFor(abbr: string, pct: number): string {
  return `${abbr} ${pct}%`;
}

describe("#6359 — a settled margin card prints no bare win probability", () => {
  it("ARM 1: the specimen — a FINAL draw drops `ANY 62%`", () => {
    const text = visibleText(renderMaps("completed", 0.3784, 0.6216));

    // The defect, by the string a reader actually saw.
    expect(text).not.toContain(badgeFor(A_ABBR, 62));

    // And not by the other side either, in case a fix flipped the favourite
    // rather than removing the claim.
    expect(text).not.toContain(badgeFor(H_ABBR, 38));

    // This is a tense fix, not a suppression: the card is still here, still
    // says what it is, and still carries the result it does have.
    //
    // `Final`, not `FINAL` — the tile's capitals are CSS, and the rendered
    // markup says `Final`. Asserting the screenshot's spelling would have made
    // this a test of a stylesheet that passes for the wrong reason.
    expect(text).toContain("expected vs final");
    expect(text).toContain("Final");
    expect(text).toContain("Tied");

    // The four graded rungs are the reason the badge read as a contradiction,
    // so they must survive the fix that removes it.
    expect(text).toContain("not cleared");
  });

  it("ARM 2: `closed` is settled too — the second graded status", () => {
    const text = visibleText(renderMaps("closed", 0.3784, 0.6216));
    expect(text).not.toContain(badgeFor(A_ABBR, 62));
  });

  /**
   * The decisive-result arm. `BRA 100%` looks like a result and is not one —
   * it is the same unlabelled win probability, and a reader has no way to know
   * that on THIS card it happens to agree with the scoreboard. Gating on "the
   * probability is ambiguous" would pass ARM 1 and leave every other finished
   * game printing a number whose tense is still invisible.
   */
  it("ARM 3: a DECISIVE final drops it too, though it looked right", () => {
    const text = visibleText(renderMaps("completed", 0.995, 0.005, 1, 0));
    expect(text).not.toContain(badgeFor(H_ABBR, 100));
  });

  it("CONTROL: an IN-PLAY card keeps the badge", () => {
    const text = visibleText(renderMaps("live", 0.3784, 0.6216));
    expect(text).toContain(badgeFor(A_ABBR, 62));
  });

  it("CONTROL: a SCHEDULED card keeps the badge", () => {
    const text = visibleText(renderMaps("scheduled", 0.3784, 0.6216, 0, 0));
    expect(text).toContain(badgeFor(A_ABBR, 62));
  });

  /**
   * The favourite rule itself is untouched by this ship, and is pinned so a
   * later edit to the badge cannot quietly change WHICH team it names while
   * every assertion above still passes — they are all absence assertions on
   * the settled arm, and absence is satisfied by any wrong answer too.
   */
  it("CONTROL: the live badge still names the favourite, not the home side", () => {
    expect(visibleText(renderMaps("live", 0.3784, 0.6216))).toContain(badgeFor(A_ABBR, 62));
    expect(visibleText(renderMaps("live", 0.71, 0.29))).toContain(badgeFor(H_ABBR, 71));
  });
});
