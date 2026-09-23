/**
 * Acronym-safe title casing (L2-174 Item 3b).
 *
 * The app title-cases keys/tags/slugs with ad-hoc per-word capitalizers
 * (`\b\w` regex, `word[0].toUpperCase() + word.slice(1)`) that mangle acronyms:
 * "pga tour major" → "A Pga Tour Major", "nba mvp" → "Nba Mvp". This caser
 * capitalizes each word BUT preserves a known-acronym allowlist in uppercase, so
 * "PGA"/"MVP"/"NBA" survive intact. It replaces the manual per-tag override maps
 * that had to hand-list every acronym.
 *
 * Deliberately minimal: it does NOT lowercase connector words (of/the/and) — the
 * ask is only acronym preservation, and lowercasing would silently change dozens
 * of existing grouped labels. Underscores are treated as word separators.
 */

// Sports leagues, awards, orgs, and domain acronyms that must stay uppercase.
// Kept intentionally to unambiguous, domain-relevant tokens.
//
// #1930 — CATEGORY_ACRONYMS is the single shared authority
// (contracts/category-acronyms.json, generated mirror). Entries below it are
// web-local extras, not a second league list: the drift-prone league tokens
// live in the contract, and the parity suite
// (__tests__/categoryAcronymParity1930.test.ts) fails if a mirror diverges.
import { CATEGORY_ACRONYMS } from "./categoryAcronyms.generated";

const ACRONYMS = new Set<string>([
  ...CATEGORY_ACRONYMS,
  // UX-P050: title sponsors that reach the reader as tournament names. "AIG" is
  // the AIG Women's Open, which the feed ships as "Aig Women S Open Womens".
  "AIG",
  "AL", "NL",
  // Awards / roles
  "MVP", "ROY", "DPOY", "OPOY", "CPOY", "GOAT", "POTY",
  // Politics / macro / world
  "US", "USA", "UK", "EU", "UN", "NATO", "SCOTUS", "AOC", "GOP",
  // NB: "Fed" (Federal Reserve) is conventionally title-case, not "FED", so it is
  // intentionally NOT listed here.
  "GDP", "CPI", "FOMC", "IPO", "ETF",
  // Tech / culture
  "AI", "EV", "TV", "SNL", "NASA", "SEC", "FBI", "CEO", "CFO",
]);

export function toTitleCaseAcronymSafe(input: string | null | undefined): string {
  if (!input) return "";
  return input
    .replace(/_/g, " ")
    .trim()
    .split(/\s+/)
    .map((raw) => {
      // Compare on an alnum-only uppercasing so "pga," or "(mvp)" still match.
      const bare = raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
      if (bare && ACRONYMS.has(bare)) return raw.toUpperCase();
      const lower = raw.toLowerCase();
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    })
    .join(" ");
}

/**
 * Acronym-safe casing for a string that ALREADY carries the casing a human
 * chose (#1930).
 *
 * `toTitleCaseAcronymSafe` above re-cases every word — right for the mangled
 * `.capitalized` strings it was written for ("Rbc Canadian Open"), wrong for a
 * value that arrives correctly cased. A `/daily` category is the second kind:
 * it is `sports.name`, which carries "MiLB", "DFB-Pokal", "FA Cup", "Liga MX",
 * "AFL", "HockeyAllsvenskan". Re-casing those lowercases a capital the source
 * supplied — measured at 24 of the 179 live `sports.name` rows on 2026-09-22
 * (artifacts/ux-1437/reach3-sport-names.txt).
 *
 * So this caser does only the two things the reader needs: shout a known
 * acronym, and capitalise a leading lower-case letter. Every other character
 * comes back exactly as given. Use it when the input is already human-cased;
 * use `toTitleCaseAcronymSafe` when the input is a machine-mangled string.
 */
export function toAcronymSafePreservingCase(input: string | null | undefined): string {
  if (!input) return "";
  return input
    .replace(/_/g, " ")
    .trim()
    .split(/\s+/)
    .map((raw) => {
      const bare = raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
      if (bare && ACRONYMS.has(bare)) return raw.toUpperCase();
      return raw.charAt(0).toUpperCase() + raw.slice(1);
    })
    .join(" ");
}

/**
 * Acronym-safe casing that changes nothing a human chose (#8286).
 *
 * `toAcronymSafePreservingCase` still capitalises every word, which is right
 * for a category label and wrong for a proper name: the DataGolf schedule
 * serves "FedEx Open de France", "Sony Open in Hawaii", "Bank of Utah
 * Championship", and a per-word capital reads "Open De France". Measured over
 * the 97 names `/api/golf` served on 2026-09-23: `toTitleCaseAcronymSafe`
 * changed 31, `toAcronymSafePreservingCase` 10, this one 1 (the leading "the"
 * of "the Memorial Tournament").
 *
 * So it shouts a known acronym ("Pga" → "PGA", the UX-P050 case) and
 * capitalises the first letter of the whole string. Every other character
 * comes back exactly as given.
 */
export function toAcronymSafeKeepingCase(input: string | null | undefined): string {
  if (!input) return "";
  const cased = input
    .replace(/_/g, " ")
    .trim()
    .split(/\s+/)
    .map((raw) => {
      const bare = raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
      return bare && ACRONYMS.has(bare) ? raw.toUpperCase() : raw;
    })
    .join(" ");
  return cased.charAt(0).toUpperCase() + cased.slice(1);
}
