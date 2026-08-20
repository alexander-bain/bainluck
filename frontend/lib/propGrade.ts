/**
 * propGrade — the ONE settled-state authority for a prop.
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
 * UX-P044 (#1642). That fix left a SECOND shape of the same failure: it treated
 * a `resolution_source` as licence to believe `is_winner`. A resolution source
 * proves only that *some settlement process touched the row* — it does not type
 * the verdict, and it cannot express void, push, or partial settlement.
 * Measured on 19 settled production events / 358 rendered cards: **70 showed a
 * red MISS** built from a generic source plus a defaulted `false`, and 3 showed
 * a HIT the same way. The mechanism is plain — `_grade_settled_prop`
 * (`app/routes/events.py`) passes `is_winner` / `resolution_source` straight
 * through from the outcome row, while `actual` / `hit` are derived ONLY from the
 * box score, so "source set, `hit` null" is exactly a box-score lookup miss.
 *
 * So the rule this module enforces is the narrow one:
 *
 *     only `hit` types a verdict.
 *
 * Everything else is withheld. That is the landed corpus oracle
 * `backend/scripts/evals/settled_prop_grade_authority_contract.py` (`e33cf7aa`),
 * and it is ruling 003 — clients format, never adjudicate. This module
 * deliberately does NOT look at a box score: grading a prop by matching player
 * names is adjudication, and is the named failure that ruling exists to prevent.
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

/**
 * The single settled-state phrase, for every surface that has to say it.
 *
 * Exported so the prop card and the WHAT HIT row cannot drift apart. #1650 was
 * one backend state wearing three vocabularies on one screen ("Resolved ·
 * grading unavailable" on the card / "grading pending" in WHAT HIT / a header
 * asserting "graded"), and UX-P043 had just finished paying for the twin of
 * that bug in the browser-audit rail: two graders reading one input and
 * disagreeing, because each restated the other's rule instead of importing it.
 */
export const SETTLED_NO_GRADE_LABEL = "Resolved · grading unavailable";

/**
 * The two settled verdicts, in the site's one settled vocabulary.
 *
 * UX-P105 (#2011). These words were literals in `PlayerPropsDashboard` and
 * `TotalPointsSpectrum`, and THE DIVERGENCE rail's first draft invented a third
 * pair ("HAPPENED" / "DIDN'T HAPPEN") — on a screen that already shows all
 * three surfaces stacked, which is #1650 exactly: one backend state wearing
 * three vocabularies. It was caught in the rendered screenshot, not in a test,
 * which is the argument for the constant rather than for more review.
 *
 * Alex's standing ruling is one system-wide settled language. That can only be
 * enforced by there being one place the words live.
 */
export const PROP_HIT_LABEL = "HIT";
export const PROP_MISS_LABEL = "MISS";

/**
 * The third settled verdict, and the reason this constant exists at all.
 *
 * UX-P106. `readPropGrade` deliberately does not MODEL a push — it never
 * manufactures one — but the backend types `graded_result: "push"` and
 * `PropsSection` has been rendering it as a bare `"Push"` literal, alongside
 * `"Hit"` / `"Miss"` literals, in a file the UX-P105 guard's hard-coded
 * three-file list did not cover. So the site was already carrying a fourth
 * settled vocabulary — title case, on the WHAT HIT section, on the same screen
 * as the rail's `HIT` and the cards' `HIT`. Not modelling a verdict is not a
 * reason to leave its WORD un-owned.
 */
export const PROP_PUSH_LABEL = "PUSH";

/** The verdict word for a typed `hit`. */
export function propVerdictLabel(hit: boolean): string {
  return hit ? PROP_HIT_LABEL : PROP_MISS_LABEL;
}

/**
 * The verdict word for a backend `graded_result`, including the push this
 * module does not adjudicate but must still SPELL consistently.
 */
export function propResultLabel(result: "hit" | "miss" | "push"): string {
  if (result === "push") return PROP_PUSH_LABEL;
  return propVerdictLabel(result === "hit");
}

/**
 * ── THE SETTLED VOCABULARY REGISTRY ──────────────────────────────────────────
 *
 * Every word or phrase this site is permitted to use to state the settled state
 * of a prop. Nothing else may appear in the verdict slot on any surface.
 *
 * WHY A REGISTRY AND NOT MORE REVIEW. The near-miss that produced it: THE
 * DIVERGENCE rail's first draft returned "HAPPENED" / "DIDN'T HAPPEN", a third
 * pair on a screen that already stacks three settled surfaces. It was caught in
 * a rendered screenshot and by NO test — and the guard that shipped with the fix
 * could not have caught it either, because it banned the words it already knew
 * (`HIT`, `MISS`) in the three files it already knew. A guard shaped like a
 * denylist of known-good words is structurally unable to see a NEW pair; that is
 * the whole failure mode.
 *
 * So the guard inverts: `__tests__/lib/settledVocabulary.test.tsx` renders each
 * settled surface twice with the verdict discriminant flipped and nothing else
 * changed, and asserts that every token which DIFFERS between the two renders is
 * in this list. A fourth vocabulary is, by construction, a pair of strings that
 * differ between hit and miss — so it lands in that difference set and reds the
 * suite without anyone having predicted the word.
 *
 * Verb forms are here because aria-labels and THE DIVERGENCE's prose state the
 * same verdict in a sentence ("… and it missed."). A screen reader is a rendered
 * surface; inventing a fourth vocabulary there is the same defect, unscreenshot-
 * able.
 */
export const SETTLED_VOCABULARY: readonly string[] = Object.freeze([
  PROP_HIT_LABEL,
  PROP_MISS_LABEL,
  PROP_PUSH_LABEL,
  SETTLED_NO_GRADE_LABEL,
  // Verb / sentence forms of the SAME three verdicts.
  "hit",
  "hits",
  "missed",
  "miss",
  "push",
  "pushed",
]);

const SETTLED_VOCABULARY_WORDS: ReadonlySet<string> = new Set(
  SETTLED_VOCABULARY.flatMap((phrase) =>
    // A multi-word phrase is admissible whole AND word-by-word, because the
    // census tokenises rendered text and `SETTLED_NO_GRADE_LABEL` arrives as
    // "Resolved", "·", "grading", "unavailable".
    [phrase, ...phrase.split(/[^A-Za-z0-9'’+-]+/)],
  ).filter(Boolean),
);

/**
 * Is this rendered token part of the one settled vocabulary?
 *
 * CASE-SENSITIVE, and that is the point rather than an oversight. The registry
 * lists `HIT` and `hit` as separate admissible entries — the badge form and the
 * sentence form — so a surface that renders a title-case `"Hit"` is caught. That
 * is not pedantry: title-case `"Hit"` / `"Push"` / `"Miss"` is precisely the
 * fourth vocabulary UX-P106 found already shipped in the WHAT HIT section, on
 * the same screen as the rail's `HIT`. A guard that folded case would have
 * looked at it and seen nothing.
 *
 * Edge punctuation is stripped first: the sentence form arrives as `missed.`
 * with the full stop attached, and a full stop is not a word.
 */
export function isSettledVocabularyToken(token: string): boolean {
  const word = token.trim().replace(/^[^A-Za-z0-9]+/, "").replace(/[^A-Za-z0-9'’+]+$/, "");
  // A token that is ENTIRELY symbol is not admissible here. `✓` versus `✗` is a
  // settled vocabulary with no letters in it, and answering "no letters, so
  // nothing to check" is how the glyph pair survived in
  // `PlayerPropsDashboard`. Punctuation that genuinely carries no verdict never
  // reaches this function — the census discards it as data first.
  return SETTLED_VOCABULARY_WORDS.has(word);
}

export type PropGradeReason =
  | "explicit_hit"
  | "no_explicit_verdict"
  | "no_typed_grade"
  | "conflicting_rung_verdicts"
  | "mixed_entity_group";

/** The reasons that carry no renderable verdict. */
export type PropWithholdReason = Exclude<
  PropGradeReason,
  "explicit_hit" | "no_explicit_verdict"
>;

export type PropGrade =
  /** The backend typed a verdict for this prop. */
  | { state: "HIT"; reason: "explicit_hit"; hit: true; actual: number | null }
  | { state: "MISS"; reason: "explicit_hit"; hit: false; actual: number | null }
  /** A real number to show, but no verdict to state. */
  | { state: "ACTUAL_ONLY"; reason: "no_explicit_verdict"; hit: null; actual: number }
  /** Nothing may be stated — render `SETTLED_NO_GRADE_LABEL`. */
  | { state: "WITHHOLD"; reason: PropWithholdReason; hit: null; actual: null };

const withhold = (reason: PropWithholdReason): PropGrade => ({
  state: "WITHHOLD",
  reason,
  hit: null,
  actual: null,
});

export interface ReadPropGradeOptions {
  /**
   * False when the rows do not all describe the same player + statistic.
   *
   * The grouping key is parsed out of free text, and when that parse finds no
   * statistic and no colon the bucket is a MATCHUP rather than a person — at
   * which point one row's verdict and `actual` get attached to a different
   * player's line. A wrong name against a real stat is worse than a blank, so
   * such a group is refused outright rather than allowed to borrow evidence.
   */
  samePlayerStat?: boolean;
}

/**
 * Read the settled state for one player+stat group.
 *
 * Rows are the thresholds of a single stat (a ladder's rungs, or one O/U line).
 * A ladder can legitimately be HIT at `1+` and MISS at `2+` — one boolean
 * cannot describe that, and picking a rung makes the badge depend on input
 * order, so a disagreement withholds the GROUP verdict. Individual rungs keep
 * rendering their own typed `hit` at the call site; what is refused here is the
 * single summary badge.
 */
export function readPropGrade(
  rows: readonly PropGradeFields[],
  options?: ReadPropGradeOptions,
): PropGrade {
  if (options?.samePlayerStat === false) return withhold("mixed_entity_group");

  const hits = new Set(rows.filter((r) => r.hit != null).map((r) => r.hit as boolean));
  if (hits.size > 1) return withhold("conflicting_rung_verdicts");

  const actual = rows.find((r) => r.actual != null)?.actual ?? null;

  if (hits.size === 1) {
    return hits.has(true)
      ? { state: "HIT", reason: "explicit_hit", hit: true, actual }
      : { state: "MISS", reason: "explicit_hit", hit: false, actual };
  }

  if (actual != null) {
    return { state: "ACTUAL_ONLY", reason: "no_explicit_verdict", hit: null, actual };
  }

  return withhold("no_typed_grade");
}

/** Did the backend publish anything renderable for this group? */
export function isGraded(grade: PropGrade): boolean {
  return grade.state !== "WITHHOLD";
}

// ---------------------------------------------------------------------------
// props_script reconciliation (#1650)
//
// The event page shows the SAME settled prop twice: as a Player Props card
// (built from `player_props[]`, graded by `readPropGrade` above) and as a WHAT
// HIT row (built from `props_script[]`, graded by the BACKEND).
//
// The backend's builder — `_build_props_script`, `app/routes/events.py` —
// carries the identical defect this module just removed:
//
//     if hit is None and pp.get("resolution_source"):
//         hit = bool(is_winner)          # ← a defaulted false becomes "miss"
//
// so the two halves of one screen disagree about one prop. `routes/events.py`
// is the LATENCY lane's file (#1494) and is not this lane's to edit, so the
// page re-derives the WHAT HIT verdict from the raw typed rows that travel on
// the same payload. That is reading the backend's typed `hit`, not deriving a
// grade — ruling 003 holds. When the backend half is fixed this becomes a
// no-op rather than a second opinion.
// ---------------------------------------------------------------------------

/** A `player_props[]` row, with the two fields that form its script key. */
export interface RawPropRow extends PropGradeFields {
  market_name?: string | null;
  outcome_name?: string | null;
}

/** The subset of a `props_script[]` mark whose grade is being verified. */
export interface ScriptGradeMark {
  key?: string | number | null;
  graded_result?: "hit" | "miss" | "push" | null;
  graded_label?: string | null;
}

/**
 * Index raw prop rows by the key `_build_props_script` builds:
 * `f"{market_name}|{outcome_name}"`. Keep every row under a key — a collision
 * is then resolved by the same conflicting-rungs rule as everywhere else,
 * rather than by whichever row happened to be last.
 */
export function indexPropRowsByScriptKey(
  rows: readonly RawPropRow[] | null | undefined,
): Map<string, PropGradeFields[]> {
  const index = new Map<string, PropGradeFields[]>();
  for (const row of rows ?? []) {
    const key = `${row.market_name ?? ""}|${row.outcome_name ?? ""}`;
    const bucket = index.get(key);
    const fields: PropGradeFields = {
      actual: row.actual ?? null,
      hit: row.hit ?? null,
      is_winner: row.is_winner ?? null,
      resolution_source: row.resolution_source ?? null,
    };
    if (bucket) bucket.push(fields);
    else index.set(key, [fields]);
  }
  return index;
}

/**
 * The WHAT HIT verdict for one script mark, held to the same authority as the
 * card above it.
 *
 * Conservative on both edges: a mark the backend already left ungraded is
 * untouched, and a mark whose raw rows cannot be found passes through unchanged
 * rather than being blanked on a lookup failure. `push` is a typed verdict this
 * module does not model and never manufactures, so it is passed through too.
 */
export function verifyScriptGrade(
  mark: ScriptGradeMark,
  index: Map<string, PropGradeFields[]>,
): { graded_result: "hit" | "miss" | "push" | null; graded_label: string | null } {
  const result = mark.graded_result ?? null;
  const label = mark.graded_label ?? null;
  if (result == null || result === "push") return { graded_result: result, graded_label: label };

  const rows = mark.key == null ? undefined : index.get(String(mark.key));
  if (!rows || rows.length === 0) return { graded_result: result, graded_label: label };

  const grade = readPropGrade(rows);
  if (grade.state === "HIT") return { graded_result: "hit", graded_label: label };
  if (grade.state === "MISS") return { graded_result: "miss", graded_label: label };
  // Withheld (or an actual with no verdict): drop the label with the verdict —
  // it reads "0 — miss" and would restate the claim we just removed.
  return { graded_result: null, graded_label: null };
}
