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

/**
 * #7331 — the label above is the fix for "which answer is this percentage for?",
 * and it works while the answer is a WORD. When the answer is itself a quantity
 * the grammar collapses. Production 2026-09-19 19:4xZ, 390px, page one, the
 * FED & RATES bundle, verbatim from the rendered card:
 *
 *     Core CPI YoY - September 2026
 *     2.4% · Resolves within a month                            41%
 *
 * Two percentages on one row — an inflation RATE and a PROBABILITY — with a `·`
 * and eight inches of whitespace between them, and nothing saying which is
 * which. The row above it reads correctly for the only reason that matters: its
 * answer is the word `Hike 25bps`.
 *
 * Returning true means the row's own percentage says `chance` — the site's
 * existing word for this (`HERO_PROBABILITY_HINT` is "chance this happens", and
 * the served captions say "16% chance, up 1 point since Feb 19"). It is spent
 * only where the ambiguity is real: on the same feed 5 of the 6 labelled rows
 * name a quantity that PREFIXES A WORD (`Above 5`, `Above 45`), which states its
 * own unit and is left byte-identical. This is a copy fix for the collapsed
 * case, not a rewording of every row.
 *
 * The predicate is deliberately the same one the backend door spends on the same
 * bundle (`leader_percent_parenthetical`, `feed_reasons.py`, #7331's other half):
 * a digit and no letter. The two doors must not disagree about which row is
 * ambiguous, or one bundle prints the word on one row and withholds it on the
 * next for no reason a reader can see.
 *
 * NOT REPAIRED HERE, and measured rather than assumed: `FuturesCard`'s variant-A
 * hero stacks `leader.name` under a 38px percentage and would collapse the same
 * way, but 0 of the 76 top-level futures cards on this feed carry a bare-quantity
 * leader. A repair with no specimen is a repair nobody can measure; it is
 * recorded on #7331 instead.
 */
export function answerIsBareQuantity(label: string | null | undefined): boolean {
  const text = (label ?? "").trim();
  if (!text) return false;
  return /\p{Nd}/u.test(text) && !/\p{L}/u.test(text);
}

/**
 * Outcome names too ordinary to claim a caption. `No` is a word every third
 * sentence contains ("No clear favorite yet"), and matching it would read an
 * incidental English word as a second leg. The affirmative side never reaches
 * here — `rowAnswerLabel` has already returned null for a bare `Yes` — but it
 * is listed because the rule is about the WORD, not about which side it is on.
 */
const TOO_COMMON_TO_CLAIM = /^(yes|no|none|other|tbd|n\/a)$/i;

/**
 * #7855 — the row prints ONE number, so its caption may not be about a
 * different outcome than the label beside it.
 *
 * 🔴 WHAT A READER SAW. Production 2026-09-21 18:55Z, 390px, page one, card 6,
 * edition `9c0cbec4350ab587`, the AI bundle, verbatim from the rendered row:
 *
 *     GPT Astra 6.1+ released?
 *     December 31 · October 31 up 20 points today               94%
 *
 * Two dates, one separator, one movement and one percentage, and nothing on the
 * line says which date the 94% is for. It reads as one sentence — "December 31,
 * October 31, up 20 points today" — and is in fact two statements about two
 * different legs of a cumulative ladder: `December 31` is the outcome the 94%
 * belongs to, `October 31` is a different outcome at 63%, and the only number
 * the sentence carries ("20 points") belongs to neither of the two printed.
 *
 * WHY EVERY SHIPPED GATE ADMITS IT. `captionNames("October 31 up 20 points
 * today", "December 31")` is false, so #4396's label correctly prints;
 * `answerIsBareQuantity("December 31")` is false, so #7331's word is correctly
 * withheld. Both gates answer their own question right. Neither was ever asked
 * whether the caption is about the SAME outcome as the label. The backend's
 * `movement_subject_is_printable` (#6219) asks the nearest thing — is the
 * mover drawn on the card — and is satisfied, because October 31 IS a row on
 * the full card. This is the compact row, which draws one number and one
 * caption, so "the subject is on the card" is true of a card the reader is not
 * looking at.
 *
 * WHY THE CAPTION IS THE HALF THAT GOES. The row's contract is #4396's: say
 * which answer the percentage is for. A why-now about a leg the row does not
 * draw cannot be tied to anything the reader can see, so it is the half that
 * cannot be read — and dropping it lands the row on a shape page one already
 * serves and reads fine (`Anthropic IPO? · December 31, 2026 · 91%`, four such
 * rows in the same response). Nothing new is minted; the full card the row
 * expands into still draws both legs with the movement.
 *
 * MEASURED, not assumed: of the 33 compact rows that response served, 10 print
 * a label and exactly 1 is this. The two rows whose caption names another leg
 * AND its own hero — "Wild Horse Nine leads at 34%, The Debut up 25.8 points",
 * "Fed maintains rate at 50%, Hike 25bps up 47 points" — print NO label (the
 * caption already ties the number), so they are outside the gate and come
 * through byte-identical. That pair is why the label, not the hero, is the
 * argument: a caption that names its own number may say whatever else it likes.
 *
 * @param caption     the sentence already rendered under the question
 * @param answerLabel what `rowAnswerLabel` decided to print, or null
 * @param outcomes    the market's served outcomes
 */
export function captionIsAboutAnotherLeg(
  caption: string | null | undefined,
  answerLabel: string | null | undefined,
  outcomes: readonly HeroCandidate[] | null | undefined,
): boolean {
  const label = normalize(answerLabel);
  if (!label || !normalize(caption)) return false;
  return (outcomes ?? []).some((outcome) => {
    const name = (outcome?.name ?? "").trim();
    if (!name || TOO_COMMON_TO_CLAIM.test(name)) return false;
    if (normalize(name) === label) return false;
    return captionNames(caption, name);
  });
}
