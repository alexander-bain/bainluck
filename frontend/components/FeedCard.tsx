"use client";

import Link from "next/link";
import Image from "next/image";
import type { FeedItem, FeedEventData, FeedFuturesData } from "@/lib/types";
import { formatProbability } from "@/lib/api";
import { getLeagueDisplay, getEmojiForLeague, getEmojiForCategory, getNameForCategory } from "@/lib/sportCategories";
import PersonalizedBadge from "./PersonalizedBadge";
import EntityImage from "./EntityImage";
import { isNonSportsCategory, isInternationalSport, flagUrl, espnTeamLogoByName } from "@/lib/images";
import { useAnalyticsContext } from "@/components/Analytics";

interface FeedCardProps {
  item: FeedItem;
  onThumbsUp?: (category: string) => void;
  onThumbsDown?: (category: string) => void;
  category?: string;
}

export default function FeedCard({ item, onThumbsUp, onThumbsDown, category }: FeedCardProps) {
  if (item.type === "event") {
    return (
      <EventFeedCard
        item={item}
        data={item.data as FeedEventData}
        onThumbsUp={onThumbsUp}
        onThumbsDown={onThumbsDown}
        category={category}
      />
    );
  }
  return (
    <FuturesFeedCard
      item={item}
      data={item.data as FeedFuturesData}
      onThumbsUp={onThumbsUp}
      onThumbsDown={onThumbsDown}
      category={category}
    />
  );
}

// ============================================================================
// Helpers
// ============================================================================

/** Format commence_time as a short game time string. */
function formatGameTime(commenceTime: string): string {
  const now = new Date();
  const game = new Date(commenceTime);
  const diffMs = game.getTime() - now.getTime();
  const diffHours = diffMs / (1000 * 60 * 60);

  // Already started or in the past
  if (diffMs <= 0) return "";

  const timeStr = game.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

  // Same calendar day
  const isToday =
    game.getDate() === now.getDate() &&
    game.getMonth() === now.getMonth() &&
    game.getFullYear() === now.getFullYear();
  if (isToday) return `Today ${timeStr}`;

  // Next calendar day
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const isTomorrow =
    game.getDate() === tomorrow.getDate() &&
    game.getMonth() === tomorrow.getMonth() &&
    game.getFullYear() === tomorrow.getFullYear();
  if (isTomorrow) return `Tomorrow ${timeStr}`;

  // Within the week — show day name
  if (diffHours < 168) {
    const dayName = game.toLocaleDateString([], { weekday: "short" });
    return `${dayName} ${timeStr}`;
  }

  // Further out — show date
  const dateStr = game.toLocaleDateString([], { month: "short", day: "numeric" });
  return `${dateStr} ${timeStr}`;
}

/** Format a finished game's date for staleness context. */
function formatFinishedDate(commenceTime: string): string {
  const game = new Date(commenceTime);
  const now = new Date();

  const isToday =
    game.getDate() === now.getDate() &&
    game.getMonth() === now.getMonth() &&
    game.getFullYear() === now.getFullYear();

  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday =
    game.getDate() === yesterday.getDate() &&
    game.getMonth() === yesterday.getMonth() &&
    game.getFullYear() === yesterday.getFullYear();

  const timeStr = game.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

  if (isToday) return `Today ${timeStr}`;
  if (isYesterday) return `Yesterday ${timeStr}`;

  return game.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

/** Format resolution date as a short string. */
function formatResolutionDate(dateStr: string | null): string | null {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = d.getTime() - now.getTime();
  if (diffMs <= 0) return null;
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  if (diffDays < 1) return "Resolves today";
  if (diffDays < 2) return "Resolves tomorrow";
  if (diffDays < 7) {
    return `Resolves ${d.toLocaleDateString([], { weekday: "short" })}`;
  }
  return `Resolves ${d.toLocaleDateString([], { month: "short", day: "numeric" })}`;
}

// ============================================================================
// Reason badge — styled pill with contextual icon (matches iOS EventCardView)
// ============================================================================

function reasonStyle(text: string): { icon: string | null; colorClass: string; bgClass: string } {
  const lower = text.toLowerCase();
  if (lower.includes("upset") || lower.includes("underdog")) {
    return { icon: "⚠", colorClass: "text-orange-500", bgClass: "bg-orange-500/10" };
  } else if (lower.includes("close") || lower.includes("tight") || lower.includes("even")) {
    return { icon: "⚖", colorClass: "text-blue-500", bgClass: "bg-blue-500/10" };
  } else if (lower.includes("line mov") || lower.includes("shifted") || lower.includes("odds")) {
    return { icon: "↕", colorClass: "text-purple-500", bgClass: "bg-purple-500/10" };
  } else if (lower.includes("starting soon")) {
    return { icon: "🕐", colorClass: "text-green-500", bgClass: "bg-green-500/10" };
  } else if (lower.includes("lead change") || lower.includes("wild") || lower.includes("exciting")) {
    return { icon: "⚡", colorClass: "text-yellow-500", bgClass: "bg-yellow-500/10" };
  }
  return { icon: null, colorClass: "text-text-secondary", bgClass: "" };
}

function ReasonBadge({ text, truncate }: { text: string; truncate?: boolean }) {
  const { icon, colorClass, bgClass } = reasonStyle(text);

  if (!bgClass) {
    // No special styling — render as plain text (backward compat)
    return <p className={`text-xs text-text-secondary ${truncate ? "truncate" : ""}`}>{text}</p>;
  }

  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-medium px-1.5 py-0.5 rounded-full ${colorClass} ${bgClass}`}>
      {icon && <span className="text-[10px]">{icon}</span>}
      <span className={truncate ? "truncate" : ""}>{text}</span>
    </span>
  );
}

// ============================================================================
// Thumbs buttons — shared by both card types
// ============================================================================

function ThumbButtons({
  category,
  onThumbsUp,
  onThumbsDown,
}: {
  category?: string;
  onThumbsUp?: (category: string) => void;
  onThumbsDown?: (category: string) => void;
}) {
  if (!category || (!onThumbsUp && !onThumbsDown)) return null;

  return (
    <div className="flex items-center gap-0.5 ml-auto flex-shrink-0">
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onThumbsUp?.(category);
        }}
        className="p-1 text-text-muted/40 hover:text-accent-live transition-colors rounded"
        title="More like this"
        aria-label="More like this"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
          <path d="M7 10v12" />
          <path d="M15 5.88L14 10h5.83a2 2 0 011.92 2.56l-2.33 8A2 2 0 0117.5 22H4a2 2 0 01-2-2v-8a2 2 0 012-2h2.76a2 2 0 001.79-1.11L12 2a3.13 3.13 0 013 3.88z" />
        </svg>
      </button>
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onThumbsDown?.(category);
        }}
        className="p-1 text-text-muted/40 hover:text-accent-danger transition-colors rounded"
        title="Less like this"
        aria-label="Less like this"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 14V2" />
          <path d="M9 18.12L10 14H4.17a2 2 0 01-1.92-2.56l2.33-8A2 2 0 016.5 2H20a2 2 0 012 2v8a2 2 0 01-2 2h-2.76a2 2 0 00-1.79 1.11L12 22a3.13 3.13 0 01-3-3.88z" />
        </svg>
      </button>
    </div>
  );
}

// ============================================================================
// Team logo — small inline logo with fallback
// ============================================================================

function TeamLogo({ url, name, color, isFlag, sport }: { url: string | null | undefined; name: string; color?: string | null; isFlag?: boolean; sport?: string | null }) {
  // Try primary URL, then ESPN fallback
  const resolvedUrl = url || (!isFlag ? espnTeamLogoByName(name, sport) : null);
  
  if (resolvedUrl) {
    return (
      <Image
        src={resolvedUrl}
        alt={name}
        width={20}
        height={isFlag ? 15 : 20}
        className={`flex-shrink-0 ${isFlag ? "rounded-sm" : "rounded-sm"}`}
        unoptimized
      />
    );
  }
  const initials = name.split(" ").map(w => w.charAt(0)).join("").slice(0, 2).toUpperCase();
  return (
    <div
      className="w-5 h-5 rounded-sm flex-shrink-0 flex items-center justify-center text-[9px] font-bold text-white/90"
      style={{ backgroundColor: color || "#6b7280" }}
    >
      {initials}
    </div>
  );
}

// ============================================================================
// Event Feed Card
// ============================================================================

function EventFeedCard({
  item,
  data,
  onThumbsUp,
  onThumbsDown,
  category,
}: {
  item: FeedItem;
  data: FeedEventData;
  onThumbsUp?: (category: string) => void;
  onThumbsDown?: (category: string) => void;
  category?: string;
}) {
  const { track } = useAnalyticsContext();
  const isLive = data.status === "live";
  const isFinished = data.status === "completed" || data.status === "closed";
  const isScheduled = data.status === "scheduled";
  const homeProb = data.current_odds?.home_probability ?? null;
  const awayProb = data.current_odds?.away_probability ?? null;
  const hasScore = (isLive || isFinished) && data.home_score !== null && data.away_score !== null;

  // Determine winner for finished events
  const homeWon = isFinished && data.home_score != null && data.away_score != null && data.home_score > data.away_score;
  const awayWon = isFinished && data.home_score != null && data.away_score != null && data.away_score > data.home_score;

  // For finished events, don't show probabilities — the score tells the story
  const displayHomeProb = isFinished ? null : homeProb;
  const displayAwayProb = isFinished ? null : awayProb;

  // Team colors for probability bar
  const homeColor = data.home_team_data?.primary_color ?? null;
  const awayColor = data.away_team_data?.primary_color ?? null;

  // International sport detection — show flags instead of team logos
  const showFlags = isInternationalSport(data.sport);
  const homeFlagImgUrl = showFlags ? flagUrl(data.home_team) : null;
  const awayFlagImgUrl = showFlags ? flagUrl(data.away_team) : null;

  // Sport emoji
  const sportEmoji = data.sport ? getEmojiForLeague(data.sport) : null;
  const leagueName = data.sport ? getLeagueDisplay(data.sport) : null;

  // Game time for scheduled events
  const gameTime = isScheduled ? formatGameTime(data.commence_time) : null;

  // Date/time for finished events (staleness context)
  const finishedTime = isFinished ? formatFinishedDate(data.commence_time) : null;

  // Opening odds context for live games
  const openedContext =
    (isLive || isFinished) && data.opening_odds?.home_probability != null && data.opening_odds?.away_probability != null
      ? `Opened ${Math.round(data.opening_odds.home_probability * 100)}/${Math.round(data.opening_odds.away_probability * 100)}`
      : null;

  // For the probability bar: finished events show opening odds, others show current
  const barHomeProb = isFinished
    ? (data.opening_odds?.home_probability ?? null)
    : displayHomeProb;
  const barAwayProb = isFinished
    ? (data.opening_odds?.away_probability ?? null)
    : displayAwayProb;

  return (
    <Link href={`/events/${data.id}`} onClick={() => {
      track('event_card_click', {
        event_id: data.id,
        sport: data.sport || 'unknown',
        league: data.sport || 'unknown',
        league_tier: 3,
        home_team: data.home_team,
        away_team: data.away_team,
        status: data.status,
        home_probability: homeProb,
        away_probability: awayProb,
        is_close_game: homeProb !== null && awayProb !== null && Math.abs(homeProb - awayProb) < 0.1,
        is_live: isLive,
        source_section: 'featured' as const,
        position_index: 0,
        minutes_to_start: Math.round((new Date(data.commence_time).getTime() - Date.now()) / 60000),
      });
    }}>
      <div className={`
        rounded-card border border-surface-border bg-surface-card
        p-3 hover:bg-surface-elevated transition-all cursor-pointer
        ${isLive ? "ring-1 ring-accent-live/20" : ""}
      `}>
        {/* Top row: league + badges + game time/score */}
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-1.5 min-w-0">
            {isLive && (
              <span className="flex items-center gap-1 bg-accent-live/15 text-accent-live px-1.5 py-0.5 rounded text-[11px] font-semibold flex-shrink-0">
                <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
                {/* Show period/clock if available */}
                {data.espn?.period || data.espn?.game_clock
                  ? `${data.espn.period || ""}${data.espn.period && data.espn.game_clock ? " " : ""}${data.espn.game_clock || ""}`
                  : "LIVE"}
              </span>
            )}
            {isFinished && (
              <span className="bg-surface-elevated text-text-muted px-1.5 py-0.5 rounded text-[11px] font-semibold flex-shrink-0">
                FINAL
              </span>
            )}
            {data.highlight?.label && (
              <span className={`px-2 py-0.5 rounded text-[11px] font-semibold flex-shrink-0 ${
                isFinished
                  ? "bg-accent-brand/15 text-accent-brand"
                  : "bg-accent-warning/15 text-accent-warning"
              }`}>
                {data.highlight.label}
              </span>
            )}
            {item.headline && !isLive && !data.highlight?.label && (
              <span className="bg-accent-warning/15 text-accent-warning px-2 py-0.5 rounded text-[11px] font-semibold flex-shrink-0">
                {item.headline}
              </span>
            )}
            {(data.ei || data.pulse) && (
              <span className="bg-accent-brand/10 text-accent-brand px-1.5 py-0.5 rounded text-[11px] font-medium flex-shrink-0">
                EI {(data.ei || data.pulse)!.score}
              </span>
            )}
            <PersonalizedBadge
              personalized={item.personalized}
              multiplier={item.multiplier}
              personalizationReasons={item.personalization_reasons}
            />
            {leagueName && (
              <span className="text-[11px] text-text-muted tracking-wide truncate">
                {sportEmoji && <span className="mr-0.5">{sportEmoji}</span>}
                {leagueName}
              </span>
            )}
          </div>

          {/* Right side: game time for scheduled, score for live/finished */}
          {hasScore && !isFinished ? (
            <span className="text-base font-mono font-bold flex-shrink-0 text-accent-live">
              {data.home_score} - {data.away_score}
            </span>
          ) : gameTime ? (
            <span className="text-[11px] text-text-secondary font-medium flex-shrink-0">
              {gameTime}
            </span>
          ) : finishedTime ? (
            <span className="text-[11px] text-text-muted font-medium flex-shrink-0">
              {finishedTime}
            </span>
          ) : null}
        </div>

        {/* Main row: teams with logos + probability */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            {/* Away team */}
            <div className="flex items-center gap-1.5 mb-0.5">
              <TeamLogo url={awayFlagImgUrl || data.away_team_data?.logo_small} name={data.away_team} color={data.away_team_data?.primary_color} isFlag={!!awayFlagImgUrl} sport={data.sport} />
              <span className={`text-sm truncate ${
                isFinished
                  ? (awayWon ? "font-semibold text-text-primary" : "text-text-muted")
                  : `font-medium ${displayAwayProb !== null && displayAwayProb >= 0.5 ? "text-text-primary" : "text-text-secondary"}`
              }`}>
                {data.away_team}
              </span>
              {isFinished && data.away_score != null && (
                <span className={`ml-auto font-mono text-sm ${awayWon ? "font-bold text-text-primary" : "text-text-muted"}`}>
                  {data.away_score}
                </span>
              )}
            </div>
            {/* Home team */}
            <div className="flex items-center gap-1.5">
              <TeamLogo url={homeFlagImgUrl || data.home_team_data?.logo_small} name={data.home_team} color={data.home_team_data?.primary_color} isFlag={!!homeFlagImgUrl} sport={data.sport} />
              <span className={`text-sm truncate ${
                isFinished
                  ? (homeWon ? "font-semibold text-text-primary" : "text-text-muted")
                  : `font-medium ${displayHomeProb !== null && displayHomeProb >= 0.5 ? "text-text-primary" : "text-text-secondary"}`
              }`}>
                {data.home_team}
              </span>
              {isFinished && data.home_score != null && (
                <span className={`ml-auto font-mono text-sm ${homeWon ? "font-bold text-text-primary" : "text-text-muted"}`}>
                  {data.home_score}
                </span>
              )}
            </div>
          </div>

          {displayHomeProb !== null && displayAwayProb !== null && (
            <div className="flex-shrink-0 text-right">
              {/* Away prob */}
              <div className={`font-mono text-sm font-bold mb-0.5 ${displayAwayProb >= 0.5 ? "text-text-primary" : "text-text-muted"}`}>
                {formatProbability(displayAwayProb)}
              </div>
              {/* Home prob */}
              <div className={`font-mono text-sm font-bold ${displayHomeProb >= 0.5 ? "text-text-primary" : "text-text-muted"}`}>
                {formatProbability(displayHomeProb)}
              </div>
            </div>
          )}
        </div>

        {/* Probability bar — current odds for live/scheduled, opening odds for finished */}
        {barHomeProb !== null && barAwayProb !== null && (
          <div className="w-full h-1.5 rounded-full overflow-hidden mt-2 flex">
            <div
              className="h-full transition-all rounded-l-full"
              style={{
                width: `${Math.round(barAwayProb * 100)}%`,
                backgroundColor: awayColor || "var(--color-text-muted)",
                opacity: awayColor ? 0.7 : 0.3,
              }}
            />
            <div
              className="h-full transition-all rounded-r-full"
              style={{
                width: `${Math.round(barHomeProb * 100)}%`,
                backgroundColor: homeColor || "var(--color-accent-brand)",
                opacity: homeColor ? 0.7 : 0.5,
              }}
            />
          </div>
        )}

        {/* Bottom row: reason + context + thumbs */}
        {(item.reason || openedContext) && (
          <div className="flex items-center justify-between gap-2 mt-1.5">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              {item.reason && (
                <ReasonBadge text={item.reason} truncate={!isFinished} />
              )}
              {openedContext && (
                <span className="text-[10px] text-text-muted flex-shrink-0">{openedContext}</span>
              )}
            </div>
            <ThumbButtons
              category={category}
              onThumbsUp={onThumbsUp}
              onThumbsDown={onThumbsDown}
            />
          </div>
        )}
        {/* Thumbs-only row when no reason or context */}
        {!item.reason && !openedContext && (
          <div className="flex items-center justify-end mt-1">
            <ThumbButtons
              category={category}
              onThumbsUp={onThumbsUp}
              onThumbsDown={onThumbsDown}
            />
          </div>
        )}
      </div>
    </Link>
  );
}

// ============================================================================
// Futures Feed Card
// ============================================================================

function FuturesFeedCard({
  item,
  data,
  onThumbsUp,
  onThumbsDown,
  category,
}: {
  item: FeedItem;
  data: FeedFuturesData;
  onThumbsUp?: (category: string) => void;
  onThumbsDown?: (category: string) => void;
  category?: string;
}) {
  const leader = data.top_outcomes?.[0];
  const leaderProb = leader?.probability;

  // Category emoji
  const catKey = data.llm_sport_category ?? "";
  const catEmoji = catKey ? getEmojiForCategory(catKey) : "📊";
  const catName = catKey ? getNameForCategory(catKey) : "Futures";

  // Entity image detection
  const isNonSports = isNonSportsCategory(catKey || null);

  // Resolution date
  const resolvesText = formatResolutionDate(data.resolution_date);

  return (
    <Link href={`/futures/${data.id}`}>
      <div className="rounded-card border border-surface-border bg-surface-card p-3 hover:bg-surface-elevated transition-all cursor-pointer">
        {/* Top row */}
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-1.5 min-w-0">
            {data.resolved && (
              <span className="bg-surface-elevated text-text-muted px-1.5 py-0.5 rounded text-[11px] font-semibold flex-shrink-0">
                RESOLVED
              </span>
            )}
            {item.headline && (
              <span className="bg-accent-futures/15 text-accent-futures px-2 py-0.5 rounded text-[11px] font-semibold flex-shrink-0">
                {item.headline}
              </span>
            )}
            <PersonalizedBadge
              personalized={item.personalized}
              multiplier={item.multiplier}
              personalizationReasons={item.personalization_reasons}
            />
            <span className="text-[11px] text-text-muted tracking-wide truncate">
              <span className="mr-0.5">{catEmoji}</span>
              {catName}
            </span>
          </div>

          <div className="flex items-center gap-1.5 flex-shrink-0">
            {resolvesText && (
              <span className="text-[10px] text-text-muted">
                {resolvesText}
              </span>
            )}
            {data.source_count > 1 && (
              <span className="text-[10px] bg-accent-futures/10 text-accent-futures px-1.5 py-0.5 rounded font-medium">
                {data.source_count} sources
              </span>
            )}
          </div>
        </div>

        {/* Main row */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-text-primary truncate">
              {data.name}
            </div>
            <p className="text-xs text-text-secondary mt-0.5 truncate">{item.reason}</p>
            {data.resolved && data.winner && data.winner_opening_probability != null && (
              <p className="text-[11px] text-accent-live font-medium mt-0.5">
                {data.winner}: {Math.round(data.winner_opening_probability * 100)}% → Won
              </p>
            )}
            {data.matched_outcomes && data.matched_outcomes.length > 0 && (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5">
                {data.matched_outcomes.slice(0, 3).map((mo, i) => (
                  <span key={i} className="text-xs text-text-secondary">
                    <span className="font-medium text-text-primary">{mo.name}</span>
                    {mo.probability !== null && (
                      <span className="ml-1 font-mono text-text-muted">
                        {mo.rank != null && `#${mo.rank} \u00B7 `}
                        {Math.round(mo.probability * 100)}%
                      </span>
                    )}
                  </span>
                ))}
              </div>
            )}
          </div>

          {leader && leaderProb !== null && (
            <div className="flex-shrink-0 text-right">
              <div className="font-mono text-sm font-bold text-text-primary">
                {formatProbability(leaderProb)}
              </div>
              <div className="flex items-center justify-end gap-1 text-[11px] text-text-muted truncate max-w-[100px]">
                {isNonSports && leader && (
                  <EntityImage type="wikipedia" name={leader.name} size={14} />
                )}
                {leader.name}
              </div>
              {leader.movement !== null && leader.movement !== undefined && leader.movement !== 0 && (
                <div className={`text-[10px] font-medium ${
                  leader.movement > 0 ? "text-accent-live" : "text-accent-danger"
                }`}>
                  {leader.movement > 0 ? "+" : ""}{(leader.movement * 100).toFixed(1)}%
                </div>
              )}
            </div>
          )}
        </div>

        {/* Top outcomes mini-list */}
        {data.top_outcomes.length > 1 && (
          <div className="flex gap-3 mt-2 pt-2 border-t border-surface-border/50">
            {data.top_outcomes.slice(0, 3).map((outcome, i) => (
              <div key={outcome.id} className="text-[11px] text-text-muted">
                <span className="text-text-muted/50 mr-1">#{i + 1}</span>
                <span className="font-medium text-text-secondary">{outcome.name.split(" ").pop()}</span>
                {outcome.probability !== null && (
                  <span className="ml-1 font-mono font-bold text-text-primary">
                    {Math.round(outcome.probability * 100)}%
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Bottom row: thumbs */}
        <div className="flex items-center justify-end mt-1">
          <ThumbButtons
            category={category}
            onThumbsUp={onThumbsUp}
            onThumbsDown={onThumbsDown}
          />
        </div>
      </div>
    </Link>
  );
}
