"use client";

import Link from "next/link";
import type { Event } from "@/lib/types";
import { formatProbability, isStartingSoon } from "@/lib/api";
import { getLeagueDisplay, getEmojiForLeague } from "@/lib/sportCategories";

interface EventCardProps {
  event: Event;
  showSport?: boolean;
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
export default function EventCard({ event, showSport = true }: EventCardProps) {
  const odds = event.current_odds;
  const homeProb = odds?.home_probability;
  const awayProb = odds?.away_probability;

  const isLive = event.status === "live";
  const isCompleted = event.status === "completed";
  const isClosed = event.status === "closed";
  const isFinished = isCompleted || isClosed;
  const startingSoon = !isLive && !isFinished && isStartingSoon(event.commence_time);

  // Check for stale data
  const { isStale, isNeedsReview, staleMinutes } = checkEventStaleness(event);

  // If event needs review (live for too long), treat it as potentially closed
  const effectivelyLive = isLive && !isNeedsReview && !isStale;

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

  // Card border/background based on state
  const cardClasses = effectivelyLive
    ? "bg-gradient-to-br from-emerald-50 to-white border-2 border-emerald-200"
    : isNeedsReview || isStale
    ? "bg-gradient-to-br from-amber-50 to-white border-2 border-amber-300"
    : isCloseGame
    ? "bg-white border-2 border-amber-200"
    : "bg-white border border-mist";

  return (
    <Link href={`/events/${event.id}`}>
      <div
        className={`rounded-card shadow-card p-4 hover:shadow-card-hover transition-all cursor-pointer ${cardClasses}`}
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
            {/* Stale/Review status takes priority over live */}
            {isNeedsReview && (
              <span className="flex items-center gap-1 bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full text-xs font-semibold">
                ⚠️ Review
              </span>
            )}
            {isStale && !isNeedsReview && isLive && (
              <span className="flex items-center gap-1 bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full text-xs font-semibold"
                    title={staleMinutes ? `Last updated ${staleMinutes} minutes ago` : undefined}>
                📡 Stale
              </span>
            )}
            {effectivelyLive && (
              <span className="flex items-center gap-1.5 bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full text-xs font-semibold">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                LIVE
              </span>
            )}
            {isCompleted && (
              <span className="flex items-center gap-1 bg-slate/10 text-slate px-2 py-0.5 rounded-full text-xs font-medium">
                ✅ Final
              </span>
            )}
            {isClosed && (
              <span className="flex items-center gap-1 bg-slate/10 text-slate px-2 py-0.5 rounded-full text-xs font-medium">
                🔒 Closed
              </span>
            )}
            {startingSoon && (
              <span className="flex items-center gap-1 bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full text-xs font-semibold">
                ⏰ Soon
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
                effectivelyLive ? "text-emerald-600" : (isStale || isNeedsReview) ? "text-amber-600" : "text-graphite"
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
                effectivelyLive ? "text-emerald-600" : (isStale || isNeedsReview) ? "text-amber-600" : "text-graphite"
              }`}>
                {event.away_score}
              </div>
              <div className="text-xs text-slate truncate max-w-[80px]">
                {event.away_team.split(" ").pop()}
              </div>
            </div>
          </div>
        ) : isLive && (event.home_score === null || event.away_score === null) ? (
          <div className="flex items-center justify-center py-2 mb-2 text-sm text-slate bg-white/60 rounded-lg">
            <span>📊 Score data pending...</span>
          </div>
        ) : null}

        {/* Main Content: Teams, Scores, Probabilities */}
        <div className="space-y-2">
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

          {/* For live/finished, show time info */}
          {(isLive || isFinished) && (
            <div className="text-xs text-slate">
              {effectivelyLive ? "🔄 Updating live" : isStale ? `⚠️ Stale (${staleMinutes}m ago)` : isNeedsReview ? "⚠️ Status unclear" : `Played ${timeStr}`}
            </div>
          )}

          {/* Empty state filler */}
          {!isLive && !isFinished && (!odds?.projected_home_score || !odds?.projected_away_score) && (
            <div className="text-xs text-slate">
              {timeStr}
            </div>
          )}

          {/* Close game indicator */}
          {isCloseGame && (
            <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">
              🔥 Close
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
