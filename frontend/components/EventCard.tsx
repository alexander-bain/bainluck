"use client";

import Link from "next/link";
import type { Event, CurrentOdds } from "@/lib/types";
import { formatProbability, formatGameTime, isStartingSoon } from "@/lib/api";
import ProbabilityBar from "./ProbabilityBar";

interface EventCardProps {
  event: Event;
  showSport?: boolean;
}

// Map sport keys to friendly display names (no soccer!)
const SPORT_DISPLAY: Record<string, string> = {
  // American Football
  americanfootball_nfl: "🏈 NFL",
  americanfootball_ncaaf: "🏈 NCAAF",
  americanfootball_cfl: "🏈 CFL",
  // Basketball
  basketball_nba: "🏀 NBA",
  basketball_ncaab: "🏀 NCAAB",
  basketball_wnba: "🏀 WNBA",
  basketball_wncaab: "🏀 WNCAAB",
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
  tennis_atp_aus_open: "🎾 Aus Open",
  tennis_atp_us_open: "🎾 US Open",
  tennis_atp_wimbledon: "🎾 Wimbledon",
  tennis_atp_french_open: "🎾 French Open",
  // Politics
  politics_us_presidential_election_winner: "🗳️ Election",
};

function getSportDisplay(sportKey: string): string {
  return SPORT_DISPLAY[sportKey] || sportKey.split("_").pop()?.toUpperCase() || sportKey;
}

/**
 * Card displaying a single event with win probabilities.
 */
export default function EventCard({ event, showSport = true }: EventCardProps) {
  const odds = event.current_odds;
  const homeProb = odds?.home_probability;
  const awayProb = odds?.away_probability;

  const isLive = event.status === "live";
  const startingSoon = !isLive && isStartingSoon(event.commence_time);

  // Determine favorite
  const homeFavorite = (homeProb ?? 0) >= (awayProb ?? 0);

  return (
    <Link href={`/events/${event.id}`}>
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4 hover:shadow-md transition-shadow cursor-pointer">
        {/* Header: Sport badge and game time */}
        <div className="flex justify-between items-center mb-3">
          <div className="flex items-center gap-2">
            {showSport && event.sport && (
              <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                {getSportDisplay(event.sport)}
              </span>
            )}
            {isLive && (
              <span className="text-xs font-bold text-red-600 bg-red-50 px-2 py-0.5 rounded animate-pulse">
                LIVE
              </span>
            )}
            {startingSoon && (
              <span className="text-xs font-medium text-orange-600 bg-orange-50 px-2 py-0.5 rounded">
                Starting Soon
              </span>
            )}
          </div>
          <span className="text-xs text-gray-500">
            {formatGameTime(event.commence_time)}
          </span>
        </div>

        {/* Teams and Probabilities */}
        <div className="space-y-3">
          {/* Home Team */}
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2">
              {homeFavorite && homeProb !== null && (
                <span className="w-2 h-2 rounded-full bg-green-500" />
              )}
              <span className={`font-semibold ${homeFavorite ? "text-gray-900" : "text-gray-700"}`}>
                {event.home_team}
              </span>
              {isLive && event.home_score !== null && (
                <span className="text-lg font-bold text-gray-900 ml-2">
                  {event.home_score}
                </span>
              )}
            </div>
            <span
              className={`text-2xl font-bold ${
                homeFavorite ? "text-green-600" : "text-gray-500"
              }`}
            >
              {formatProbability(homeProb)}
            </span>
          </div>

          {/* Probability Bar */}
          <ProbabilityBar
            homeProbability={homeProb}
            awayProbability={awayProb}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
            showLabels={false}
            size="sm"
          />

          {/* Away Team */}
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2">
              {!homeFavorite && awayProb !== null && (
                <span className="w-2 h-2 rounded-full bg-blue-500" />
              )}
              <span className={`font-semibold ${!homeFavorite ? "text-gray-900" : "text-gray-700"}`}>
                {event.away_team}
              </span>
              {isLive && event.away_score !== null && (
                <span className="text-lg font-bold text-gray-900 ml-2">
                  {event.away_score}
                </span>
              )}
            </div>
            <span
              className={`text-2xl font-bold ${
                !homeFavorite ? "text-blue-600" : "text-gray-500"
              }`}
            >
              {formatProbability(awayProb)}
            </span>
          </div>
        </div>

        {/* Footer: Additional odds info */}
        {odds && (odds.spread !== null || odds.over_under !== null) && (
          <div className="mt-3 pt-3 border-t border-gray-100 flex gap-4 text-xs text-gray-500">
            {odds.spread !== null && (
              <span>
                Spread: <span className="font-medium text-gray-700">{odds.spread > 0 ? `+${odds.spread}` : odds.spread}</span>
              </span>
            )}
            {odds.over_under !== null && (
              <span>
                O/U: <span className="font-medium text-gray-700">{odds.over_under}</span>
              </span>
            )}
          </div>
        )}
      </div>
    </Link>
  );
}
