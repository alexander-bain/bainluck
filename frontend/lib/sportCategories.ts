/**
 * Sport categories for grouping leagues under parent sports.
 *
 * BLACKLIST APPROACH: The backend excludes only soccer (soccer_*).
 * Everything else from The Odds API is included and should be categorized here.
 *
 * This file maps sport keys to categories and display names dynamically.
 * Unknown sports fall into an "Other" category rather than being hidden.
 */

export interface SportCategory {
  key: string;
  name: string;
  emoji: string;
  prefixes: string[]; // Sport key prefixes that belong to this category
}

/**
 * Sport categories with their key prefixes.
 * A sport key is matched to the first category whose prefix it starts with.
 */
export const SPORT_CATEGORIES: SportCategory[] = [
  {
    key: "football",
    name: "Football",
    emoji: "🏈",
    prefixes: ["americanfootball_"],
  },
  {
    key: "basketball",
    name: "Basketball",
    emoji: "🏀",
    prefixes: ["basketball_"],
  },
  {
    key: "baseball",
    name: "Baseball",
    emoji: "⚾",
    prefixes: ["baseball_"],
  },
  {
    key: "hockey",
    name: "Hockey",
    emoji: "🏒",
    prefixes: ["icehockey_"],
  },
  {
    key: "mma",
    name: "MMA",
    emoji: "🥋",
    prefixes: ["mma_"],
  },
  {
    key: "boxing",
    name: "Boxing",
    emoji: "🥊",
    prefixes: ["boxing_"],
  },
  {
    key: "golf",
    name: "Golf",
    emoji: "⛳",
    prefixes: ["golf_"],
  },
  {
    key: "tennis",
    name: "Tennis",
    emoji: "🎾",
    prefixes: ["tennis_"],
  },
  {
    key: "cricket",
    name: "Cricket",
    emoji: "🏏",
    prefixes: ["cricket_"],
  },
  {
    key: "rugby",
    name: "Rugby",
    emoji: "🏉",
    prefixes: ["rugbyleague_", "rugbyunion_"],
  },
  {
    key: "aussierules",
    name: "Aussie Rules",
    emoji: "🦘",
    prefixes: ["aussierules_"],
  },
  {
    key: "politics",
    name: "Politics",
    emoji: "🗳️",
    prefixes: ["politics_"],
  },
  {
    key: "esports",
    name: "Esports",
    emoji: "🎮",
    prefixes: ["esports_"],
  },
  {
    key: "lacrosse",
    name: "Lacrosse",
    emoji: "🥍",
    prefixes: ["lacrosse_"],
  },
  {
    key: "motorsport",
    name: "Motorsport",
    emoji: "🏎️",
    prefixes: ["motorsport_", "racing_"],
  },
  // Other category is a catch-all (handled in code, not here)
];

/**
 * Known league display names.
 * If a league isn't here, we generate a display name from the key.
 */
export const LEAGUE_DISPLAY: Record<string, string> = {
  // Football
  americanfootball_nfl: "NFL",
  americanfootball_ncaaf: "NCAAF",
  americanfootball_cfl: "CFL",
  americanfootball_xfl: "XFL",
  americanfootball_ufl: "UFL",
  // Basketball
  basketball_nba: "NBA",
  basketball_ncaab: "NCAAB",
  basketball_wnba: "WNBA",
  basketball_wncaab: "WNCAAB",
  basketball_euroleague: "EuroLeague",
  basketball_nbl: "NBL (Australia)",
  // Baseball
  baseball_mlb: "MLB",
  baseball_ncaa: "NCAA Baseball",
  baseball_npb: "NPB (Japan)",
  baseball_kbo: "KBO (Korea)",
  // Hockey
  icehockey_nhl: "NHL",
  icehockey_ahl: "AHL",
  icehockey_khl: "KHL",
  icehockey_shl: "SHL (Sweden)",
  icehockey_liiga: "Liiga (Finland)",
  // MMA
  mma_mixed_martial_arts: "MMA",
  mma_ufc: "UFC",
  // Boxing
  boxing_boxing: "Boxing",
  // Golf
  golf_pga_championship: "PGA Championship",
  golf_masters_tournament: "Masters",
  golf_us_open: "US Open",
  golf_the_open: "The Open",
  golf_pga_tour: "PGA Tour",
  // Tennis
  tennis_atp_aus_open: "Australian Open",
  tennis_atp_us_open: "US Open",
  tennis_atp_wimbledon: "Wimbledon",
  tennis_atp_french_open: "French Open",
  tennis_wta_aus_open: "AO (WTA)",
  tennis_wta_us_open: "US Open (WTA)",
  // Cricket
  cricket_ipl: "IPL",
  cricket_bbl: "BBL",
  cricket_test_match: "Test Match",
  cricket_odi: "ODI",
  cricket_t20: "T20",
  // Rugby
  rugbyleague_nrl: "NRL",
  rugbyunion_six_nations: "Six Nations",
  rugbyunion_super_rugby: "Super Rugby",
  // Aussie Rules
  aussierules_afl: "AFL",
  // Politics
  politics_us_presidential_election_winner: "US Election",
  politics_us_presidential_election: "US Election",
  // Esports
  esports_lol: "League of Legends",
  esports_csgo: "CS:GO",
  esports_dota2: "Dota 2",
  esports_valorant: "Valorant",
};

/**
 * Get category for a league key based on prefix matching.
 */
export function getCategoryForLeague(leagueKey: string): SportCategory | undefined {
  return SPORT_CATEGORIES.find((cat) =>
    cat.prefixes.some((prefix) => leagueKey.startsWith(prefix))
  );
}

/**
 * Get display name for a league.
 * Falls back to generating a readable name from the key.
 */
export function getLeagueDisplay(leagueKey: string): string {
  if (LEAGUE_DISPLAY[leagueKey]) {
    return LEAGUE_DISPLAY[leagueKey];
  }

  // Generate a display name from the key
  // e.g., "basketball_nba" -> "NBA", "tennis_atp_aus_open" -> "ATP Aus Open"
  const parts = leagueKey.split("_");
  if (parts.length > 1) {
    // Remove the first part (category) and capitalize the rest
    const displayParts = parts.slice(1).map((part) =>
      part.toUpperCase()
    );
    return displayParts.join(" ");
  }
  return leagueKey.toUpperCase();
}

/**
 * Get full display with emoji for a league.
 */
export function getLeagueDisplayWithEmoji(leagueKey: string): string {
  const category = getCategoryForLeague(leagueKey);
  const leagueName = getLeagueDisplay(leagueKey);
  return category ? `${category.emoji} ${leagueName}` : `🏆 ${leagueName}`;
}

/**
 * Get emoji for a sport category or default trophy for unknown.
 */
export function getEmojiForLeague(leagueKey: string): string {
  const category = getCategoryForLeague(leagueKey);
  return category?.emoji || "🏆";
}

/**
 * Get category name for a league, or "Other" for unknown.
 */
export function getCategoryName(leagueKey: string): string {
  const category = getCategoryForLeague(leagueKey);
  return category?.name || "Other";
}

/**
 * Group an array of league keys by their category.
 * Returns a map of categoryKey -> leagueKeys[]
 */
export function groupLeaguesByCategory(leagueKeys: string[]): Map<string, string[]> {
  const groups = new Map<string, string[]>();

  for (const leagueKey of leagueKeys) {
    const category = getCategoryForLeague(leagueKey);
    const categoryKey = category?.key || "other";

    if (!groups.has(categoryKey)) {
      groups.set(categoryKey, []);
    }
    groups.get(categoryKey)!.push(leagueKey);
  }

  return groups;
}

/**
 * Get all unique categories present in a list of league keys.
 * Includes "other" category if there are uncategorized leagues.
 */
export function getActiveCategoriesFromLeagues(leagueKeys: string[]): SportCategory[] {
  const categorySet = new Set<string>();
  let hasOther = false;

  for (const leagueKey of leagueKeys) {
    const category = getCategoryForLeague(leagueKey);
    if (category) {
      categorySet.add(category.key);
    } else {
      hasOther = true;
    }
  }

  const activeCategories = SPORT_CATEGORIES.filter((cat) => categorySet.has(cat.key));

  if (hasOther) {
    activeCategories.push({
      key: "other",
      name: "Other",
      emoji: "🏆",
      prefixes: [],
    });
  }

  return activeCategories;
}
