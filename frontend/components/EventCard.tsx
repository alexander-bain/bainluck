"use client";

import { useEffect } from "react";
import { useSpring, useTransform } from "framer-motion";
import { motion } from "@/components/motion";
import type { Event } from "@/lib/types";
import { getLeagueDisplay } from "@/lib/sportCategories";
import { useAnalytics } from "@/hooks";
import { cn } from "@/lib/utils";
import EventCardShell from "./EventCardShell";
import PersonalizedBadge from "./PersonalizedBadge";
import ProbabilityBar from "./ProbabilityBar";
import EntityImage from "./EntityImage";
import { isInternationalSport, flagUrl, espnTeamLogoByName } from "@/lib/images";
import { teamColorStyle } from "@/lib/teamColors";
import TeamNameLink from "./TeamNameLink";
import { shouldWithholdProbability } from "@/lib/probabilityEvidence";
import { renderedDuelPercents } from "@/lib/renderedPercent";
import { formatFinishedGameLabel, formatLiveClockLabel } from "@/lib/gameTimeLabel";
import {
  isFinishedStatus,
  isSuspendedStatus,
  suspendedSummary,
} from "@/lib/eventState";

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
// AnimatedProbability — smoothly counts between ALREADY-RESOLVED whole percents
// ---------------------------------------------------------------------------
//
// #2787: this took a raw probability and did its own `Math.round(v * 100)`
// inside `useTransform`, which is what put the card's two chips outside the
// rendered-percent contract. The rounding happens on the SPRING's output, so a
// per-side `renderedPercent` at the call site would have been discarded — the
// contract has to be applied to the spring's TARGET. So the target is the whole
// percent now, and this component only animates towards it.
function AnimatedProbability({
  percent,
  className,
}: {
  percent: number | null;
  className?: string;
}) {
  const springValue = useSpring(percent ?? 0, {
    stiffness: 80,
    damping: 20,
    mass: 0.5,
  });
  const display = useTransform(springValue, (v: number) => `${Math.round(v)}%`);

  // Update spring target when value changes
  useEffect(() => {
    springValue.set(percent ?? 0);
  }, [percent, springValue]);

  if (percent === null) {
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

  // UX-P166 — the live footer's "Opened 62/38" prints both sides of one question
  // in fixed positions, which makes it a duel. Rounding the two independently
  // printed 101 whenever the opening line landed on a half-percent: measured on
  // production 2026-08-29, 207 of 24,117 events carrying an opening line do, and
  // none print 99. The away side is derived as `1 - home` when absent, exactly as
  // before, which is precisely what makes the pair an exact complement and the
  // both-sides-round-up case reachable.
  //
  // #2787 AMENDMENT: that reasoning was right and its SCOPE was wrong. The
  // HEADLINE CHIPS print both sides of the same question in fixed positions too
  // — home above, away below — so they are the same duel, and they were not
  // going through this. See `chipAwayPct`/`chipHomePct` below.
  const [openedAwayPct, openedHomePct] = renderedDuelPercents(
    opening?.away_probability ?? (opening ? 1 - opening.home_probability : null),
    opening?.home_probability,
  );

  // Determine which probability to display based on game status
  let homeProb: number | null;
  let awayProb: number | null;

  if (isFinishedStatus(event.status) && opening) {
    homeProb = opening.home_probability;
    awayProb = opening.away_probability;
  } else if (shouldWithholdProbability(event)) {
    // UX-P042 (#1640) — the only evidence is an untraded Polymarket midpoint, so
    // `current_odds` reads a confident 0.5/0.5 built from nothing. Show no number.
    homeProb = null;
    awayProb = null;
  } else {
    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
  }

  // #2787 — the fourth arm of #2084/#2085/#2279. The chips below print
  // `homeProb` and `awayProb` in two fixed slots of one card, and each side was
  // rounded ALONE inside `AnimatedProbability`, so an exact complement pair
  // landing on a half-percent on both sides rounded up twice: measured on
  // production 2026-09-03, `/sports/tennis_atp_us_open` printed 82/19, 20/81
  // and 18/83 on three of ~16 upcoming cards. Resolved ONCE here, as a pair, and
  // handed to the chips already whole — never a per-side round at the leaf.
  //
  // `homeFavorite` deliberately still reads the raw probabilities: which side is
  // emphasised is a comparison, not a printed number, and it must not flip on a
  // rounding tie.
  const [chipAwayPct, chipHomePct] = renderedDuelPercents(awayProb, homeProb);

  const handleCardClick = () => {
    trackEventCardClick(event, sourceSection, positionIndex);
  };

  const hasStarted = new Date(event.commence_time).getTime() <= Date.now();
  const isLive = event.status === "live" && hasStarted;
  const isFinished = isFinishedStatus(event.status);
  const isSuspended = isSuspendedStatus(event.status);
  const homeFavorite = (homeProb ?? 0) >= (awayProb ?? 0);

  // Format time and date compactly
  const gameTime = new Date(event.commence_time);
  // UX-P074: an unparseable/absent commence_time renders NO time chip. The
  // league rail now feeds this card and types that field nullable, and
  // `toLocaleTimeString` on an invalid Date prints the literal string
  // "Invalid Date" — a card is allowed to say nothing, never to say that.
  const hasGameTime = !Number.isNaN(gameTime.getTime());
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
  
  // For finished: show just the date. The impossible-state guard (L2-112 Item 2 /
  // gotcha #14 — a FINAL game can't be in the future when commence_time actually
  // holds a Kalshi close/resolution timestamp) now lives in one place for all
  // three surfaces. UX-P045: the "compact" style preserves this card's existing
  // month/day output exactly, so adopting the shared module is not a restyle.
  const finishedDateStr = formatFinishedGameLabel(
    event.commence_time,
    now.getTime(),
    "compact",
  );

  // International sport detection — show flags instead of team logos
  const showFlags = isInternationalSport(event.sport);
  const homeFlagUrl = showFlags ? flagUrl(event.home_team) : null;
  const awayFlagUrl = showFlags ? flagUrl(event.away_team) : null;

  // Short team names (last word) for compact display
  const homeShort = event.home_team.split(" ").pop() || event.home_team;
  const awayShort = event.away_team.split(" ").pop() || event.away_team;

  return (
    // UX-P083 (#1860) / UX-P154: the stable hook the browser rail counts and the
    // link-and-card treatment both live in `EventCardShell` now. Ruling 047's
    // acceptance is "the league page renders the SHARED event card", and that is
    // a claim about WHICH COMPONENT rendered — unanswerable from the DOM unless
    // the shared card marks itself. It moved one level down so the tournament
    // match list can make the same claim without copying a wrapper, which is
    // exactly the "reinventing the event card" Alex named.
    <EventCardShell
      href={`/events/${event.id}`}
      onClick={handleCardClick}
      live={isLive}
      finished={isFinished}
      ariaLabel={`${event.away_team} at ${event.home_team}${isLive ? " - Live" : isFinished ? " - Final" : ""}`}
      style={teamColorStyle(
        event.home_team_data?.primary_color,
        event.away_team_data?.primary_color,
        event.home_team_data?.secondary_color,
        event.away_team_data?.secondary_color,
      )}
    >
      <>
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
                  {/* Show period/clock if available, otherwise LIVE.
                      UX-P051 (#1710): "available" now means ESPN is reporting an
                      in-game state, not merely that the fields are non-empty —
                      this site printed the whole pre-game sentence followed by
                      "0.0". Composition and fallback are unchanged. */}
                  {formatLiveClockLabel(event.espn?.period, event.espn?.game_clock) || highlightLabel || "LIVE"}
                </span>
              )}
              {/* live/048: a suspended match must not advertise a start time.
                  Its commence_time is in the PAST and the clock has run out —
                  printing "Today 7:00 PM" beside it is the upcoming-branch
                  fall-through this state exists to avoid. */}
              {/* CERT-786 — one shared summary, not the bare badge this
                  originally carried. Four surfaces render this state and they
                  now render one string, so "the card says the same thing
                  wherever you meet it" is a property of the function rather
                  than of four editors remembering. Not uppercased: the settled
                  sibling below uppercases the single word "Final", and shouting
                  a whole sentence is a different register. */}
              {/* #2786 — HOME-AWAY, because that is what this component does
                  everywhere else: the FINAL block below prints home then away,
                  both live score slots put home above away, and the `Proj`
                  footer is home-away. The away-home default made this the only
                  numeric pair on the card reading the other way, and it shipped
                  an inverted score on production (event 15293347: "last score
                  6-3" for a 3-6 match, directly under the HOME team's name). */}
              {isSuspended && (
                <span className="text-micro-xs text-text-muted">
                  {suspendedSummary(event.away_score, event.home_score, "home-away")}
                </span>
              )}
              {!isLive && !isFinished && !isSuspended && hasGameTime && (
                <span className="text-micro text-text-muted">{dateTimeStr}</span>
              )}
              {isFinished && (
                <>
                  {finishedDateStr && <span className="text-micro-xs text-text-muted">{finishedDateStr}</span>}
                  <span className="text-micro-xs text-text-muted uppercase">Final</span>
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
                ) : (event.home_team_data?.logo_small || espnTeamLogoByName(event.home_team, event.sport)) ? (
                  <img
                    src={(event.home_team_data?.logo_small || espnTeamLogoByName(event.home_team, event.sport))!}
                    crossOrigin="anonymous"
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
                <TeamNameLink
                  name={event.home_team}
                  sportKey={event.sport}
                  className={cn(
                    "text-sm font-medium truncate hover:underline",
                    homeFavorite ? "text-text-primary" : "text-text-secondary",
                  )}
                />
                {/* Inline live score */}
                {isLive && event.home_score !== null && (
                  <span className="font-mono text-sm font-bold text-accent-live ml-auto" aria-label={`${event.home_team} score: ${event.home_score}`}>{event.home_score}</span>
                )}
              </div>
              {/* Probability chip — scheduled/live only; a FINAL card drops the
                  live-style chip for the settled score block above (L2-112 Item 2),
                  and so does a SUSPENDED one (live/048, CERT-792). `suspended` is
                  neither live nor finished, so it fell through to the pregame chip
                  and printed a confident 72%/28% two lines under "No result
                  reported" — the card contradicting itself in one glance. The
                  suspended summary above is the whole statement. */}
              {!isLive && !isFinished && !isSuspended && (
                <AnimatedProbability
                  percent={chipHomePct}
                  className={cn(
                    "font-mono tabular-nums",
                    homeFavorite ? "text-prob-md text-text-primary" : "text-prob-sm text-text-secondary",
                  )}
                />
              )}
              {isLive && (
                <AnimatedProbability
                  percent={chipHomePct}
                  className="font-mono tabular-nums text-xs text-text-muted"
                />
              )}
            </div>

            {/* Team-colored probability bar — hidden on FINAL (settled score
                above) and on SUSPENDED (CERT-792): a filled bar is the loudest
                claim on the card, and there is no live price behind it. */}
            {!isFinished && !isSuspended && (
              <ProbabilityBar
                homeProbability={homeProb}
                homeFavorite={homeFavorite}
                useCSSVars
                height={isLive ? 3 : 5}
              />
            )}

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
                ) : (event.away_team_data?.logo_small || espnTeamLogoByName(event.away_team, event.sport)) ? (
                  <img
                    src={(event.away_team_data?.logo_small || espnTeamLogoByName(event.away_team, event.sport))!}
                    alt=""
                    crossOrigin="anonymous"
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
                <TeamNameLink
                  name={event.away_team}
                  sportKey={event.sport}
                  className={cn(
                    "text-sm font-medium truncate hover:underline",
                    !homeFavorite ? "text-text-primary" : "text-text-secondary",
                  )}
                />
                {/* Inline live score */}
                {isLive && event.away_score !== null && (
                  <span className="font-mono text-sm font-bold text-accent-live ml-auto" aria-label={`${event.away_team} score: ${event.away_score}`}>{event.away_score}</span>
                )}
              </div>
              {/* Probability chip — scheduled/live only (see home team above). */}
              {!isLive && !isFinished && !isSuspended && (
                <AnimatedProbability
                  percent={chipAwayPct}
                  className={cn(
                    "font-mono tabular-nums",
                    !homeFavorite ? "text-prob-md text-text-primary" : "text-prob-sm text-text-secondary",
                  )}
                />
              )}
              {isLive && (
                <AnimatedProbability
                  percent={chipAwayPct}
                  className="font-mono tabular-nums text-xs text-text-muted"
                />
              )}
            </div>
          </div>

          {/* Footer — contextual info (hide for finished games, and for
              suspended ones: "Proj 6-4" is a pregame promise and the match is
              stopped, not upcoming — CERT-792). */}
          {!isFinished && !isSuspended && (
            <div className="mt-2.5 pt-2 border-t border-surface-border/50 flex justify-between items-center text-micro">
              {/* UX-P074: `!= null`, not `!== null`. An ABSENT key answered the
                  strict test with `undefined !== null` → true, and the card then
                  printed "Proj NaN-NaN". Found the moment the league rail — a
                  producer that carries a blend and no projection — started
                  feeding this shared card. */}
              {!isLive && odds && odds.projected_home_score != null && odds.projected_away_score != null ? (
                <span className="text-text-muted">
                  Proj <span className="font-mono text-text-secondary">{Math.round(odds.projected_home_score)}-{Math.round(odds.projected_away_score)}</span>
                </span>
              ) : isLive && opening && openedHomePct !== null && openedAwayPct !== null ? (
                <span className="text-text-muted">
                  Opened <span className="font-mono text-text-secondary">{openedHomePct}/{openedAwayPct}</span>
                </span>
              ) : null}
              {event.espn?.broadcast && (
                <span className="text-text-muted truncate ml-auto">
                  {event.espn.broadcast.split(",")[0].trim()}
                </span>
              )}
            </div>
          )}
      </>
    </EventCardShell>
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
