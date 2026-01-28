/**
 * Sport categories for grouping leagues under parent sports.
 */

export interface SportCategory {
  key: string;
  name: string;
  emoji: string;
  leagues: string[]; // Sport keys that belong to this category
}

// Sport categories with their leagues
export const SPORT_CATEGORIES: SportCategory[] = [
  {
    key: "football",
    name: "Football",
    emoji: "🏈",
    leagues: ["americanfootball_nfl", "americanfootball_ncaaf", "americanfootball_cfl", "americanfootball_xfl"],
  },
  {
    key: "basketball",
    name: "Basketball",
    emoji: "🏀",
    leagues: ["basketball_nba", "basketball_ncaab", "basketball_wnba", "basketball_wncaab", "basketball_euroleague"],
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
    name: "Combat",
    emoji: "🥊",
    leagues: ["mma_mixed_martial_arts", "boxing_boxing"],
  },
  {
    key: "golf",
    name: "Golf",
    emoji: "⛳",
    leagues: ["golf_pga_championship", "golf_masters_tournament"],
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
  americanfootball_cfl: "CFL",
  americanfootball_xfl: "XFL",
  // Basketball
  basketball_nba: "NBA",
  basketball_ncaab: "NCAAB",
  basketball_wnba: "WNBA",
  basketball_wncaab: "WNCAAB",
  basketball_euroleague: "EuroLeague",
  // Baseball
  baseball_mlb: "MLB",
  // Hockey
  icehockey_nhl: "NHL",
  icehockey_ahl: "AHL",
  // Combat
  mma_mixed_martial_arts: "MMA",
  boxing_boxing: "Boxing",
  // Golf
  golf_pga_championship: "PGA",
  golf_masters_tournament: "Masters",
  // Tennis
  tennis_atp_aus_open: "Australian Open",
  tennis_atp_us_open: "US Open",
  tennis_atp_wimbledon: "Wimbledon",
  tennis_atp_french_open: "French Open",
  // Politics
  politics_us_presidential_election_winner: "US Election",
};

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
