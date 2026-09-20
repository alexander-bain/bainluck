export function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

const SPORT_KEY_TO_PATH: Record<string, { sport: string; league: string }> = {
  basketball_nba: { sport: "basketball", league: "nba" },
  americanfootball_nfl: { sport: "football", league: "nfl" },
  baseball_mlb: { sport: "baseball", league: "mlb" },
  icehockey_nhl: { sport: "hockey", league: "nhl" },
  basketball_ncaab: { sport: "basketball", league: "ncaab" },
  americanfootball_ncaaf: { sport: "football", league: "ncaaf" },
  basketball_wnba: { sport: "basketball", league: "wnba" },
  soccer_usa_mls: { sport: "soccer", league: "mls" },
  soccer_epl: { sport: "soccer", league: "epl" },
  soccer_spain_la_liga: { sport: "soccer", league: "laliga" },
  soccer_uefa_champs_league: { sport: "soccer", league: "ucl" },
  soccer_germany_bundesliga: { sport: "soccer", league: "bundesliga" },
  basketball_wncaab: { sport: "basketball", league: "wncaab" },
  mma_mixed_martial_arts: { sport: "mma", league: "ufc" },
  golf_pga: { sport: "golf", league: "pga" },
};

/**
 * The sport key a `/sport/<sport>/<league>/` route names. The inverse of
 * `buildTeamPageUrl`'s own mapping, and it lives here so the two can never
 * drift apart. #5852
 *
 * Both halves of that map matter: `("soccer", "ucl")` is `soccer_uefa_champs_league`
 * (an ALIAS — nothing about the segment says "uefa champs league"), while an
 * unmapped pair rejoins on the underscore the same way the fallback arm above
 * split it. Returns null only when a segment is missing.
 */
export function sportKeyForRoute(
  sport: string,
  league: string,
): string | null {
  const s = sport.trim().toLowerCase();
  const l = league.trim().toLowerCase();
  if (!s || !l) return null;
  for (const [key, mapped] of Object.entries(SPORT_KEY_TO_PATH)) {
    if (mapped.sport === s && mapped.league === l) return key;
  }
  return `${s}_${l}`;
}

export function buildTeamPageUrl(
  teamName: string,
  sportKey: string | null | undefined,
): string | null {
  if (!sportKey) return null;
  const mapped = SPORT_KEY_TO_PATH[sportKey];
  if (mapped) {
    return `/sport/${mapped.sport}/${mapped.league}/team/${slugify(teamName)}`;
  }
  const parts = sportKey.split("_");
  if (parts.length >= 2) {
    return `/sport/${parts[0]}/${parts.slice(1).join("_")}/team/${slugify(teamName)}`;
  }
  return null;
}
