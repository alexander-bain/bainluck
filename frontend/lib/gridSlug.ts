/**
 * Map an Odds-API-style `sport_key` (e.g. "baseball_mlb") to the championship
 * grid slug the `/api/playoffs/{slug}` endpoint expects (L2-162).
 *
 * Extracted from the league page's inline map so the team page (season-journey +
 * division-race) can resolve the same slug. Pure + side-effect-free so it is
 * unit-testable and SSR-safe. Grid slugs don't always match the sport-key
 * suffix (soccer/UCL), hence the explicit table with a sensible fallback.
 */
const GRID_SLUG_MAP: Record<string, string> = {
  soccer_usa_mls: "mls",
  soccer_epl: "epl",
  soccer_uefa_champs_league: "champions-league",
  soccer_spain_la_liga: "la-liga",
  soccer_germany_bundesliga: "bundesliga",
  americanfootball_nfl: "nfl",
  americanfootball_ncaaf: "ncaa-football",
  basketball_nba: "nba",
  basketball_ncaab: "ncaa-basketball",
  basketball_wnba: "wnba",
  icehockey_nhl: "nhl",
  baseball_mlb: "mlb",
};

/** Resolve the championship-grid slug for a sport_key, or null when unknown. */
export function sportKeyToGridSlug(sportKey: string | null | undefined): string | null {
  if (!sportKey) return null;
  if (GRID_SLUG_MAP[sportKey]) return GRID_SLUG_MAP[sportKey];
  // Fallback: strip the leading provider prefix ("baseball_mlb" → "mlb").
  const suffix = sportKey.split("_").slice(1).join("_");
  return suffix || sportKey;
}
