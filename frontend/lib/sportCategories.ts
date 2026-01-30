/**
 * Sport categories for grouping leagues under parent sports.
 *
 * BLACKLIST APPROACH: The backend excludes soccer, cricket, rugby, and AFL.
 * (soccer_*, cricket_*, rugbyleague_*, rugbyunion_*, aussierules_*)
 * Everything else from The Odds API is included and should be categorized here.
 *
 * This file maps sport keys to categories and display names dynamically.
 * Unknown sports fall into an "Other" category rather than being hidden.
 *
 * Last updated: 2025-01-27
 */

export interface SportCategory {
  key: string;
  name: string;
  emoji: string;
  prefixes: string[]; // Sport key prefixes that belong to this category
  tier: 1 | 2 | 3; // 1 = primary (Football, Basketball, Baseball), 2 = secondary, 3 = tertiary
}

/**
 * Sport categories with their key prefixes.
 * A sport key is matched to the first category whose prefix it starts with.
 */
export const SPORT_CATEGORIES: SportCategory[] = [
  // Tier 1: Primary sports (most users care about these)
  {
    key: "football",
    name: "Football",
    emoji: "🏈",
    prefixes: ["americanfootball_"],
    tier: 1,
  },
  {
    key: "basketball",
    name: "Basketball",
    emoji: "🏀",
    prefixes: ["basketball_"],
    tier: 1,
  },
  {
    key: "baseball",
    name: "Baseball",
    emoji: "⚾",
    prefixes: ["baseball_"],
    tier: 1,
  },
  // Tier 2: Secondary sports (popular but niche)
  {
    key: "hockey",
    name: "Hockey",
    emoji: "🏒",
    prefixes: ["icehockey_"],
    tier: 2,
  },
  {
    key: "mma",
    name: "MMA",
    emoji: "🥋",
    prefixes: ["mma_"],
    tier: 2,
  },
  {
    key: "boxing",
    name: "Boxing",
    emoji: "🥊",
    prefixes: ["boxing_"],
    tier: 2,
  },
  {
    key: "golf",
    name: "Golf",
    emoji: "⛳",
    prefixes: ["golf_"],
    tier: 2,
  },
  {
    key: "tennis",
    name: "Tennis",
    emoji: "🎾",
    prefixes: ["tennis_"],
    tier: 2,
  },
  // Tier 3: Tertiary sports (niche audience)
  {
    key: "cricket",
    name: "Cricket",
    emoji: "🏏",
    prefixes: ["cricket_"],
    tier: 3,
  },
  {
    key: "rugby",
    name: "Rugby",
    emoji: "🏉",
    prefixes: ["rugbyleague_", "rugbyunion_"],
    tier: 3,
  },
  {
    key: "aussierules",
    name: "Aussie Rules",
    emoji: "🦘",
    prefixes: ["aussierules_"],
    tier: 3,
  },
  {
    key: "politics",
    name: "Politics",
    emoji: "🗳️",
    prefixes: ["politics_"],
    tier: 3,
  },
  {
    key: "esports",
    name: "Esports",
    emoji: "🎮",
    prefixes: ["esports_"],
    tier: 3,
  },
  {
    key: "lacrosse",
    name: "Lacrosse",
    emoji: "🥍",
    prefixes: ["lacrosse_"],
    tier: 3,
  },
  {
    key: "motorsport",
    name: "Motorsport",
    emoji: "🏎️",
    prefixes: ["motorsport_", "racing_"],
    tier: 3,
  },
  // Other category is a catch-all (handled in code, not here)
];

/**
 * League tiers for prioritizing major leagues.
 * 1 = Major pro league (NFL, NBA, MLB, NHL)
 * 2 = Major college or secondary pro (NCAAF, NCAAB, WNBA)
 * 3 = Minor leagues and international
 */
export const LEAGUE_TIERS: Record<string, 1 | 2 | 3> = {
  // Football
  americanfootball_nfl: 1,
  americanfootball_ncaaf: 2,
  americanfootball_cfl: 3,
  americanfootball_xfl: 3,
  americanfootball_ufl: 3,
  // Basketball
  basketball_nba: 1,
  basketball_ncaab: 2,
  basketball_wnba: 2,
  basketball_wncaab: 3,
  basketball_euroleague: 3,
  basketball_nbl: 3,
  // Baseball
  baseball_mlb: 1,
  baseball_ncaa: 3,
  baseball_npb: 3,
  baseball_kbo: 3,
  // Hockey
  icehockey_nhl: 1,
  icehockey_ahl: 3,
  icehockey_khl: 3,
  icehockey_shl: 3,
  // MMA/Boxing
  mma_ufc: 2,
  mma_mixed_martial_arts: 2,
  boxing_boxing: 2,
  // Golf
  golf_pga_tour: 2,
  golf_masters_tournament: 2,
  golf_pga_championship: 2,
  golf_us_open: 2,
  golf_the_open: 2,
  // Tennis
  tennis_atp_aus_open: 2,
  tennis_atp_wimbledon: 2,
  tennis_atp_us_open: 2,
  tennis_atp_french_open: 2,
};

/**
 * Get league tier (default to 3 for unknown leagues)
 */
export function getLeagueTier(leagueKey: string): 1 | 2 | 3 {
  return LEAGUE_TIERS[leagueKey] ?? 3;
}

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
  basketball_nbl: "NBL",
  basketball_nba_championship_winner: "NBA Finals",
  basketball_ncaab_championship_winner: "March Madness",
  // Baseball
  baseball_mlb: "MLB",
  baseball_ncaa: "NCAA Baseball",
  baseball_npb: "NPB",
  baseball_kbo: "KBO",
  baseball_mlb_world_series_winner: "World Series",
  // Hockey
  icehockey_nhl: "NHL",
  icehockey_ahl: "AHL",
  icehockey_khl: "KHL",
  icehockey_shl: "SHL",
  icehockey_liiga: "Liiga",
  icehockey_mestis: "Mestis",
  icehockey_sweden_hockey_league: "SHL",
  icehockey_sweden_allsvenskan: "Allsvenskan",
  icehockey_nhl_championship_winner: "Stanley Cup",
  // MMA
  mma_mixed_martial_arts: "MMA",
  mma_ufc: "UFC",
  // Boxing
  boxing_boxing: "Boxing",
  // Golf
  golf_pga_championship: "PGA Championship",
  golf_pga_championship_winner: "PGA Championship",
  golf_masters_tournament: "Masters",
  golf_masters_tournament_winner: "Masters",
  golf_us_open: "US Open",
  golf_us_open_winner: "US Open",
  golf_the_open: "The Open",
  golf_the_open_championship_winner: "The Open",
  golf_pga_tour: "PGA Tour",
  // Tennis
  tennis_atp_aus_open: "Australian Open",
  tennis_atp_aus_open_singles: "Australian Open (ATP)",
  tennis_wta_aus_open_singles: "Australian Open (WTA)",
  tennis_atp_us_open: "US Open",
  tennis_atp_us_open_singles: "US Open (ATP)",
  tennis_wta_us_open_singles: "US Open (WTA)",
  tennis_atp_wimbledon: "Wimbledon",
  tennis_atp_wimbledon_singles: "Wimbledon (ATP)",
  tennis_wta_wimbledon_singles: "Wimbledon (WTA)",
  tennis_atp_french_open: "French Open",
  tennis_atp_french_open_singles: "French Open (ATP)",
  tennis_wta_french_open_singles: "French Open (WTA)",
  // Cricket
  cricket_ipl: "IPL",
  cricket_bbl: "BBL",
  cricket_test_match: "Test Match",
  cricket_odi: "ODI",
  cricket_t20: "T20",
  cricket_international_t20: "International T20",
  // Rugby
  rugbyleague_nrl: "NRL",
  rugbyleague_nrl_state_of_origin: "State of Origin",
  rugbyunion_six_nations: "Six Nations",
  rugbyunion_super_rugby: "Super Rugby",
  // Aussie Rules
  aussierules_afl: "AFL",
  // Lacrosse
  lacrosse_ncaa: "NCAA Lacrosse",
  lacrosse_pll: "PLL",
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
      tier: 3,
    });
  }

  return activeCategories;
}
/**
 * Calculate an excitement score for an event.
 * Higher scores = more exciting/important games that should surface first.
 *
 * Factors:
 * - Live games get high priority
 * - Close matchups (within 10% of 50/50) are exciting
 * - Starting soon (within 1 hour) gets boost
 * - Higher tier leagues get slight boost
 *
 * Returns a score from 0-100
 */
export function calculateExcitementScore(
  event: {
    status: "scheduled" | "live" | "completed";
    commence_time: string;
    sport: string | null;
    current_odds?: {
      home_probability: number | null;
    };
  }
): number {
  let score = 0;

  // Live games: +50 points
  if (event.status === "live") {
    score += 50;
  }

  // Close games (within 10% of 50/50): +30 points max
  const homeProb = event.current_odds?.home_probability ?? 0.5;
  const closeness = 1 - Math.abs(homeProb - 0.5) * 2; // 1.0 = perfectly even, 0.0 = one-sided
  if (closeness > 0.8) {
    // Within 10% of 50/50
    score += 30 * closeness;
  }

  // Starting soon (within 1 hour): +15 points
  const now = new Date();
  const gameTime = new Date(event.commence_time);
  const hoursUntil = (gameTime.getTime() - now.getTime()) / (1000 * 60 * 60);
  if (hoursUntil > 0 && hoursUntil <= 1) {
    score += 15;
  } else if (hoursUntil > 1 && hoursUntil <= 3) {
    score += 5;
  }

  // League tier boost: Tier 1 = +5, Tier 2 = +2, Tier 3 = 0
  if (event.sport) {
    const tier = getLeagueTier(event.sport);
    if (tier === 1) score += 5;
    else if (tier === 2) score += 2;
  }

  return Math.min(100, score);
}

/**
 * Determine if an event is "featured" (exciting enough to highlight)
 * Featured = Live OR (close game AND starting within 3 hours)
 */
export function isFeaturedEvent(
  event: {
    status: "scheduled" | "live" | "completed";
    commence_time: string;
    current_odds?: {
      home_probability: number | null;
    };
  }
): boolean {
  // Live games are always featured
  if (event.status === "live") {
    return true;
  }

  // Close games starting soon are featured
  const homeProb = event.current_odds?.home_probability ?? 0.5;
  const isClose = Math.abs(homeProb - 0.5) <= 0.1; // Within 10% of 50/50

  const now = new Date();
  const gameTime = new Date(event.commence_time);
  const hoursUntil = (gameTime.getTime() - now.getTime()) / (1000 * 60 * 60);
  const startingSoon = hoursUntil > 0 && hoursUntil <= 3;

  return isClose && startingSoon;
}

// Force rebuild Wed Jan 28 2026 - tiered polling update
