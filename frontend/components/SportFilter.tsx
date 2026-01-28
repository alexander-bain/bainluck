"use client";

import type { Sport } from "@/lib/types";

interface SportFilterProps {
  sports: Sport[];
  selectedSport: string | null;
  onSelectSport: (sportKey: string | null) => void;
  loading?: boolean;
}

// Map sport keys to friendly names with emojis (no soccer!)
const SPORT_DISPLAY: Record<string, string> = {
  // American Football
  americanfootball_nfl: "🏈 NFL",
  americanfootball_ncaaf: "🏈 NCAAF",
  americanfootball_cfl: "🏈 CFL",
  americanfootball_xfl: "🏈 XFL",
  // Basketball
  basketball_nba: "🏀 NBA",
  basketball_ncaab: "🏀 NCAAB",
  basketball_wnba: "🏀 WNBA",
  basketball_wncaab: "🏀 WNCAAB",
  basketball_euroleague: "🏀 EuroLeague",
  // Baseball
  baseball_mlb: "⚾ MLB",
  // Hockey
  icehockey_nhl: "🏒 NHL",
  // Combat Sports
  mma_mixed_martial_arts: "🥊 MMA",
  boxing_boxing: "🥋 Boxing",
  // Golf
  golf_pga_championship: "⛳ PGA",
  golf_masters_tournament: "⛳ Masters",
  // Tennis
  tennis_atp_aus_open: "🎾 Australian Open",
  tennis_atp_us_open: "🎾 US Open",
  tennis_atp_wimbledon: "🎾 Wimbledon",
  tennis_atp_french_open: "🎾 French Open",
  // Politics
  politics_us_presidential_election_winner: "🗳️ US Election",
};

function getSportDisplay(sport: Sport): string {
  return SPORT_DISPLAY[sport.key] || sport.name;
}

/**
 * Filter component for selecting a sport.
 */
export default function SportFilter({
  sports,
  selectedSport,
  onSelectSport,
  loading = false,
}: SportFilterProps) {
  if (loading) {
    return (
      <div className="flex gap-2 overflow-x-auto pb-2">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-8 w-20 bg-gray-200 rounded-full animate-pulse"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
      {/* All Sports button */}
      <button
        onClick={() => onSelectSport(null)}
        className={`px-4 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
          selectedSport === null
            ? "bg-gray-900 text-white"
            : "bg-gray-100 text-gray-700 hover:bg-gray-200"
        }`}
      >
        All Sports
      </button>

      {/* Individual sport buttons */}
      {sports.map((sport) => (
        <button
          key={sport.key}
          onClick={() => onSelectSport(sport.key)}
          className={`px-4 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
            selectedSport === sport.key
              ? "bg-gray-900 text-white"
              : "bg-gray-100 text-gray-700 hover:bg-gray-200"
          }`}
        >
          {getSportDisplay(sport)}
        </button>
      ))}
    </div>
  );
}
