/**
 * Sport categories for grouping leagues under parent sports.
 *
 * IMPORTANT: This must be MECE (Mutually Exclusive, Collectively Exhaustive)
 * with the backend's OddsAPIService.SPORTS list. Every sport the backend polls
 * must appear in exactly one category's leagues array.
 *
 * Backend SPORTS list (from backend/app/services/odds_api.py):
 * - americanfootball_nfl, americanfootball_ncaaf
 * - basketball_nba, basketball_ncaab, basketball_wnba
 * - baseball_mlb
 * - icehockey_nhl, icehockey_ahl
 * - mma_mixed_martial_arts, boxing_boxing
 * - golf_pga_championship
 * - tennis_atp_aus_open, tennis_atp_us_open, tennis_atp_wimbledon, tennis_atp_french_open
 * - politics_us_presidential_election_winner
 */

export interface SportCategory {
  key: string;
  name: string;
  emoji: string;
  leagues: string[]; // Sport keys that belong to this category
}

// Sport categories with their leagues - MUST match backend SPORTS list exactly
export const SPORT_CATEGORIES: SportCategory[] = [
  {
    key: "football",
    name: "Football",
    emoji: "🏈",
    leagues: ["americanfootball_nfl", "americanfootball_ncaaf"],
  },
  {
    key: "basketball",
    name: "Basketball",
    emoji: "🏀",
    leagues: ["basketball_nba", "basketball_ncaab", "basketball_wnba"],
  },
  {
    key: "baseball",
    name: "Baseball",
    emoji: "⚾",
    leagues: ["baseball_mlb"],
  },
  {
    key: "hockey",
    name: "Hockey",
    emoji: "🏒",
    leagues: ["icehockey_nhl", "icehockey_ahl"],
  },
  {
    key: "combat",
    name: "Combat Sports",
    emoji: "🥊",
    leagues: ["mma_mixed_martial_arts", "boxing_boxing"],
  },
  {
    key: "golf",
    name: "Golf",
    emoji: "⛳",
    leagues: ["golf_pga_championship"],
  },
  {
    key: "tennis",
    name: "Tennis",
    emoji: "🎾",
    leagues: ["tennis_atp_aus_open", "tennis_atp_us_open", "tennis_atp_wimbledon", "tennis_atp_french_open"],
  },
  {
    key: "politics",
    name: "Politics",
    emoji: "🗳️",
    leagues: ["politics_us_presidential_election_winner"],
  },
];

// Map league keys to display names
export const LEAGUE_DISPLAY: Record<string, string> = {
  // Football
  americanfootball_nfl: "NFL",
  americanfootball_ncaaf: "NCAAF",
  // Basketball
  basketball_nba: "NBA",
  basketball_ncaab: "NCAAB",
  basketball_wnba: "WNBA",
  // Baseball
  baseball_mlb: "MLB",
  // Hockey
  icehockey_nhl: "NHL",
  icehockey_ahl: "AHL",
  // Combat Sports
  mma_mixed_martial_arts: "MMA",
  boxing_boxing: "Boxing",
  // Golf
  golf_pga_championship: "PGA Championship",
  // Tennis
  tennis_atp_aus_open: "Australian Open",
  tennis_atp_us_open: "US Open",
  tennis_atp_wimbledon: "Wimbledon",
  tennis_atp_french_open: "French Open",
  // Politics
  politics_us_presidential_election_winner: "US Election",
};

// Set of all supported league keys (for validation)
export const ALL_SUPPORTED_LEAGUES = new Set(
  SPORT_CATEGORIES.flatMap((cat) => cat.leagues)
);

// Get category for a league key
export function getCategoryForLeague(leagueKey: string): SportCategory | undefined {
  return SPORT_CATEGORIES.find((cat) => cat.leagues.includes(leagueKey));
}

// Get display name for a league
export function getLeagueDisplay(leagueKey: string): string {
  return LEAGUE_DISPLAY[leagueKey] || leagueKey.split("_").pop()?.toUpperCase() || leagueKey;
}

// Get full display with emoji for a league
export function getLeagueDisplayWithEmoji(leagueKey: string): string {
  const category = getCategoryForLeague(leagueKey);
  const leagueName = getLeagueDisplay(leagueKey);
  return category ? `${category.emoji} ${leagueName}` : leagueName;
}

// Check if a league is supported (in the MECE categorization)
export function isLeagueSupported(leagueKey: string): boolean {
  return ALL_SUPPORTED_LEAGUES.has(leagueKey);
}
