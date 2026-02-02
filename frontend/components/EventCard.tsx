"use client";

import Link from "next/link";
import type { Event } from "@/lib/types";
import { formatProbability, isStartingSoon } from "@/lib/api";
import { getLeagueDisplay, getEmojiForLeague, formatTimeUntil, getLeagueTier } from "@/lib/sportCategories";
import { useAnalytics } from "@/hooks";
import { calculateMinutesToStart, isCloseGame as checkCloseGame } from "@/lib/analytics";

type SourceSection = 'featured' | 'sport_category' | 'recently_finished' | 'archived' | 'search_results';

interface EventCardProps {
  event: Event;
  showSport?: boolean;
  /** Source section for analytics tracking */
  sourceSection?: SourceSection;
  /** Position in list for analytics tracking */
  positionIndex?: number;
}

// Staleness thresholds
const STALE_ODDS_MINUTES = 30; // Odds not updated in 30 minutes = stale
const MAX_LIVE_HOURS = 4; // If "live" for more than 4 hours, needs review

/**
 * Check if an event's live status is stale and needs review.
 * Returns: { isStale: boolean, isNeedsReview: boolean, staleMinutes: number | null }
 */
function checkEventStaleness(event: Event): {
  isStale: boolean;
  isNeedsReview: boolean;
  staleMinutes: number | null;
} {
  const now = new Date();
  const commenceTime = new Date(event.commence_time);
  const hoursSinceStart = (now.getTime() - commenceTime.getTime()) / (1000 * 60 * 60);

  // Check if event has been "live" for too long (>4 hours without completion)
  const isNeedsReview = event.status === "live" && hoursSinceStart > MAX_LIVE_HOURS;

  // Check if odds data is stale (not updated in 30+ minutes)
  let isStale = false;
  let staleMinutes: number | null = null;

  if (event.current_odds?.captured_at) {
    const lastUpdate = new Date(event.current_odds.captured_at);
    const minutesSinceUpdate = (now.getTime() - lastUpdate.getTime()) / (1000 * 60);

    if (minutesSinceUpdate > STALE_ODDS_MINUTES) {
      isStale = true;
      staleMinutes = Math.round(minutesSinceUpdate);
    }
  }

  return { isStale, isNeedsReview, staleMinutes };
}

/**
 * Redesigned Event card with:
 * - Information density: state, time, score, projected score
 * - Color for importance: live games green, close games amber border
 * - Emoji throughout
 * - Compact probability display
 */
export default function EventCard({
  event,
  showSport = true,
  sourceSection = 'sport_category',
  positionIndex = 0,
}: EventCardProps) {
  const { trackEventCardClick } = useAnalytics();
  const odds = event.current_odds;
  const homeProb = odds?.home_probability;
  const awayProb = odds?.away_probability;

  // Handle card click with analytics
  const handleCardClick = () => {
    trackEventCardClick(event, sourceSection, positionIndex);
  };

  // Check if game has actually started based on commence_time
  const hasStarted = new Date(event.commence_time).getTime() <= Date.now();

  // Only consider "live" if status is "live" AND game has actually started
  const isLive = event.status === "live" && hasStarted;
  const isCompleted = event.status === "completed";
  const isClosed = event.status === "closed";
  const isFinished = isCompleted || isClosed;
  const startingSoon = !isLive && !isFinished && isStartingSoon(event.commence_time);

  // Check for stale data
  const { isStale, isNeedsReview, staleMinutes } = checkEventStaleness(event);

  // Show all live events as live (stale/needs review tracked internally for analytics only)
  const effectivelyLive = isLive;

  // Determine favorite
  const homeFavorite = (homeProb ?? 0) >= (awayProb ?? 0);

  // Is this a close game? (within 10% of 50/50)
  const isCloseGame = homeProb !== null && homeProb !== undefined &&
    Math.abs(homeProb - 0.5) < 0.1 && !isFinished;

  // Format time compactly
  const gameTime = new Date(event.commence_time);
  const timeStr = gameTime.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });

  // Get sport emoji
  const sportEmoji = event.sport ? getEmojiForLeague(event.sport) : "🏆";

  // Card border/background based on state (no amber warning styles for users)
  const cardClasses = effectivelyLive
    ? "bg-gradient-to-br from-emerald-50 to-white border-2 border-emerald-200"
    : isCloseGame
    ? "bg-white border-2 border-amber-200"
    : "bg-white border border-mist";

  return (
    <Link href={`/events/${event.id}`} className="h-full" onClick={handleCardClick}>
      <div
        className={`h-full flex flex-col rounded-card shadow-card p-4 hover:shadow-card-hover transition-all cursor-pointer ${cardClasses}`}
      >
        {/* Header: Sport, League, Status */}
        <div className="flex justify-between items-start mb-3">
          <div className="flex items-center gap-2 flex-wrap">
            {showSport && event.sport && (
              <span className="text-sm bg-slate/10 px-2 py-0.5 rounded-full flex items-center gap-1">
                <span>{sportEmoji}</span>
                <span className="text-slate font-medium">
                  {getLeagueDisplay(event.sport)}
                </span>
              </span>
            )}
          </div>

          {/* Status Badge */}
          <div className="flex items-center gap-1.5">
            {/* Note: "Needs Review" and "Stale" indicators are tracked internally but not shown to users */}
            {effectivelyLive && (
              <span className="flex items-center gap-1.5 bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full text-xs font-semibold">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                LIVE
              </span>
            )}
            {isCompleted && (
              <>
                <span className="flex items-center gap-1 bg-slate/10 text-slate px-2 py-0.5 rounded-full text-xs font-medium">
                  ✅ Final
                </span>
                {/* Show GEI badge for exciting completed games */}
                {event.excitement && event.excitement.percentile_global && event.excitement.percentile_global >= 75 && (
                  <span
                    className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
                      event.excitement.percentile_global >= 95
                        ? "bg-orange-100 text-orange-700"
                        : event.excitement.percentile_global >= 90
                        ? "bg-amber-100 text-amber-700"
                        : "bg-yellow-100 text-yellow-700"
                    }`}
                    title={`${event.excitement.label} - Top ${100 - event.excitement.percentile_global}% most exciting games`}
                  >
                    {event.excitement.emoji || "⚡"} {event.excitement.percentile_global}%
                  </span>
                )}
              </>
            )}
            {isClosed && (
              <span className="flex items-center gap-1 bg-slate/10 text-slate px-2 py-0.5 rounded-full text-xs font-medium">
                🔒 Closed
              </span>
            )}
            {startingSoon && !isLive && !isFinished && (
              <span className="flex items-center gap-1 bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full text-xs font-semibold">
                ⏰ {formatTimeUntil(event.commence_time)}
              </span>
            )}
            {!isLive && !isFinished && !startingSoon && (
              <span className="text-xs text-slate">
                {timeStr}
              </span>
            )}
          </div>
        </div>

        {/* Prominent Score Display for live/finished games */}
        {(isLive || isFinished) && event.home_score !== null && event.away_score !== null ? (
          <div className="flex items-center justify-center gap-4 py-2 mb-2 bg-white/60 rounded-lg">
            <div className="text-center">
              <div className={`text-2xl font-bold font-mono ${
                effectivelyLive ? "text-emerald-600" : "text-graphite"
              }`}>
                {event.home_score}
              </div>
              <div className="text-xs text-slate truncate max-w-[80px]">
                {event.home_team.split(" ").pop()}
              </div>
            </div>
            <div className="text-lg text-slate font-medium">—</div>
            <div className="text-center">
              <div className={`text-2xl font-bold font-mono ${
                effectivelyLive ? "text-emerald-600" : "text-graphite"
              }`}>
                {event.away_score}
              </div>
              <div className="text-xs text-slate truncate max-w-[80px]">
                {event.away_team.split(" ").pop()}
              </div>
            </div>
          </div>
        ) : null}

        {/* Main Content: Teams, Scores, Probabilities */}
        <div className="space-y-2 flex-grow">
          {/* Home Team Row */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <span
                className={`text-base font-semibold truncate ${
                  homeFavorite ? "text-graphite" : "text-slate"
                }`}
              >
                {event.home_team}
              </span>
            </div>
            {/* Probability */}
            <span
              className={`font-mono text-xl font-bold tabular-nums ${
                homeFavorite ? "text-graphite" : "text-silver"
              }`}
            >
              {formatProbability(homeProb)}
            </span>
          </div>

          {/* Probability Bar - slim and subtle */}
          <div className="h-1.5 w-full rounded-full overflow-hidden flex bg-slate/10">
            <div
              className={`transition-all duration-300 ${
                homeFavorite
                  ? effectivelyLive ? "bg-emerald-500" : "bg-graphite"
                  : "bg-slate/30"
              }`}
              style={{ width: `${(homeProb ?? 0.5) * 100}%` }}
            />
            <div
              className={`transition-all duration-300 ${
                !homeFavorite
                  ? effectivelyLive ? "bg-emerald-500" : "bg-graphite"
                  : "bg-slate/30"
              }`}
              style={{ width: `${(awayProb ?? 0.5) * 100}%` }}
            />
          </div>

          {/* Away Team Row */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <span
                className={`text-base font-semibold truncate ${
                  !homeFavorite ? "text-graphite" : "text-slate"
                }`}
              >
                {event.away_team}
              </span>
            </div>
            {/* Probability */}
            <span
              className={`font-mono text-xl font-bold tabular-nums ${
                !homeFavorite ? "text-graphite" : "text-silver"
              }`}
            >
              {formatProbability(awayProb)}
            </span>
          </div>
        </div>

        {/* Footer: Projected Score for future games, Time for live/finished */}
        <div className="mt-3 pt-3 border-t border-mist/50 flex justify-between items-center">
          {/* Projected Score (only for future games with odds) */}
          {!isLive && !isFinished && odds && odds.projected_home_score !== null && odds.projected_away_score !== null && (
            <div className="flex items-center gap-1.5 text-sm">
              <span className="text-slate">Projected:</span>
              <span className="font-mono font-medium text-graphite">
                {Math.round(odds.projected_home_score)} - {Math.round(odds.projected_away_score)}
              </span>
            </div>
          )}

          {/* For live/finished, show time info - don't duplicate stale indicator */}
          {(isLive || isFinished) && (
            <div className="text-xs text-slate">
              {effectivelyLive ? "🔄 Live" : isFinished ? `Played ${timeStr}` : `Started ${timeStr}`}
            </div>
          )}

          {/* Empty state filler */}
          {!isLive && !isFinished && (!odds?.projected_home_score || !odds?.projected_away_score) && (
            <div className="text-xs text-slate">
              {timeStr}
            </div>
          )}

          {/* Right side: Close game indicator and/or bookmaker count */}
          <div className="flex items-center gap-2">
            {/* Bookmaker count indicator */}
            {odds?.bookmaker_count && odds.bookmaker_count > 1 && (
              <span
                className="text-xs text-silver cursor-help border-b border-dotted border-silver/50 hover:text-slate hover:border-slate transition-colors px-1 py-0.5 -mx-1"
                title={event.bookmaker_odds?.map(b => b.bookmaker).join(", ")}
              >
                {odds.bookmaker_count} books
              </span>
            )}
            {/* Close game indicator */}
            {isCloseGame && (
              <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">
                🔥 Close
              </span>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}
