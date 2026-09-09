/**
 * Standing notice 33's word ban, as one predicate two guards share.
 *
 * Alex, 2026-09-08: *"we wouldn't EVER want to reference 'bookmakers'"*. The
 * words "books", "bookmaker", "bookmakers", "per-bookmaker" never appear where a
 * reader can see them; **D91** makes "sportsbooks" the approved word.
 *
 * ═══ WHY THIS IS A SHARED FILE AND NOT A COPIED REGEX ═══
 *
 * It was a copied regex for one day, and that is exactly how #4096 happened.
 * `appNeverSaysBookmaker.test.ts` shipped a correct, well-argued scan — over
 * `ios/` only. The web kept saying "20+ bookmakers" and "a finding about the
 * books" in rendered prose, and kept `Per-Bookmaker (Odds API)` in two label
 * maps, because no web guard existed and the iOS one could not see them. A ban
 * enforced on one client is a ban on one client.
 *
 * So the pattern lives here, both guards import it, and neither can quietly
 * become the lenient one. `bannedWordIn` is the whole vocabulary; a caller
 * supplies only the strings it believes a reader sees, because THAT judgement
 * is per-surface and does not belong in a shared file.
 *
 * Lives under `__tests__/helpers/` beside `cssModuleProxy.js`: jest's
 * `testMatch` is `**\/__tests__\/**\/*.test.ts`, so a file without `.test.` in
 * its name is importable without being collected as an empty suite.
 */

/**
 * The banned words, as whole words.
 *
 * `\b` is load-bearing in both directions. It keeps "sportsbook" and
 * "sportsbooks" — the APPROVED word (D91) — out of the `books?` pattern, because
 * there is no word boundary inside "sportsbooks"; and it keeps the possessive
 * "the books' projected" IN, because an apostrophe is a boundary. Both spellings
 * of the apostrophe, since the codebase uses typographic punctuation in prose.
 */
export const BANNED: ReadonlyArray<readonly [string, RegExp]> = [
  ['the supplier class word "bookmaker(s)" (D91: the word is "sportsbooks")', /\bbookmakers?\b/i],
  ['the supplier class word "book(s)" (D91: the word is "sportsbooks")', /\bbooks?['’]?\b/i],
];

/**
 * A literal shaped like a KEY rather than a sentence is data, not prose.
 *
 * Structural, not an allowlist, and that distinction is the lesson #4021 paid
 * for: a list of known-good exceptions hands the claim to the first case nobody
 * listed. A payload key, a JSON field, an SF Symbol, a URL path and a
 * UserDefaults key are all lowercase with separators and no spaces; a sentence a
 * reader sees has a space or a capital in it. `odds_api_bookmaker` is exempt for
 * the same reason `bookmaker_count` is — they are the API's words, not ours, and
 * renaming a wire key to satisfy a copy rule would be a data change wearing a
 * ban's clothes. The notice-33 clarification (Fable-5, 2026-09-08 3:52pm PT)
 * says this in so many words: machine keys are out of scope "unless a client
 * renders them raw".
 *
 * THE COST OF THE RULE, STATED: a bare `"books"` drawn as a label would pass.
 * Widening the rule to catch it would flag every payload key containing the
 * token — the trade that turns a scan into a nuisance and gets it deleted. The
 * web's own registries close that hole a different way, by asserting over the
 * label VALUES directly rather than over source text, where a bare "Books" is
 * not key-shaped anyway (it is capitalised).
 */
export const KEY_SHAPED = /^[a-z0-9_.:/+-]*$/;

/**
 * The banned word in `text`, described for a failure message — or `null`.
 *
 * Returns the DESCRIPTION rather than a boolean so an offender list can name
 * which rule it broke and what to write instead; a guard that only says "no"
 * gets read as noise.
 */
export function bannedWordIn(text: string): string | null {
  return BANNED.find(([, re]) => re.test(text))?.[0] ?? null;
}

/** As `bannedWordIn`, but key-shaped strings are data and never prose. */
export function bannedWordInProse(text: string): string | null {
  return KEY_SHAPED.test(text) ? null : bannedWordIn(text);
}
