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

/**
 * Reader copy for `/calibration`'s **data corrections log** (#7729).
 *
 * WHY THIS EXISTS.
 *
 * `corrections[9].title` on the live payload is
 *
 *     Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)
 *
 * and `Queue #186` is our handoff directory's own numbering. It renders, at
 * 390px, on a public page, in the one slot this card gives a reader — and it
 * resolves to nothing a reader can open. It is the only one of the thirteen
 * titles that carries one; the other twelve are clean.
 *
 * ── THIS IS #4067 / CERT-2295, ONE FIELD LATER ──────────────────────────────
 *
 * That cert named the specimen exactly: *"a notice-33 supplier word inside a
 * notice-34 method note, quoting our own issue number at a reader."* The repair
 * moved the render off `description` (the backend's auditor paragraph) and onto
 * `title`, on the reasoning that the title is the page's copy. The reasoning was
 * right and the field was not: `title` is written in the same file, by the same
 * hand, in the same sitting as the paragraph below it, so it inherits the same
 * prose. Moving one field left was a narrowing, not a fence.
 *
 * ── WHY THE PAGE FIXES IT AND NOT THE PRODUCER ──────────────────────────────
 *
 * Two reasons, and the second is the load-bearing one.
 *
 * `precompute_calibration_main` is a `HEAVY_TASK`, and `bainluck-heavy` runs
 * behind master (notice 48). The served artifact has been stamped
 * `2026-09-15T11:16:10Z` for six days (#6868). A one-word edit in the producer
 * would be correct and invisible for an unbounded time.
 *
 * And presentation is the page's, which is the rule this card already lives
 * under — `NAMED_EXCLUSION_LABELS` next door is a closed map for the same
 * reason, and `orderCorrections` above took the sort for the same reason: a
 * rule applied upstream fixes the rows published today and nothing appended
 * after them.
 *
 * ── THE MAP IS CLOSED AND THE STRIP IS A FLOOR, NOT THE FIX ─────────────────
 *
 * `CORRECTION_TITLE_OVERRIDES` is keyed on the producer's exact string, so a
 * title the page has chosen words for is a deliberate, reviewable pair and never
 * a guess. That is the fix.
 *
 * `withheldInternalReference` is the floor under it: a title the map has no
 * entry for still may not carry a tracker id, so the fragment carrying one is
 * WITHHELD — dropped, never rewritten (#4113, notice 34: the page may remove its
 * own words, it may not invent a reader's). A reader loses a fragment that meant
 * nothing to them and gains no paragraph about the loss.
 *
 * The floor is not a licence to skip the map. It cannot produce good copy — run
 * on the specimen above it yields *"…— corrected discriminator"*, which is still
 * jargon in the slot the page controls. It exists so that the day the producer
 * grows a title nobody mapped, the leak is a missing clause rather than a
 * tracker id on a trust panel. `correctionsNeedingCopy` counts exactly those
 * rows so the gap travels as a data attribute (notice 34's failing-self-audit
 * remedy) and the suite can pin it at zero against the producer's own source.
 */
export const CORRECTION_TITLE_OVERRIDES: Readonly<Record<string, string>> = {
  // The producer's own words for what changed: the earlier rule kept any row
  // that had a live bid behind it, and a snapshot-level verify disproved that —
  // real-bid rows are corrupt too (a scorer and a non-scorer in one market both
  // carrying 0.995 with a live 0.99 bid). The test moved to the captured price
  // itself. `precompute_calibration.py`'s `description` for this entry is the
  // source; none of its series tickers, issue numbers or column names travel.
  "Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)":
    "Player-prop prices (Kalshi): corrected the test for which prices to drop",

  // ── #7734: the eight July titles that were engineer shorthand ──────────────
  //
  // Each line below is the producer's own `description` for that row, said once,
  // in the vocabulary the September entries already use ("Prices nobody could
  // have traded at", "A price ladder is one forecast, not forty"). No claim
  // moves: no count, no exclusion basis, no regrade. What changes is that the
  // one slot this card gives a reader is now written for one.

  // "Player-threshold props stored the OVER probability against the Under/No
  // side (gotcha #17). Re-graded the Polymarket half."
  "Polymarket hockey sign-flip":
    "Hockey player props (Polymarket): over and under prices were the wrong way round, now re-scored",

  // "Symmetric exclusion of did-not-play / withdrew outcomes so the golf curve
  // isn't inflated by non-participants."
  "DataGolf survivorship exclusion":
    "Golf: players who withdrew or never teed off are no longer scored",

  // "Illiquid poly props stamped a no-signal ~0.50 midpoint … now excluded from
  // the curve by bid presence — read-side only, no regrade."
  "Polymarket no-bid placeholder exclusion":
    "Polymarket prices with no offer behind them, parked near 50%, are no longer scored",

  // "Resolved 2-outcome mutually-exclusive markets must have exactly one winner.
  // Zero-winner (void) and two-winner (impossible) markets are data artifacts."
  "Malformed-binary exclusion":
    "Yes-or-no markets that settled with no winner, or with two, are no longer scored",

  // "Golf winner/round-leader outcomes priced >=0.80 in a mutually-exclusive
  // market with >=2 such outcomes are one-sided-ask placeholders … genuine
  // single leaders stay in." The copy names the two-at-once shape, which is the
  // part that makes the price impossible rather than merely confident.
  "Golf FIELD one-sided-ask placeholder exclusion":
    "Golf: prices that put two players in one event both above 80% to win are no longer scored",

  // "Mutually-exclusive markets with >=3 outcomes are one question and must sum
  // to ~1.0, but sources stamp each candidate at its one-sided ask so the sum
  // inflated to 2.4-5.3. Now each such market's probabilities are divided by the
  // per-market sum."
  "Multi-candidate probability normalization":
    "Markets with several candidates now add up to 100%, instead of well over it",

  // "Soccer game-odds were captured 2-way (home/away only) — no draw column — so
  // every soccer moneyline row … structurally dropped the ~25% draw mass … is
  // excluded from the curve; soccer spreads/totals are kept." The copy says
  // win-or-lose rather than naming the market type: it is the reader's phrase for
  // the rows that went, and it keeps the scope honest (spreads and totals stayed).
  "Soccer 2-way (draw-omission) historical exclusion":
    "Soccer: older win-or-lose prices left the draw out, so they are no longer scored",

  // "Polymarket packs a whole esports match (cumulative Total-Kills ladders per
  // game, per-game winners, first-blood props) into one non-partition market …
  // neither sums to ~1.0 nor buckets as a clean prediction."
  "Esports match-bundle exclusion":
    "Esports markets that pack a whole match into one question are no longer scored",
};

/**
 * Fragments of a title that exist for us, not for a reader.
 *
 * A tracker id in any of the shapes this repo actually writes — `Queue #186`,
 * `#4067`, `CERT-2295`, `L2-74`, `CAL-P114`, `OPS-557`, `q271` — inside a
 * trailing parenthetical or after an em-dash. Anchored to those two carriers on
 * purpose: an id in the MIDDLE of a sentence cannot be cut without changing what
 * the sentence says, so those are left to the map and counted, not mangled.
 *
 * Written as one alternation over the id shapes rather than a bare `#\d+` so a
 * real reader number — a price, a year, a count — is never eaten.
 */
// The `\b` on the named prefixes is load-bearing: without it the single-letter
// arms (`D`, `q`) match mid-word — `3D2`, `Iraq2024` — and the floor would start
// cutting clauses out of titles that carry no tracker id at all. `#\d{2,}` takes
// no boundary because `#` is not a word character, so `\b` before it would
// require a word character IN FRONT of the hash and the common shape (a hash
// after a space) would stop matching.
const TRACKER_ID = String.raw`(?:\b(?:Queue|Issue|CERT|OPS|CAL-P|L2|UX-P|D|q)[\s-]?#?\d+|#\d{2,})`;
const TRAILING_PARENTHETICAL = new RegExp(String.raw`\s*\((?:[^()]*\s)?${TRACKER_ID}[^()]*\)\s*$`);
const TRAILING_DASH_CLAUSE = new RegExp(String.raw`\s*[—–-]\s*[^—–]*${TRACKER_ID}[^—–]*$`);

/** Does this title still carry something written for our own tracker? */
export function carriesInternalReference(title: string): boolean {
  return new RegExp(TRACKER_ID).test(title);
}

/**
 * The title with any trailing tracker fragment withheld.
 *
 * Returns the title unchanged when the reference is not in a carrier this can
 * cut cleanly — that row is a `correctionsNeedingCopy`, and the honest answer
 * is to say so rather than to guess at a cut.
 */
export function withheldInternalReference(title: string): string {
  const cut = title.replace(TRAILING_PARENTHETICAL, "").replace(TRAILING_DASH_CLAUSE, "");
  const trimmed = cut.trim();
  return trimmed.length > 0 ? trimmed : title;
}

/**
 * What the page prints for one correction: the map's words, else the producer's
 * title with any trailing tracker fragment withheld.
 */
export function correctionTitle(title: string | null | undefined): string {
  if (!title) return "";
  const override = CORRECTION_TITLE_OVERRIDES[title];
  if (override !== undefined) return override;
  return carriesInternalReference(title) ? withheldInternalReference(title) : title;
}

/**
 * Rows whose producer title carries a tracker id and that the map has no words
 * for — the ones running on the floor rather than on chosen copy.
 *
 * Never rendered as prose. Published as a data attribute so the gap is readable
 * by a probe the day the producer grows a title nobody mapped, the same contract
 * `NAMED_EXCLUSION_LABELS`'s `unlistedRules` carries next door.
 */
export function correctionsNeedingCopy(
  corrections: readonly CalibrationCorrection[] | null | undefined,
): number {
  if (!corrections || !corrections.length) return 0;
  return corrections.filter(c => {
    const title = c?.title;
    if (!title) return false;
    if (CORRECTION_TITLE_OVERRIDES[title] !== undefined) return false;
    return carriesInternalReference(title);
  }).length;
}
