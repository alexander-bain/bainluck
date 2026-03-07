"use client";

import { useEffect } from "react";
import Link from "next/link";
import { motion, useSpring, useTransform } from "framer-motion";
import type { Event } from "@/lib/types";
import { getLeagueDisplay } from "@/lib/sportCategories";
import { useAnalytics } from "@/hooks";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import EIBadge from "./EIBadge";
import PersonalizedBadge from "./PersonalizedBadge";
import ProbabilityBar from "./ProbabilityBar";
import EntityImage from "./EntityImage";
import { isInternationalSport, flagUrl } from "@/lib/images";
import { teamColorStyle } from "@/lib/teamColors";
import { fadeIn } from "@/lib/animations";

type SourceSection = 'featured' | 'sport_category' | 'recently_finished' | 'archived' | 'search_results' | 'pinned' | 'my_stuff';

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
  /** Whether this item was personalized by the feed */
  personalized?: boolean;
  /** Personalization multiplier */
  multiplier?: number;
  /** Personalization reason strings */
  personalizationReasons?: string[];
}

// ---------------------------------------------------------------------------
// AnimatedProbability — smoothly counts between probability values
// ---------------------------------------------------------------------------
function AnimatedProbability({
  value,
  className,
}: {
  value: number | null;
  className?: string;
}) {
  const springValue = useSpring(value !== null ? value * 100 : 0, {
    stiffness: 80,
    damping: 20,
    mass: 0.5,
  });
  const display = useTransform(springValue, (v: number) => `${Math.round(v)}%`);

  // Update spring target when value changes
  useEffect(() => {
    springValue.set(value !== null ? value * 100 : 0);
  }, [value, springValue]);

  if (value === null) {
    return <span className={className}>-</span>;
  }

  return <motion.span className={className}>{display}</motion.span>;
}

export default function EventCard({
  event,
  showSport = true,
  sourceSection = 'sport_category',
  positionIndex = 0,
  highlightLabel,
  isPinned = false,
  onPinToggle,
  pinDisabled = false,
  personalized,
  multiplier,
  personalizationReasons,
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
  const opening = event.opening_odds;

  // Determine which probability to display based on game status
  let homeProb: number | null;
  let awayProb: number | null;

  if ((event.status === "completed" || event.status === "closed") && opening) {
    homeProb = opening.home_probability;
    awayProb = opening.away_probability;
  } else {
    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
  }

  const handleCardClick = () => {
    trackEventCardClick(event, sourceSection, positionIndex);
  };

  const hasStarted = new Date(event.commence_time).getTime() <= Date.now();
  const isLive = event.status === "live" && hasStarted;
  const isCompleted = event.status === "completed";
  const isClosed = event.status === "closed";
  const isFinished = isCompleted || isClosed;
  const homeFavorite = (homeProb ?? 0) >= (awayProb ?? 0);

  // Format time and date compactly
  const gameTime = new Date(event.commence_time);
  const now = new Date();
  const isToday = gameTime.toDateString() === now.toDateString();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const isTomorrow = gameTime.toDateString() === tomorrow.toDateString();
  
  const timeStr = gameTime.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
  
  // For upcoming: show "Today 7:00 PM" or "Mar 8 7:00 PM"
  const dateTimeStr = isToday
    ? `Today ${timeStr}`
    : isTomorrow
      ? `Tomorrow ${timeStr}`
      : `${gameTime.toLocaleDateString("en-US", { month: "short", day: "numeric" })} ${timeStr}`;
  
  // For finished: show just the date
  const finishedDateStr = gameTime.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: gameTime.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
  });

  // International sport detection — show flags instead of team logos
  const showFlags = isInternationalSport(event.sport);
  const homeFlagUrl = showFlags ? flagUrl(event.home_team) : null;
  const awayFlagUrl = showFlags ? flagUrl(event.away_team) : null;

  // Short team names (last word) for compact display
  const homeShort = event.home_team.split(" ").pop() || event.home_team;
  const awayShort = event.away_team.split(" ").pop() || event.away_team;

  return (
    <Link href={`/events/${event.id}`} className="h-full" onClick={handleCardClick}>
      <motion.div
        variants={fadeIn}
        initial="hidden"
        animate="visible"
      >
        <Card
          className={cn(
            "h-full flex flex-col p-3 sm:p-4 transition-all cursor-pointer group/card",
            "bg-surface-card border-surface-border",
            "hover:bg-surface-elevated hover:shadow-card-hover hover:scale-[1.005] hover:border-surface-elevated",
            isLive && "border-l-[3px] border-l-accent-live ring-1 ring-accent-live/20",
            isFinished && "opacity-80 hover:opacity-100 hover:scale-100",
          )}
          style={teamColorStyle(
            event.home_team_data?.primary_color,
            event.away_team_data?.primary_color,
            event.home_team_data?.secondary_color,
            event.away_team_data?.secondary_color,
          )}
        >
          {/* Top bar: league + status + pin */}
          <div className="flex items-center justify-between gap-2 mb-2.5">
            <div className="flex items-center gap-1.5 min-w-0">
              {showSport && event.sport && (
                <span className="text-micro-xs text-text-muted uppercase tracking-widest truncate">
                  {getLeagueDisplay(event.sport)}
                </span>
              )}
              {highlightLabel && !isLive && (
                <span className="text-micro-xs bg-accent-warning/15 text-accent-warning px-1.5 py-0.5 rounded">
                  {highlightLabel}
                </span>
              )}
              <PersonalizedBadge
                personalized={personalized}
                multiplier={multiplier}
                personalizationReasons={personalizationReasons}
              />
            </div>

            <div className="flex items-center gap-1.5 flex-shrink-0">
              {isLive && (
                <span className="flex items-center gap-1 bg-accent-live/15 text-accent-live px-2 py-0.5 rounded text-micro-xs font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
                  {/* Show period/clock if available, otherwise LIVE */}
                  {event.espn?.period || event.espn?.game_clock
                    ? `${event.espn.period || ""}${event.espn.period && event.espn.game_clock ? " " : ""}${event.espn.game_clock || ""}`
                    : highlightLabel || "LIVE"}
                </span>
              )}
              {isLive && (event.ei || event.pulse) && (
                <EIBadge ei={(event.ei || event.pulse)!} size="sm" isLive />
              )}
              {!isLive && !isFinished && (
                <span className="text-micro text-text-muted">{dateTimeStr}</span>
              )}
              {isFinished && (
                <>
                  <span className="text-micro-xs text-text-muted">{finishedDateStr}</span>
                  <span className="text-micro-xs text-text-muted uppercase">Final</span>
                  {(event.ei || event.pulse) && <EIBadge ei={(event.ei || event.pulse)!} size="sm" />}
                </>
              )}
              {/* Pin button */}
              {onPinToggle && (
                <button
                  onClick={handlePinClick}
                  disabled={pinDisabled && !isPinned}
                  className={cn(
                    "p-1 rounded transition-all",
                    isPinned
                      ? 'text-accent-warning'
                      : 'text-text-muted/30 hover:text-text-muted group-hover/card:text-text-muted/50',
                    pinDisabled && !isPinned && 'cursor-not-allowed opacity-30',
                  )}
                  title={isPinned ? 'Unpin' : pinDisabled ? 'Max 6 pins' : 'Pin'}
                  aria-label={isPinned ? 'Unpin event' : 'Pin event'}
                >
                  <PinIcon filled={isPinned} className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Finished: centered score block */}
          {isFinished && event.home_score !== null && event.away_score !== null && (
            <div className="flex items-center justify-center gap-3 py-1.5 mb-2 bg-surface-elevated/50 rounded">
              <div className="text-center">
                <div className={cn(
                  "font-mono text-lg font-bold",
                  event.home_score! > event.away_score! ? "text-text-primary" : "text-text-muted",
                )}>
                  {event.home_score}
                </div>
                <div className="text-[9px] text-text-muted uppercase">{homeShort}</div>
              </div>
              <span className="text-text-muted text-xs">—</span>
              <div className="text-center">
                <div className={cn(
                  "font-mono text-lg font-bold",
                  event.away_score! > event.home_score! ? "text-text-primary" : "text-text-muted",
                )}>
                  {event.away_score}
                </div>
                <div className="text-[9px] text-text-muted uppercase">{awayShort}</div>
              </div>
            </div>
          )}

          {/* Teams + Probabilities */}
          <div className="space-y-1.5 flex-grow">
            {/* Home team */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                {homeFlagUrl ? (
                  <img
                    src={homeFlagUrl}
                    alt={event.home_team}
                    width={20}
                    height={15}
                    loading="lazy"
                    className="w-5 h-[15px] object-cover rounded-sm flex-shrink-0"
                  />
                ) : event.home_team_data?.logo_small ? (
                  <img
                    src={event.home_team_data.logo_small}
                    alt=""
                    width={20}
                    height={20}
                    loading="lazy"
                    className="w-5 h-5 object-contain flex-shrink-0"
                  />
                ) : (
                  <div
                    className="w-5 h-5 rounded-sm flex-shrink-0 flex items-center justify-center text-[9px] font-bold text-white/90"
                    style={{ backgroundColor: "rgb(var(--team-home-primary))" }}
                  >
                    {event.home_team.split(" ").map(w => w.charAt(0)).join("").slice(0, 2).toUpperCase()}
                  </div>
                )}
                <span className={cn(
                  "text-sm font-medium truncate",
                  homeFavorite ? "text-text-primary" : "text-text-secondary",
                )}>
                  {event.home_team}
                </span>
                {/* Inline live score */}
                {isLive && event.home_score !== null && (
                  <span className="font-mono text-sm font-bold text-accent-live ml-auto">{event.home_score}</span>
                )}
              </div>
              {!isLive && (
                <AnimatedProbability
                  value={homeProb}
                  className={cn(
                    "font-mono tabular-nums",
                    homeFavorite ? "text-prob-md text-text-primary" : "text-prob-sm text-text-secondary",
                  )}
                />
              )}
              {isLive && (
                <AnimatedProbability
                  value={homeProb}
                  className="font-mono tabular-nums text-xs text-text-muted"
                />
              )}
            </div>

            {/* Team-colored probability bar */}
            <ProbabilityBar
              homeProbability={homeProb}
              homeFavorite={homeFavorite}
              useCSSVars
              height={isLive ? 3 : 5}
            />

            {/* Away team */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                {awayFlagUrl ? (
                  <img
                    src={awayFlagUrl}
                    alt={event.away_team}
                    width={20}
                    height={15}
                    loading="lazy"
                    className="w-5 h-[15px] object-cover rounded-sm flex-shrink-0"
                  />
                ) : event.away_team_data?.logo_small ? (
                  <img
                    src={event.away_team_data.logo_small}
                    alt=""
                    width={20}
                    height={20}
                    loading="lazy"
                    className="w-5 h-5 object-contain flex-shrink-0"
                  />
                ) : (
                  <div
                    className="w-5 h-5 rounded-sm flex-shrink-0 flex items-center justify-center text-[9px] font-bold text-white/90"
                    style={{ backgroundColor: "rgb(var(--team-away-primary))" }}
                  >
                    {event.away_team.split(" ").map(w => w.charAt(0)).join("").slice(0, 2).toUpperCase()}
                  </div>
                )}
                <span className={cn(
                  "text-sm font-medium truncate",
                  !homeFavorite ? "text-text-primary" : "text-text-secondary",
                )}>
                  {event.away_team}
                </span>
                {/* Inline live score */}
                {isLive && event.away_score !== null && (
                  <span className="font-mono text-sm font-bold text-accent-live ml-auto">{event.away_score}</span>
                )}
              </div>
              {!isLive && (
                <AnimatedProbability
                  value={awayProb}
                  className={cn(
                    "font-mono tabular-nums",
                    !homeFavorite ? "text-prob-md text-text-primary" : "text-prob-sm text-text-secondary",
                  )}
                />
              )}
              {isLive && (
                <AnimatedProbability
                  value={awayProb}
                  className="font-mono tabular-nums text-xs text-text-muted"
                />
              )}
            </div>
          </div>

          {/* Footer — contextual info (hide for finished games) */}
          {!isFinished && (
            <div className="mt-2.5 pt-2 border-t border-surface-border/50 flex justify-between items-center text-micro">
              {!isLive && odds && odds.projected_home_score !== null && odds.projected_away_score !== null ? (
                <span className="text-text-muted">
                  Proj <span className="font-mono text-text-secondary">{Math.round(odds.projected_home_score)}-{Math.round(odds.projected_away_score)}</span>
                </span>
              ) : isLive && opening ? (
                <span className="text-text-muted">
                  Opened <span className="font-mono text-text-secondary">{Math.round(opening.home_probability * 100)}/{Math.round((opening.away_probability ?? (1 - opening.home_probability)) * 100)}</span>
                </span>
              ) : null}
              {event.espn?.broadcast && (
                <span className="text-text-muted truncate ml-auto">
                  {event.espn.broadcast.split(",")[0].trim()}
                </span>
              )}
            </div>
          )}
        </Card>
      </motion.div>
    </Link>
  );
}

function PinIcon({ filled, className }: { filled: boolean; className?: string }) {
  if (filled) {
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor">
        <path d="M16 4c0-.55-.22-1.05-.58-1.41-.37-.37-.86-.59-1.42-.59s-1.05.22-1.41.58l-6.01 6.01C5.22 9.95 4 11.59 4 13.5c0 1.1.45 2.1 1.17 2.83L2 19.5l1.41 1.41 3.17-3.17c.73.72 1.73 1.17 2.83 1.17 1.91 0 3.55-1.22 4.91-2.58l6.01-6.01c.36-.36.58-.86.58-1.41s-.22-1.05-.58-1.41c-.37-.37-.86-.59-1.42-.59s-1.05.22-1.41.58l-4.95 4.95-2.12-2.12L16 4z"/>
      </svg>
    );
  }
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v1H5V5z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 11v6" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 17h6" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 6h14l-2 5H7L5 6z" />
    </svg>
  );
}
