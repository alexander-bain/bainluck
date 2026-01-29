"use client";

import Link from "next/link";
import type { Event } from "@/lib/types";
import { formatProbability, formatGameTime, isStartingSoon } from "@/lib/api";
import { getLeagueDisplay } from "@/lib/sportCategories";
import ProbabilityBar from "./ProbabilityBar";

interface EventCardProps {
  event: Event;
  showSport?: boolean;
}

/**
 * Event card per design brief.
 * Clean, typography-driven, no team colors.
 * Probabilities in monospace, right-aligned.
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
      <div className="bg-white rounded-card shadow-card p-4 hover:shadow-card-hover transition-shadow cursor-pointer">
        {/* Header: Sport badge and live indicator */}
        <div className="flex justify-between items-center mb-3">
          <div className="flex items-center gap-2">
            {showSport && event.sport && (
              <span className="text-micro text-slate bg-mist px-2 py-0.5 rounded">
                {getLeagueDisplay(event.sport)}
              </span>
            )}
            {isLive && (
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald animate-pulse-live" />
                <span className="text-micro font-medium text-emerald">
                  LIVE
                </span>
              </div>
            )}
            {startingSoon && (
              <span className="text-micro text-amber">
                Soon
              </span>
            )}
          </div>
        </div>

        {/* Teams and Probabilities */}
        <div className="space-y-2">
          {/* Home Team */}
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2">
              <span className={`text-title-3 ${homeFavorite ? "text-graphite" : "text-slate"}`}>
                {event.home_team}
              </span>
              {isLive && event.home_score !== null && (
                <span className="text-body-strong text-graphite">
                  {event.home_score}
                </span>
              )}
            </div>
            <span
              className={`font-mono text-2xl font-bold tabular-nums ${
                homeFavorite ? "text-graphite" : "text-silver"
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
              <span className={`text-title-3 ${!homeFavorite ? "text-graphite" : "text-slate"}`}>
                {event.away_team}
              </span>
              {isLive && event.away_score !== null && (
                <span className="text-body-strong text-graphite">
                  {event.away_score}
                </span>
              )}
            </div>
            <span
              className={`font-mono text-2xl font-bold tabular-nums ${
                !homeFavorite ? "text-graphite" : "text-silver"
              }`}
            >
              {formatProbability(awayProb)}
            </span>
          </div>
        </div>

        {/* Footer: Game time */}
        <div className="mt-3 pt-3 border-t border-mist">
          <span className="text-caption text-slate">
            {formatGameTime(event.commence_time)}
          </span>
        </div>
      </div>
    </Link>
  );
}
