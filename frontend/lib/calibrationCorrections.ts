import type { CalibrationCorrection } from "./api";

/**
 * Reading order for `/calibration`'s **data corrections log** (#7599).
 *
 * WHY THIS EXISTS.
 *
 * The card's intro names the date as the log's organising fact — *"Every
 * data-quality correction we've made is on the record here, **dated**"* — and
 * every entry leads with that date, in monospace, in a fixed-width column of
 * its own. The page then rendered `data.corrections.map(...)`: the payload
 * array, verbatim, with no ordering step.
 *
 * On the live payload (q271, `generated_at` 2026-09-15T11:16Z) twelve of the
 * thirteen entries are oldest-first and the SECOND one is not — `2026-07-08`
 * (Premature golf resolutions) sits below `2026-07-09` (Polymarket hockey
 * sign-flip). A list that is monotone except for one row does not read as
 * unordered; it reads as a list that lost a row's place, on the page whose
 * whole subject is whether our numbers can be checked.
 *
 * ── WHY THE ORDER IS DECIDED HERE AND NOT UPSTREAM ──────────────────────────
 *
 * The backend list grows by hand. Re-sorting the thirteen rows it publishes
 * today fixes today and nothing after it: the next entry appended in the wrong
 * place is this defect again. Presentation order is the page's, so the page
 * takes it, and it takes it once — a sort at the call site would be a rule with
 * no test, which is how the page got here.
 *
 * ── THE TWO PROPERTIES THAT ARE NOT OBVIOUS ─────────────────────────────────
 *
 * **Oldest first, not newest first.** The list is already 12/13 oldest-first,
 * so preserving that direction moves exactly ONE row, which is a claim an
 * after-LOOK can check by eye. Reversing the log is a separate presentation
 * call that would move all thirteen and make "is it ordered now?" unanswerable
 * from a screenshot.
 *
 * **Stable in ties.** Five entries share `2026-07-09` and two share
 * `2026-09-12`. A stable sort leaves those in the sequence the backend
 * published, so no row moves except the one that is wrong. `Array.prototype.sort`
 * has been required to be stable since ES2019, and the comparator below returns
 * 0 on equal dates rather than reaching for a second key — inventing a
 * tie-break (title, row count) would reorder rows this fix has no opinion
 * about.
 *
 * ── THE DATES ARE COMPARED AS STRINGS, DELIBERATELY ─────────────────────────
 *
 * `date` is an ISO `YYYY-MM-DD` day, so lexicographic order IS chronological
 * order and the comparison needs no parse. `new Date(...)` would buy nothing
 * and would cost the one thing that matters here: a value it cannot parse
 * becomes `NaN`, every comparison against `NaN` is false, and the row lands
 * wherever the sort happened to leave it — a malformed date would be shuffled
 * silently rather than left where the payload put it. A string compare has no
 * such state: an unexpected shape sorts by its own text, deterministically.
 *
 * The one case worth naming: an entry with a missing or empty `date` sorts
 * before every real one. That is the right way to be wrong — a dateless row in
 * a log the page calls "dated" is visible at the top rather than buried at a
 * position nobody can predict.
 */
export function orderCorrections(
  corrections: readonly CalibrationCorrection[] | null | undefined,
): CalibrationCorrection[] {
  if (!corrections || !corrections.length) return [];
  return [...corrections].sort((a, b) => {
    const da = a?.date ?? "";
    const db = b?.date ?? "";
    // Not `localeCompare`: these are machine dates, and a locale-aware collator
    // is free to treat the separators as ignorable punctuation.
    if (da < db) return -1;
    if (da > db) return 1;
    return 0;
  });
}
