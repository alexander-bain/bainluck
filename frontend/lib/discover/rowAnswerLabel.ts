/**
 * #4396 — a bundle row's percentage says which answer it belongs to.
 *
 * `FuturesCompactRow` is the row page one actually shows, five to a bundle. It
 * prints the question on the left, a caption under it, and the hero percentage
 * on the right. Nothing on the row says WHICH outcome that percentage is for.
 *
 * 🔴 MEASURED on the live feed 2026-09-09 09:35 PT (`GET /api/feed?limit=250`,
 * edition `b433c96f31941ab7`, the 22 futures rows rendered through this row on
 * page one). **7 of 22 print a percentage whose outcome is named nowhere:**
 *
 *   How many Fed rate cuts in 2026?       93%  ← `0 (0 bps)`   "Well off its opening price"
 *   How many dissent at the Oct Fed …?    25%  ← `3`           "As central banks grapple with…"
 *   Russia x Ukraine ceasefire by…?       41%  ← `December 31` "Well off its opening price"
 *   FIFA Women's World Cup 2027 Winner    22%  ← `Brazil`      (no caption)
 *   Will the U.S. invade Iran before 2027?     ← `Yes`         (no caption)
 *   Will the Iranian regime fall …?            ← `Yes`         "Well off its opening price"
 *   Putin out as President of Russia …?        ← `Yes`         "Well off its opening price"
 *
 * The caption compared against is `feedContextSnippet`'s whole futures chain —
 * `context_summary`, `headline`, `reason`, `hook_description` — because the
 * fourth link is a real rendered caption: the dissent row above reads as LLM
 * hook prose, which fills the line and still names no answer.
 *
 * The Fed row is the one that made this a bug rather than a polish item: 93% is
 * the probability of **zero** cuts, and a reader scanning "How many Fed rate
 * cuts in 2026? … 93%" reads a confident yes to a question whose answer is none.
 * The same class as `heroOutcome`'s inverted binary, one component further out.
 *
 * WHY IT IS NOT UNCONDITIONAL. The other 15 of the 22 already name their outcome
 * in the caption the backend wrote — "Hike 25bps leads at 56%", "New favorite:
 * Jon Ossoff (17%)". Printing the name again beside those would put "The Odyssey"
 * on the row twice. The label is therefore the CAPTION'S GAP, not a new fixture:
 * it appears exactly where the sentence already on the row failed to say it.
 *
 * WHY A BARE `Yes` IS LEFT ALONE. "Will the U.S. invade Iran before 2027? … 12%"
 * is already a complete reading — the question states the affirmative and the
 * percentage answers it. `heroOutcome` has already flipped an inverted binary to
 * its affirmative side by the time we get here, so a hero still reading "No" is
 * one whose affirmative had no price, and that one DOES need saying.
 */

import type { HeroCandidate } from "./heroOutcome";

/**
 * The affirmative whose name the question itself already carries. Only the bare
 * word — Polymarket's `Yes: <restatement>` says something the question may not,
 * and "Yes (before June)" is a date answer wearing a yes.
 */
const BARE_AFFIRMATIVE = /^\s*yes\s*$/i;

/** Collapse whitespace and case so a caption and an outcome name compare. */
function normalize(text: string | null | undefined): string {
  return (text ?? "").replace(/\s+/g, " ").trim().toLowerCase();
}

/**
 * True when `caption` already says `name` to the reader.
 *
 * Boundary-checked rather than a bare `includes`, because outcome names on a
 * quantity market are one or two characters (`3`, `0`, `2+`) and would
 * otherwise be "found" inside any caption containing that digit. Three real
 * captions say why each side of the check is what it is:
 *
 *   "Up 13 points since Monday"   `3` must not match     -> digits join
 *   "Well off its 3-month low"    `3` must not match     -> a hyphen joins
 *   "…leads at 25%"               `25` must not match    -> a trailing % is a
 *                                                           price, not an answer
 *   "0 (0 bps) leads at 93%"      `0 (0 bps)` MUST match -> a needle whose own
 *                                                           edge is punctuation
 *                                                           needs no boundary
 *
 * A boundary is required only on the sides of the NEEDLE that are themselves
 * word characters, which is what lets `0 (0 bps)` butt against anything.
 */
const JOINS_BEFORE = /[a-z0-9-]/;
const JOINS_AFTER = /[a-z0-9\-%]/;

export function captionNames(caption: string | null | undefined, name: string | null | undefined): boolean {
  const hay = normalize(caption);
  const needle = normalize(name);
  if (!hay || !needle) return false;

  const isWordChar = (ch: string) => /[a-z0-9]/.test(ch);
  let from = 0;
  for (;;) {
    const at = hay.indexOf(needle, from);
    if (at < 0) return false;
    const before = at === 0 ? "" : hay[at - 1];
    const after = hay[at + needle.length] ?? "";
    const headOk = !isWordChar(needle[0]) || before === "" || !JOINS_BEFORE.test(before);
    const tailOk = !isWordChar(needle[needle.length - 1]) || after === "" || !JOINS_AFTER.test(after);
    if (headOk && tailOk) return true;
    from = at + 1;
  }
}

/**
 * The outcome name a compact row must print beside its percentage, or `null`
 * when the row already reads correctly without one.
 *
 * @param hero    the outcome the percentage speaks for (`heroOutcome`'s pick)
 * @param caption the sentence already rendered under the question
 */
export function rowAnswerLabel(
  hero: HeroCandidate | null | undefined,
  caption: string | null | undefined,
): string | null {
  const name = (hero?.name ?? "").replace(/\s+/g, " ").trim();
  if (!name) return null;
  if (BARE_AFFIRMATIVE.test(name)) return null;
  if (captionNames(caption, name)) return null;
  return name;
}
