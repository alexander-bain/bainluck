/**
 * propResolution — a settled prop's verdict, expressed on the OVER axis.
 *
 * UX-P105 (#2011). THE DIVERGENCE draws every bar in over-probability space:
 * `over_probability` and `pregame_mark` are both the price of the OVER side,
 * and the backend already normalises them that way — a Polymarket row whose
 * `outcome_name` is "Under" still ships the OVER price. So a settled bar that
 * wants to end at the resolution needs the resolution on that same axis.
 *
 * ── WHY THIS MODULE EXISTS, AND WHY IT IS NOT ONE LINE ──
 *
 * #2011's scope section prescribes, verbatim, "resolution is 1.0 for HIT and
 * 0.0 for MISS". Measured against 12 settled production events before writing
 * any of it, that rule is WRONG ON 9 OF 57 typed rows (15.8%), every one of
 * them a Polymarket "Under" leg — because `hit` types the verdict of THE ROW'S
 * OWN OUTCOME, not of the over side the price is quoted on:
 *
 *     Ozzie Albies: Home Runs O/U 0.5 | outcome "Under"
 *        over_probability 0.085 · pregame_mark 0.085 · actual 0 · hit TRUE
 *
 *     -> the UNDER hit (he hit no home runs). The OVER resolved NO.
 *        Surprise is |0 - 0.085| = 8.5 points.
 *        #2011's rule reads `hit: true` and computes |1 - 0.085| = 91.5,
 *        then ranks the least surprising prop on the page FIRST.
 *
 * That is the same inversion #2011 is written to remove, re-created at 15.8%
 * of rows and pointing the other way. The issue's own second specimen IS this
 * row, described as "the biggest upset in the game"; it is a 8.5-point
 * non-event, and the flat bar it draws today is telling the truth about it.
 * (The issue's FIRST specimen — Freddie Freeman 3+, 93% -> MISS — is correct,
 * and so is its central claim; see `propDivergence.ts` for the ranking fix.)
 *
 * ── THE CROSS-CHECK, BECAUSE A MAPPING RULE NEEDS A SECOND SIGNAL ──
 *
 * The side-mapping was not adopted on inspection. Every typed row also ships
 * `actual` (the statistic's realised value) and `threshold`, which resolve the
 * over side INDEPENDENTLY of `hit`. Over 12 settled production events:
 *
 *     57 typed rows · 57 agree · 0 disagree · 0 unverifiable
 *
 * `actual` is used ONLY as that oracle, in the tests. Production code never
 * derives a verdict from a box-score number — that is adjudication, and
 * ruling 003 puts it out of bounds for a client. This module reads the typed
 * `hit` the backend published and does one thing to it: states it on the axis
 * the price is already quoted on.
 *
 * ── REFUSAL BY CONSTRUCTION ──
 *
 * An outcome label this module cannot place on the over axis yields NO
 * resolution, never a guessed one. Ratified as the resolution pattern this
 * cycle (Fable, cycle 102 ruling (a)): the #2001 near-miss shipped 11.6% wrong
 * ids because a plausible fallback looked harmless. Measured coverage of the
 * parser over 587 production prop rows: 586 placed, 1 refused (a row whose
 * `outcome_name` is a matchup string, which `parsePlayerName` rejects anyway).
 *
 * PURE — no I/O, no clock, no React.
 */

import { readPropGrade, type PropGrade, type PropGradeFields } from "./propGrade";

/** Which side of the line an outcome label names, in over-probability space. */
export type PropOutcomeSide = "over" | "under" | "unreadable";

/** Kalshi's inclusive ladder rung: "Freddie Freeman: 3+", "Willi Castro: 2+". */
const RUNG_RE = /\d+\s*\+/;

/**
 * Place an outcome label on the over axis.
 *
 * Three shapes cover 586 of 587 production rows:
 *   - Polymarket O/U legs: "Over" / "Under"
 *   - Polymarket binary legs: "Yes" / "No"
 *   - Kalshi rungs: "<Player>: N+" — inclusive, and therefore the over side
 */
export function propOutcomeSide(outcomeName?: string | null): PropOutcomeSide {
  const o = (outcomeName || "").trim().toLowerCase();
  if (!o) return "unreadable";
  if (o === "over" || o === "yes") return "over";
  if (o === "under" || o === "no") return "under";
  if (RUNG_RE.test(o)) return "over";
  return "unreadable";
}

/**
 * One `player_props[]` row's grading fields restated on the over axis.
 *
 * `hit` is flipped for an under-side leg and passed through for an over-side
 * one. `actual` is NOT side-dependent (it is the statistic, not a verdict) and
 * travels unchanged, so `readPropGrade`'s ACTUAL_ONLY state still means what it
 * means. An unreadable side contributes NOTHING — not a `false`, which is the
 * defaulted-`is_winner` mistake #1638 already paid for.
 */
export function toOverSideGradeFields(row: {
  outcome_name?: string | null;
  hit?: boolean | null;
  actual?: number | null;
  is_winner?: boolean | null;
  resolution_source?: string | null;
}): PropGradeFields | null {
  const side = propOutcomeSide(row.outcome_name);
  if (side === "unreadable") return null;
  const hit = row.hit == null ? null : side === "over" ? row.hit : !row.hit;
  return {
    hit,
    actual: row.actual ?? null,
    // `is_winner` and `resolution_source` are carried so the shape stays a
    // PropGradeFields, but propGrade deliberately reads neither as a verdict.
    is_winner: row.is_winner ?? null,
    resolution_source: row.resolution_source ?? null,
  };
}

export interface OverSideResolution {
  /** The full grade, from `readPropGrade` — imported, never restated. */
  grade: PropGrade;
  /**
   * Where the question actually landed on the over axis: 1 when the over
   * resolved YES, 0 when it resolved NO, `null` when nothing may be stated.
   */
  resolution: 0 | 1 | null;
}

/**
 * The over-axis resolution for one question, across every leg that describes
 * it.
 *
 * Both legs of a Polymarket O/U are normally present and, once mapped, AGREE
 * (Albies: "Under" hit true and "Over" hit false both say the over resolved
 * NO). They are reconciled rather than assumed to agree, and a disagreement
 * withholds — which is `readPropGrade`'s existing conflicting-rungs rule doing
 * the work, not a second opinion invented here.
 */
export function readOverSideResolution(
  rows: readonly {
    outcome_name?: string | null;
    hit?: boolean | null;
    actual?: number | null;
    is_winner?: boolean | null;
    resolution_source?: string | null;
  }[],
): OverSideResolution {
  const mapped = rows
    .map(toOverSideGradeFields)
    .filter((f): f is PropGradeFields => f !== null);

  // Every leg was unreadable: there is nothing to grade, and saying so is not
  // the same as saying "no grade was published".
  if (mapped.length === 0) {
    return { grade: readPropGrade([]), resolution: null };
  }

  const grade = readPropGrade(mapped);
  const resolution = grade.state === "HIT" ? 1 : grade.state === "MISS" ? 0 : null;
  return { grade, resolution };
}
