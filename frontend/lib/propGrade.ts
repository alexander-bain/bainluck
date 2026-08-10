/**
 * propGrade — is a settled prop actually GRADED, or merely resolved?
 *
 * UX-P040 (#1638). A finished game page was printing a red MISS on 25 props the
 * backend never graded, because the client read `is_winner` as a verdict:
 *
 *   const hasGrade = actual != null || is_winner != null;   // false != null → true
 *
 * `is_winner` is a non-nullable column whose default is `false`. On a row that
 * was never graded it is indistinguishable from "graded a loser" — the
 * never-graded cohort carries exactly that shape (resolution_source NULL,
 * is_winner defaulted false). Production event 15191121 returned 25 of 25
 * player props as `actual: null, hit: null, is_winner: false,
 * resolution_source: null`, and every one of them rendered MISS.
 *
 * The field that CAN tell them apart was already typed and already on the wire
 * (`resolution_source`, api.ts) and simply was not read. So this module reads
 * the backend's typed decision rather than deriving one — ruling 003 (clients
 * format, never adjudicate). It deliberately does NOT look at a box score:
 * grading a prop from a box score by matching player names is adjudication, and
 * is the named failure that ruling exists to prevent.
 *
 * PURE — no I/O, no React.
 */

/** The grading-relevant subset of a `player_props[]` row. */
export interface PropGradeFields {
  actual?: number | null;
  hit?: boolean | null;
  is_winner?: boolean | null;
  resolution_source?: string | null;
}

export type PropGrade =
  /** The backend published a grade. `hit` may still be null when only `actual` landed. */
  | { graded: true; hit: boolean | null; actual: number | null }
  /** Resolved, but no grade was published — render the honest fallback. */
  | { graded: false };

/** Non-empty string, tolerating a whitespace-only value from the wire. */
function hasResolutionSource(row: PropGradeFields): boolean {
  return typeof row.resolution_source === "string" && row.resolution_source.trim() !== "";
}

/**
 * Did the backend publish grading EVIDENCE for this row?
 *
 * Evidence is a non-null `actual`, a non-null `hit`, or a resolution source.
 * A bare `is_winner` is NOT evidence — see the module header. `is_winner` is
 * still believed once something else establishes that grading happened.
 */
export function hasGradeEvidence(row: PropGradeFields): boolean {
  return row.actual != null || row.hit != null || hasResolutionSource(row);
}

/**
 * Read the grade for one player+stat from every row that carries it.
 *
 * Rows are the thresholds of a single stat (a ladder's rungs, or one O/U line);
 * they share an `actual`, and any of them may be the one that carries the
 * resolution source. The first row with real evidence wins, matching the
 * existing first-rung-wins behaviour for genuinely graded props.
 */
export function readPropGrade(rows: readonly PropGradeFields[]): PropGrade {
  const evidenced = rows.filter(hasGradeEvidence);
  if (evidenced.length === 0) return { graded: false };

  const actual = evidenced.find((r) => r.actual != null)?.actual ?? null;
  const explicitHit = evidenced.find((r) => r.hit != null)?.hit ?? null;

  if (explicitHit != null) return { graded: true, hit: explicitHit, actual };

  // Only now is `is_winner` meaningful: something else proved grading happened.
  const sourced = evidenced.find((r) => hasResolutionSource(r) && r.is_winner != null);
  if (sourced) return { graded: true, hit: sourced.is_winner as boolean, actual };

  // `actual` alone: a real number to show, but no verdict to state.
  return { graded: true, hit: null, actual };
}
