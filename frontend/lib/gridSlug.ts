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
  basketball_wncaab: "ncaa-women-basketball",
  basketball_wnba: "wnba",
  icehockey_nhl: "nhl",
  baseball_mlb: "mlb",
};

const SLUG_TO_SPORT_KEY: Record<string, string> = {
  ...Object.fromEntries(
    Object.entries(GRID_SLUG_MAP).map(([sportKey, slug]) => [slug, sportKey]),
  ),
  ucl: "soccer_uefa_champs_league",
  "la-liga": "soccer_spain_la_liga",
  laliga: "soccer_spain_la_liga",
  ncaab: "basketball_ncaab",
  ncaa: "basketball_ncaab",
  ncaaf: "americanfootball_ncaaf",
  wncaab: "basketball_wncaab",
};

// Season-phase suffixes a team's sport.key can carry (e.g.
// "baseball_mlb_preseason") that must be stripped before mapping — the grid is
// keyed on the canonical league, not the phase. This is the same stale-phase
// copy L2-158 Item 3 stripped for the breadcrumb label.
const SEASON_PHASE_SUFFIXES = [
  "_preseason",
  "_postseason",
  "_regular_season",
  "_regular",
  "_playoffs",
  "_spring_training",
];

function stripSeasonPhase(sportKey: string): string {
  for (const suffix of SEASON_PHASE_SUFFIXES) {
    if (sportKey.endsWith(suffix)) return sportKey.slice(0, -suffix.length);
  }
  return sportKey;
}

/** Resolve the championship-grid slug for a sport_key, or null when unknown. */
export function sportKeyToGridSlug(sportKey: string | null | undefined): string | null {
  if (!sportKey) return null;
  const canonical = stripSeasonPhase(sportKey);
  if (GRID_SLUG_MAP[canonical]) return GRID_SLUG_MAP[canonical];
  // Fallback: strip the leading provider prefix ("baseball_mlb" → "mlb").
  const suffix = canonical.split("_").slice(1).join("_");
  return suffix || canonical;
}

/**
 * Inverse of `sportKeyToGridSlug` (#11492): resolve the canonical `sport_key`
 * (e.g. `"baseball_mlb"`) for a championship-grid league slug (`"mlb"`,
 * `"la-liga"`, `"ncaa-women-basketball"`), or `null` when the slug is not a
 * team-sport grid (e.g. `"golf"`).
 */
export function gridSlugToSportKey(slug: string | null | undefined): string | null {
  if (!slug) return null;
  const normalized = slug.trim().toLowerCase();
  if (!normalized) return null;
  if (GRID_SLUG_MAP[normalized]) return normalized;
  return SLUG_TO_SPORT_KEY[normalized] ?? null;
}
