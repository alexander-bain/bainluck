// #7660 — A LIVE GAME'S SCORE DIFFERENTIAL STOPS DRAWING A "KALSHI IMPLIED"
// LINE AT A TIE WHILE THE HERO ABOVE IT READS 78%.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `/events/14780544` — Kansas City Chiefs 24, Indianapolis Colts 20, **live,
// 5:12 left in the 3rd quarter** — read at 390px on 2026-09-20 7:27 PM PDT,
// during the notice-42 no-refresh pass on the Sunday night game.
// Frame: `artifacts/ux-1402/final/20260920-snf-final-1927PT-y700.png`.
//
// In the Score Differential card, on one screen:
//
//   * a flat purple dashed line labelled **Kalshi Implied**, edge to edge, at
//     **a tie**;
//   * the pink **Polymarket Implied** line above it at about **Chiefs +7**;
//   * the orange **Actual Score Diff** finishing at **Chiefs +4**;
//   * and one card up, the hero: **Chiefs 78% – Colts 22%**.
//
// Kalshi was the only thing on the page saying the game was even.
//
// ── AND KALSHI WAS NOT SAYING THAT ───────────────────────────────────────────
//
// `GET /api/events/14780544/history`, captured live and committed verbatim as
// `fixtures/impliedSpread.14780544.live.json`:
//
//     kalshi      home_margin: +0.3   confidence: 0.2   33 rungs
//     polymarket  home_margin: +6.7   confidence: 0.97   7 rungs
//     sportsbook  home_margin: +7.1   confidence: 1.0    0 rungs
//
// The kalshi arm's HALF-POINT rungs are clean and monotone and cross 0.50 at
// **7.5** — Chiefs by 7.5, agreeing with polymarket, the sportsbooks and the
// hero. Three INTEGER thresholds are interleaved into them, each appearing
// twice with contradictory probabilities, and one lands beside the crossing:
//
//     1.0 -> 0.37  and  1.0 -> 0.11
//     7.0 -> 0.02  and  7.0 -> 0.48
//    15.0 -> 0.12  and 15.0 -> 0.13
//
// Spreads are quoted on half points so they cannot push; a `.0` rung in a
// spread ladder is a different market family folded in at ingest. Repairing
// that is the DERIVATION half of #7660 and is not ux's — it is filed with this
// wire quoted, and the fixture below holds it contracts and all so the evidence
// outlives the fix.
//
// ── TWO DISCRIMINATORS WERE BUILT BEFORE THIS ONE AND BOTH MEASURED WRONG ────
//
// Recorded because each looked right until the controls answered:
//
//   1. "Refuse a ladder with duplicated rungs." Those integer duplicates are in
//      EVERY NFL kalshi ladder on the wire, including #6142's scheduled
//      control. The rule deleted the line on every page, not the broken ones.
//   2. "Refuse duplicates that straddle 0.50" — the pair that can actually move
//      the implied margin. The live ladder moved across that boundary between
//      two reads six minutes apart (`7.0 -> [0.50, 0.01]` at 02:29Z became
//      `[0.02, 0.48]` at 02:35Z). It caught a moment, not a defect.
//
// A renderer cannot re-derive its way to trust in a number the producer
// derived. What the producer STATES is `confidence`, which #6142 recorded the
// chart ignores — `0.2` draws exactly like `1.0`.
//
// ── THE MEASUREMENT THAT DECLINED THIS GATE HAS INVERTED ─────────────────────
//
// #6142 declined a confidence floor on one reading: every kalshi arm served
// `0.2`, so a floor "would delete the feature on every game". True when taken.
// On the wire of 2026-09-21 02:29Z:
//
//     14780544 live       polymarket 0.97 (+6.7)   kalshi 0.2 (+0.3)
//     14780545 scheduled  polymarket 0.95 (+6.9)   kalshi 0.2 (-0.4)
//
// Both non-final NFL pages keep a line, and the line each keeps is the one that
// agrees with the score, the hero and the sportsbooks.
//
// ── WHAT IT COSTS, ASSERTED RATHER THAN GLOSSED ──────────────────────────────
//
// #6142 installed "an unplayed game still draws it, from both venues" against
// exactly this ship deleting the feature. Its fixture (polymarket 0.3, kalshi
// 0.2) now draws neither arm. That is a real reduction in coverage on games
// whose only arms are distrusted, taken deliberately and asserted below so it
// cannot widen by accident.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import {
  MIN_CONFIDENCE,
  impliedSpreadArmIsTrusted,
  drawnImpliedSpreadSources,
} from "@/lib/impliedSpreadAxis";

const LIVE = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/impliedSpread.14780544.live.json"),
    "utf8"
  )
);

function seriesAttr(markup: string, attr: string): string | null {
  const m = markup.match(new RegExp(`${attr}="([^"]*)"`));
  return m ? m[1] : null;
}

function renderChart(
  wire: Record<string, unknown>,
  overrides: Record<string, unknown> = {}
): string {
  return renderToStaticMarkup(
    React.createElement(ScoreDifferentialChart, {
      history: wire.history as never,
      homeTeam: wire.home_team as string,
      awayTeam: wire.away_team as string,
      commenceTime: wire.commence_time as string,
      scoreHistory: wire.score_history as never,
      eventStatus: wire.status as string,
      sportKey: "americanfootball_nfl",
      pmSpreadData: wire.pm_spread_data as never,
    } as never)
  );
}

/** A believed arm, varied per assertion. Built rather than read so the clause
 *  under test is the only thing that moves. */
const arm = (confidence?: number) => ({
  spread: -6.7,
  home_margin: 6.7,
  ...(confidence === undefined ? {} : { confidence }),
});

describe("#7660 — the wire this is about", () => {
  // Strawman guards. Every assertion in this file is about numbers on a
  // captured payload; if the capture stops carrying them the file goes quietly
  // vacuous, which is the one way a guard fails without anyone noticing.
  it("the fixture still holds the specimen, defect and all", () => {
    const arms = LIVE.pm_spread_data.implied_spreads;
    expect(LIVE.status).toBe("live");
    expect(LIVE.home_team).toBe("Kansas City Chiefs");
    expect(Object.keys(arms)).toEqual(["kalshi", "polymarket", "sportsbook"]);

    // The distrusted arm, and the value the reader saw drawn from it.
    expect(arms.kalshi.confidence).toBe(0.2);
    expect(arms.kalshi.home_margin).toBe(0.3);
    // The believed arm beside it, which must survive the gate.
    expect(arms.polymarket.confidence).toBe(0.97);
    expect(arms.polymarket.home_margin).toBe(6.7);

    // The scoreboard at capture: Chiefs by 4. Neither +0.3 nor a tie.
    const last = LIVE.score_history[LIVE.score_history.length - 1];
    expect(last.home_score - last.away_score).toBe(4);
  });

  it("the withheld arm's own ladder crosses 0.50 at 7.5, not at zero", () => {
    // The point of the whole issue: the number withheld is not merely
    // low-confidence, it disagrees with the rungs it claims to summarise. If
    // this ever stops being true the fixture has been refreshed and the file
    // is describing a payload it no longer contains.
    const rungs: { threshold: number; probability: number }[] =
      LIVE.pm_spread_data.implied_spreads.kalshi.contracts;
    const halfPoint = rungs
      .filter((r) => Math.abs(r.threshold % 1) === 0.5)
      .sort((a, b) => a.threshold - b.threshold);

    const crossing = halfPoint.find((r) => r.probability < 0.5);
    expect(crossing?.threshold).toBe(7.5);

    // And the contradiction that drags the served value to ~0 is present.
    const atOne = rungs.filter((r) => r.threshold === 1.0).map((r) => r.probability);
    expect(atOne).toHaveLength(2);
    expect(atOne[0]).not.toBe(atOne[1]);
  });
});

describe("#7660 — the rule", () => {
  it("draws an arm the producer believes, and withholds one it does not", () => {
    expect(impliedSpreadArmIsTrusted(arm(0.97))).toBe(true);
    expect(impliedSpreadArmIsTrusted(arm(0.2))).toBe(false);
  });

  it("the floor is a floor — the boundary value draws", () => {
    // A `>` where `>=` belongs is invisible on the production values (0.2/0.3
    // against 0.95/0.97/1.0 leave the boundary untested by every real arm).
    expect(MIN_CONFIDENCE).toBe(0.5);
    expect(impliedSpreadArmIsTrusted(arm(MIN_CONFIDENCE))).toBe(true);
    expect(impliedSpreadArmIsTrusted(arm(MIN_CONFIDENCE - 0.01))).toBe(false);
  });

  it("an arm that states no confidence is drawn — absence is not a low score", () => {
    // Refusing an unmarked arm would silently widen this gate the day the
    // producer drops or renames the field, and it would look like working code.
    expect(impliedSpreadArmIsTrusted(arm(undefined))).toBe(true);
    expect(drawnImpliedSpreadSources({ polymarket: arm(undefined) }, false)).toEqual([
      "polymarket",
    ]);
  });

  it("a believed arm is still withheld once the game is final (#6142 stands)", () => {
    // The two clauses are independent, and this ship must not have weakened
    // the older one into "low confidence only".
    expect(drawnImpliedSpreadSources({ polymarket: arm(0.97) }, true)).toEqual([]);
  });
});

describe("#7660 — the chart, on the production wire", () => {
  it("THE SHIP: the live Chiefs–Colts page draws no Kalshi Implied line", () => {
    const drawn = seriesAttr(renderChart(LIVE), "data-implied-spread-series");
    expect(drawn).not.toContain("kalshi");
  });

  it("and still draws the believed arm beside it — a filter, not a blackout", () => {
    const markup = renderChart(LIVE);
    expect(seriesAttr(markup, "data-implied-spread-series")).toBe("polymarket");
    // The card is a real card, not an error stub that would satisfy the ship
    // assertion for the worst possible reason.
    expect(seriesAttr(markup, "data-actual-series")).toBe("true");
    expect(seriesAttr(markup, "data-projected-series")).toBe("true");
    expect(markup).not.toContain("Score data is not available");
  });

  it("THE DIFFERENTIAL: `confidence` is the only field that decides it", () => {
    // Identical bytes, one number changed. A gate keyed on the source name, on
    // the ladder's shape, on the rung count or on anything else the kalshi arm
    // merely happens to carry passes the ship assertion and fails this one.
    const believedKalshi = JSON.parse(JSON.stringify(LIVE));
    believedKalshi.pm_spread_data.implied_spreads.kalshi.confidence = 0.97;

    expect(seriesAttr(renderChart(LIVE), "data-implied-spread-series")).toBe(
      "polymarket"
    );
    expect(
      seriesAttr(renderChart(believedKalshi), "data-implied-spread-series")
    ).toBe("kalshi,polymarket");
  });

  it("THE COST: a non-final game whose arms are all distrusted draws none", () => {
    // Asserted, not glossed. #6142's scheduled control is exactly this case,
    // and it is the coverage this ship knowingly gave up.
    const allDistrusted = JSON.parse(JSON.stringify(LIVE));
    allDistrusted.pm_spread_data.implied_spreads.polymarket.confidence = 0.2;

    expect(
      seriesAttr(renderChart(allDistrusted), "data-implied-spread-series")
    ).toBe("none");
  });
});
