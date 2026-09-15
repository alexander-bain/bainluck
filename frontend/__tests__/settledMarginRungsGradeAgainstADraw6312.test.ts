/**
 * #6312 (consumer half) — the rows the backend readmits land in a renderer that
 * is already waiting for them.
 *
 * `/events/15306857` (Gwangju FC 1 · FC Anyang 1, Final) served `spreads: []`
 * while holding a settled, fully graded Kalshi Spread market whose four legs all
 * lost. The backend half of #6312 puts those four rows in the payload.
 *
 * THE QUESTION THIS FILE ANSWERS IS "AND THEN WHAT DOES THE READER SEE?" —
 * #6110's lesson, one ship later: a repair that reaches the payload and not the
 * page is half a repair. The margin map's grader (`gradeMarginRung`, #6203) does
 * the SAME subtraction the backend's `margin_verdict_from_final_score` does, and
 * `ladderGraded` turns the ladder from quotes into verdicts only when EVERY rung
 * knows how it finished. Both are exercised here against the served rows
 * verbatim, so "the page can say `not cleared` about these four lines" is a
 * measured fact and not a reading of the component.
 *
 * It is a pure-helper test on purpose. The layout files are ux's (notice 41) and
 * nothing here edits or asserts their markup; these are the two exported
 * functions that decide what the ladder MEANS.
 */

import { parseSpreadRungs, isFullGameSpread } from "@/lib/marketMapUtils";
import { ladderGraded, type MarketMapLadderRow } from "@/components/MarketMap";
import { gradeMarginRung } from "@/components/MarketMapSection";

const HOME = "Gwangju FC";
const AWAY = "FC Anyang";

/** `SPORT_SCORING`'s declared unit for soccer — the PLURAL, which is what
 *  `spreadUnitOf` normalises an outcome's "goals" to and what the rail passes. */
const SOCCER_RAIL_UNIT = "goals";

/** The four rows the backend now serves, verbatim (market 60672667). */
const SERVED_SPREADS = [
  { market_name: "Gwangju vs FC Anyang: Spread", outcome_name: "FC Anyang wins by more than 1.5 goals", probability: 0.0, source: "kalshi" },
  { market_name: "Gwangju vs FC Anyang: Spread", outcome_name: "FC Anyang wins by more than 2.5 goals", probability: 0.0, source: "kalshi" },
  { market_name: "Gwangju vs FC Anyang: Spread", outcome_name: "Gwangju wins by more than 1.5 goals", probability: 0.0, source: "kalshi" },
  { market_name: "Gwangju vs FC Anyang: Spread", outcome_name: "Gwangju wins by more than 2.5 goals", probability: 0.0, source: "kalshi" },
];

/** 1–1. The margin the whole card is graded against. */
const FINAL_MARGIN = 0;

describe("#6312 — a draw's readmitted spread rungs reach the margin ladder", () => {
  it("all four rows survive the full-game filter and the unit rail", () => {
    const fullGame = SERVED_SPREADS.filter((s) => isFullGameSpread(s.market_name));
    expect(fullGame).toHaveLength(4);

    const parsed = parseSpreadRungs(fullGame, HOME, AWAY, SOCCER_RAIL_UNIT);
    expect(parsed).toHaveLength(4);
  });

  it("each side is resolved to its own end of the rail", () => {
    const parsed = parseSpreadRungs(SERVED_SPREADS, HOME, AWAY, SOCCER_RAIL_UNIT);
    // 🔴 The inversion that would put a verdict under the wrong club's name:
    // "Gwangju" must not match "FC Anyang" through the shared token "FC".
    expect(parsed.filter((p) => p.isHome).map((p) => p.threshold).sort()).toEqual([1.5, 2.5]);
    expect(parsed.filter((p) => !p.isHome).map((p) => p.threshold).sort()).toEqual([1.5, 2.5]);
  });

  it("every rung grades as missed against a 1–1 draw", () => {
    const parsed = parseSpreadRungs(SERVED_SPREADS, HOME, AWAY, SOCCER_RAIL_UNIT);
    for (const p of parsed) {
      expect(gradeMarginRung(FINAL_MARGIN, p.isHome, p.threshold)).toBe("missed");
    }
  });

  it("the ladder is FULLY graded, so it prints verdicts and not a row of 0%", () => {
    /* `ladderGraded` is all-or-nothing by design (#3769): a partially graded
       ladder puts "cleared" beside "0%" and invites the reader to compare them.
       These four rows are the whole market, so the card has one tense. */
    const parsed = parseSpreadRungs(SERVED_SPREADS, HOME, AWAY, SOCCER_RAIL_UNIT);
    const ladder: MarketMapLadderRow[] = parsed.map((p) => ({
      label: `${p.isHome ? "GWA" : "ANY"} by ${p.threshold}+`,
      probability: Math.round(p.probability * 100),
      side: p.isHome ? "right" : "left",
      outcome: gradeMarginRung(FINAL_MARGIN, p.isHome, p.threshold),
    }));

    expect(ladderGraded(ladder)).toBe(true);
    expect(ladder.map((r) => r.outcome)).toEqual(["missed", "missed", "missed", "missed"]);
  });

  it("the same rungs against a 3–0 home win grade in both directions", () => {
    /* 🔴 The anti-strawman: a grader that answered "missed" to everything would
       satisfy every assertion above. Only a scoreline that clears some lines and
       not others can tell the arithmetic from a constant. */
    const parsed = parseSpreadRungs(SERVED_SPREADS, HOME, AWAY, SOCCER_RAIL_UNIT);
    const outcomes = parsed.map((p) => [
      `${p.isHome ? "GWA" : "ANY"} ${p.threshold}`,
      gradeMarginRung(3, p.isHome, p.threshold),
    ]);
    expect(Object.fromEntries(outcomes)).toEqual({
      "GWA 1.5": "cleared",
      "GWA 2.5": "cleared",
      "ANY 1.5": "missed",
      "ANY 2.5": "missed",
    });
  });

  it("an ungraded rail still quotes, so nothing here fires before full time", () => {
    /* `gradeMarginRung` returns `undefined` with no final margin, and a ladder
       with one ungraded rung is not a graded ladder. A live game's card is
       untouched by the backend carve-out and by this contract. */
    const parsed = parseSpreadRungs(SERVED_SPREADS, HOME, AWAY, SOCCER_RAIL_UNIT);
    const ladder: MarketMapLadderRow[] = parsed.map((p) => ({
      label: `${p.isHome ? "GWA" : "ANY"} by ${p.threshold}+`,
      probability: Math.round(p.probability * 100),
      side: p.isHome ? "right" : "left",
      outcome: gradeMarginRung(null, p.isHome, p.threshold),
    }));
    expect(ladderGraded(ladder)).toBe(false);
  });
});
