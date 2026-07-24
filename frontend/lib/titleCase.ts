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
const ACRONYMS = new Set<string>([
  // Leagues / tours
  "NBA", "WNBA", "NFL", "MLB", "NHL", "MLS", "NCAA", "NCAAB", "NCAAF",
  "EPL", "UCL", "UEFA", "FIFA", "PGA", "LPGA", "LIV", "ATP", "WTA",
  "UFC", "MMA", "F1", "NASCAR", "AFC", "NFC", "AL", "NL",
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
