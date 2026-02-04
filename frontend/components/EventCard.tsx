"use client";

import Link from "next/link";
import type { Event } from "@/lib/types";
import { formatProbability } from "@/lib/api";
import { getLeagueDisplay, getEmojiForLeague } from "@/lib/sportCategories";
import { useAnalytics } from "@/hooks";
import PulseBadge from "./PulseBadge";

type SourceSection = 'featured' | 'sport_category' | 'recently_finished' | 'archived' | 'search_results' | 'pinned';

interface EventCardProps {
  event: Event;
  showSport?: boolean;
  /** Source section for analytics tracking */
  sourceSection?: SourceSection;
  /** Position in list for analytics tracking */
  positionIndex?: number;
  /** Optional highlight label from backend */
  highlightLabel?: string | null;
  /** Whether the event is pinned */
  isPinned?: boolean;
  /** Callback when pin is toggled */
  onPinToggle?: (eventId: number) => void;
  /** Whether max pins has been reached (disable pin button) */
  pinDisabled?: boolean;
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
  highlightLabel,
  isPinned = false,
  onPinToggle,
  pinDisabled = false,
}: EventCardProps) {
  const { trackEventCardClick } = useAnalytics();

  // Handle pin button click (prevent navigation)
  const handlePinClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (onPinToggle) {
      onPinToggle(event.id);
    }
  };
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

  // Use highlight flags from backend if available
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

  // Use highlight flags for styling if available
  const isFeaturedHighlight = event.highlight?.flags?.favorite_switched ||
    event.highlight?.flags?.is_upset;

  // Card border/background based on state
  const cardClasses = effectivelyLive
    ? "bg-gradient-to-br from-emerald-50 to-white border-2 border-emerald-200"
    : isFeaturedHighlight
    ? "bg-gradient-to-br from-amber-50 to-white border-2 border-amber-300"
    : isCloseGame
    ? "bg-white border-2 border-amber-200"
    : "bg-white border border-mist";

  return (
    <Link href={`/events/${event.id}`} className="h-full" onClick={handleCardClick}>
      <div
        className={`h-full flex flex-col rounded-card shadow-card p-4 hover:shadow-card-hover transition-all cursor-pointer group/card ${cardClasses}`}
      >
        {/* Header: Sport, League, Status */}
        <div className="flex justify-between items-start mb-3">
          <div className="flex items-center gap-2 flex-wrap">
            {/* Pin button - always visible but subtle, more prominent on hover */}
            {onPinToggle && (
              <button
                onClick={handlePinClick}
                disabled={pinDisabled && !isPinned}
                className={`
                  p-1 rounded-full transition-all
                  ${isPinned
                    ? 'text-amber-500 bg-amber-50 hover:bg-amber-100'
                    : 'text-slate/30 hover:text-slate hover:bg-slate/10 group-hover/card:text-slate/50'
                  }
                  ${pinDisabled && !isPinned ? 'cursor-not-allowed opacity-30' : ''}
                  focus:outline-none focus:ring-2 focus:ring-amber-300
                `}
                title={isPinned ? 'Unpin event' : pinDisabled ? 'Maximum 6 pins' : 'Pin event'}
                aria-label={isPinned ? 'Unpin event' : 'Pin event'}
              >
                <PinIcon filled={isPinned} className="w-4 h-4" />
              </button>
            )}
            {showSport && event.sport && (
              <span className="text-sm bg-slate/10 px-2 py-0.5 rounded-full flex items-center gap-1">
                <span>{sportEmoji}</span>
                <span className="text-slate font-medium">
                  {getLeagueDisplay(event.sport)}
                </span>
              </span>
            )}
          </div>

          {/* Status Badge and Time */}
          <div className="flex items-center gap-1.5">
            {/* Start time for scheduled games - always show in this location */}
            {!isLive && !isFinished && (
              <span className="text-xs text-slate">
                {timeStr}
              </span>
            )}
            {/* Highlight label from backend (e.g., "Upset brewing", "Close game") */}
            {highlightLabel && !effectivelyLive && (
              <span className="flex items-center gap-1 bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full text-xs font-semibold">
                {highlightLabel}
              </span>
            )}
            {effectivelyLive && (
              <>
                <span className="flex items-center gap-1.5 bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full text-xs font-semibold">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  {highlightLabel || "LIVE"}
                </span>
                {/* Show live Pulse score with tooltip */}
                {event.pulse && (
                  <PulseBadge pulse={event.pulse} size="sm" />
                )}
              </>
            )}
            {isCompleted && (
              <>
                <span className="flex items-center gap-1 bg-slate/10 text-slate px-2 py-0.5 rounded-full text-xs font-medium">
                  ✅ Final
                </span>
                {/* Show Pulse badge for all completed games */}
                {event.pulse && (
                  <PulseBadge pulse={event.pulse} size="sm" />
                )}
              </>
            )}
            {isClosed && (
              <>
                <span className="flex items-center gap-1 bg-slate/10 text-slate px-2 py-0.5 rounded-full text-xs font-medium">
                  🔒 Closed
                </span>
                {/* Show Pulse badge for closed games too */}
                {event.pulse && (
                  <PulseBadge pulse={event.pulse} size="sm" />
                )}
              </>
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

        {/* Footer: Projected Score for future games, bookmaker count */}
        <div className="mt-3 pt-3 border-t border-mist/50 flex justify-between items-center">
          {/* Left side: Projected Score or broadcast info */}
          <div className="flex items-center gap-1.5 text-sm">
            {!isLive && !isFinished && odds && odds.projected_home_score !== null && odds.projected_away_score !== null ? (
              <>
                <span className="text-slate">Projected:</span>
                <span className="font-mono font-medium text-graphite">
                  {Math.round(odds.projected_home_score)} - {Math.round(odds.projected_away_score)}
                </span>
              </>
            ) : (isLive || isFinished) ? (
              <span className="text-xs text-slate">
                {effectivelyLive ? "🔄 Live updates" : `Played ${timeStr}`}
              </span>
            ) : null}
            {/* Broadcast info from ESPN */}
            {event.espn?.broadcast && (
              <span className="text-xs text-silver ml-1" title={event.espn.broadcast}>
                📺 {event.espn.broadcast.split(",")[0].trim()}
              </span>
            )}
          </div>

          {/* Right side: Bookmaker count and Close game indicator */}
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

/**
 * Pin icon - pushpin style
 */
function PinIcon({ filled, className }: { filled: boolean; className?: string }) {
  if (filled) {
    // Filled pushpin
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor">
        <path d="M16 4c0-.55-.22-1.05-.58-1.41-.37-.37-.86-.59-1.42-.59s-1.05.22-1.41.58l-6.01 6.01C5.22 9.95 4 11.59 4 13.5c0 1.1.45 2.1 1.17 2.83L2 19.5l1.41 1.41 3.17-3.17c.73.72 1.73 1.17 2.83 1.17 1.91 0 3.55-1.22 4.91-2.58l6.01-6.01c.36-.36.58-.86.58-1.41s-.22-1.05-.58-1.41c-.37-.37-.86-.59-1.42-.59s-1.05.22-1.41.58l-4.95 4.95-2.12-2.12L16 4z"/>
      </svg>
    );
  }

  // Outline pushpin
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v1H5V5z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 11v6" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 17h6" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 6h14l-2 5H7L5 6z" />
    </svg>
  );
}
