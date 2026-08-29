"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import type { FeedItem, FeedEventData, FeedFuturesData, FeedTournamentData, FeedConceptData, GolfTournament } from "@/lib/types";
import { formatProbability } from "@/lib/api";
import { servedDuelPercents } from "@/lib/servedDuelPercents";
import { renderedCardPercents, cardSumReason, renderedLeaderPercent } from "@/lib/renderedPercent";
import { cardSumExplanation } from "@/lib/cardSum";
import { eventPath } from "@/lib/eventKey";
import { leaderFirstSlice } from "@/lib/discover/leaderOrder";
import { getLeagueDisplay, getEmojiForLeague, getEmojiForCategory, getNameForCategory } from "@/lib/sportCategories";
import PersonalizedBadge from "./PersonalizedBadge";
import EntityImage from "./EntityImage";
import TournamentCard from "./TournamentCard";
import { isNonSportsCategory, isInternationalSport, flagUrl, espnTeamLogoByName } from "@/lib/images";
import { useAnalyticsContext } from "@/components/Analytics";
import { feedItemHasRenderableContent, resolvesLabel, formatConceptMovement } from "@/components/discover/utils";
import { formatFinishedGameLabel, formatLiveClockLabel } from "@/lib/gameTimeLabel";
import TeamNameLink from "./TeamNameLink";

interface FeedCardProps {
  item: FeedItem;
  onThumbsUp?: (category: string) => void;
  onThumbsDown?: (category: string) => void;
  category?: string;
}

export default function FeedCard({ item, onThumbsUp, onThumbsDown, category }: FeedCardProps) {
  // L2-215 Item 1: fail-closed defense-in-depth (#1486). The Sports page filters
  // empty predictive envelopes at its section boundary; guard the leaf too so an
  // empty concept/futures/tournament can never render as a bare tile.
  if (!feedItemHasRenderableContent(item)) return null;

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

  if (item.type === "tournament") {
    const td = item.data as FeedTournamentData;
    // Adapt FeedTournamentData → GolfTournament shape for TournamentCard
    const tournament: GolfTournament = {
      key: td.key,
      name: td.name,
      slug: td.slug,
      is_major: td.is_major,
      tour: td.tour,
      tour_label: td.tour_label,
      commence_time: td.commence_time ?? null,
      resolution_date: td.resolution_date ?? null,
      start_date: td.start_date,
      end_date: td.end_date,
      venue: td.venue,
      location: td.location,
      schedule_status: td.schedule_status,
      market_ids: td.market_ids,
      golfers: td.golfers.map((g) => ({
        name: g.name,
        probability: g.probability,
        rank: g.rank,
        movement_24h: g.movement_24h,
        american_odds: null,
        opening_probability: null,
        sources: {},
      })),
    };
    return <TournamentCard tournament={tournament} whatHit={td.marquee_whathit === true} />;
  }

  if (item.type === "concept") {
    return <ConceptFeedCard item={item} data={item.data as FeedConceptData} />;
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

/**
 * Format a finished game's date for staleness context.
 *
 * UX-P045: the body moved to `@/lib/gameTimeLabel` unchanged. It used to live
 * here as a module-private function, which is precisely why the Discover card —
 * the default landing page, and the surface that needed it most — never got it.
 */
function formatFinishedDate(commenceTime: string): string {
  return formatFinishedGameLabel(commenceTime, Date.now(), "relative");
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
  const [imgError, setImgError] = useState(false);
  const resolvedUrl = url || (!isFlag ? espnTeamLogoByName(name, sport) : null);

  if (resolvedUrl && !imgError) {
    return (
      <Image
        src={resolvedUrl}
        alt={name}
        width={20}
        height={isFlag ? 15 : 20}
        className={`flex-shrink-0 ${isFlag ? "rounded-sm" : "rounded-sm"}`}
        unoptimized
        onError={() => setImgError(true)}
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

  // For finished events, show opening odds (pre-game prediction context).
  // Fall back to current aggregate if opening odds aren't available.
  const openingHome = data.opening_odds?.home_probability ?? null;
  const openingAway = data.opening_odds?.away_probability ?? null;
  const displayHomeProb = isFinished ? (openingHome ?? homeProb) : homeProb;
  const displayAwayProb = isFinished ? (openingAway ?? awayProb) : awayProb;
  // UX-P114 — the chips below print BOTH sides of one question, and the feed
  // derives away as `1 - home`, so rounding them independently printed 101
  // whenever the blend landed on a half-percent (34 of 414 live/upcoming events,
  // 2026-08-21). Same decision as the Discover card's strip.
  //
  // The served percents describe `current_odds`, and the chips only render when
  // `!isFinished` — i.e. exactly when `displayProb` IS `current_odds`. The
  // `opening_odds` branch above therefore never reaches them, which is why the
  // served values can be used directly rather than being matched to their source.
  //
  // #2279 — BOTH SERVED OR NEITHER. This site coalesced per side, so a payload
  // carrying one field and not the other printed a served value beside a derived
  // one — the same 101 from the other direction, on a cached response or a
  // partial rollout.
  const [awayPct, homePct] = servedDuelPercents(
    displayAwayProb,
    displayHomeProb,
    data.current_odds?.away_rendered_percent,
    data.current_odds?.home_rendered_percent,
  );

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

  // Opening odds context for live games.
  //
  // UX-P166 — this prints BOTH sides of one question in fixed positions, so it is
  // a duel and not two numbers that happen to sit together. Rounding them
  // independently printed 101 whenever the opening line landed on a half-percent,
  // and the opening line lands there constantly: measured on production
  // 2026-08-29 over every event carrying one, ALL 24,117 are complement pairs and
  // 207 print 101 (115 completed, 91 closed, 1 live at the time of measurement).
  // Zero print 99 — the one-directional skew of the half-cent grid, same
  // signature as the `current_odds` strip UX-P114 fixed above.
  //
  // Not a served value: the three `opening_odds` serializers publish the two
  // floats and no rendered percent, so the local contract fallback IS the
  // decision here rather than a stand-in for one.
  const [openedAwayPct, openedHomePct] = renderedDuelPercents(
    data.opening_odds?.away_probability,
    data.opening_odds?.home_probability,
  );
  const openedContext =
    (isLive || isFinished) && openedHomePct !== null && openedAwayPct !== null
      ? `Opened ${openedHomePct}/${openedAwayPct}`
      : null;

  // For the probability bar: finished events show opening odds, others show current
  const barHomeProb = isFinished
    ? (data.opening_odds?.home_probability ?? null)
    : displayHomeProb;
  const barAwayProb = isFinished
    ? (data.opening_odds?.away_probability ?? null)
    : displayAwayProb;

  return (
    <Link href={`/events/${data.id}`} aria-label={`${data.away_team} at ${data.home_team}${isLive ? " - Live" : isFinished ? "- Final" : ""}`} onClick={() => {
      track('event_card_click', {
        event_id: data.id,
        sport: data.sport || 'unknown',
        league: data.sport || 'unknown',
        league_tier: 1 as 1 | 2 | 3,
        home_team: data.home_team,
        away_team: data.away_team,
        status: data.status,
        home_probability: homeProb,
        away_probability: awayProb,
        is_close_game: homeProb !== null && awayProb !== null && Math.abs(homeProb - awayProb) < 0.1,
        is_live: isLive,
        source_section: 'feed' as const,
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
          <div className="flex items-center flex-wrap gap-1.5 min-w-0">
            {isLive && (
              <span className="flex items-center gap-1 bg-accent-live/15 text-accent-live px-1.5 py-0.5 rounded text-[11px] font-semibold flex-shrink-0 max-w-[140px]">
                <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse flex-shrink-0" />
                <span className="truncate">
                {/* UX-P051 (#1710): this site's character-count heuristic was the
                    only guard anywhere, and it was wrong in both directions — it
                    let the clock through alone ("0.0") when it rejected ESPN's
                    pre-game sentence, and it silently dropped real long labels
                    ("1st Quarter", "End of 1st Half", "End of Regulation"). The
                    shared rule reads the reported state, not the length. */}
                {formatLiveClockLabel(data.espn?.period, data.espn?.game_clock) || "LIVE"}
                </span>
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
              <TeamNameLink
                name={data.away_team}
                sportKey={data.sport}
                className={`text-sm truncate hover:underline ${
                  isFinished
                    ? (awayWon ? "font-semibold text-text-primary" : "text-text-muted")
                    : `font-medium ${displayAwayProb !== null && displayAwayProb >= 0.5 ? "text-text-primary" : "text-text-secondary"}`
                }`}
              />
              {isFinished && data.away_score != null && (
                <span className={`ml-auto font-mono text-sm ${awayWon ? "font-bold text-text-primary" : "text-text-muted"}`}>
                  {data.away_score}
                </span>
              )}
            </div>
            {/* Home team */}
            <div className="flex items-center gap-1.5">
              <TeamLogo url={homeFlagImgUrl || data.home_team_data?.logo_small} name={data.home_team} color={data.home_team_data?.primary_color} isFlag={!!homeFlagImgUrl} sport={data.sport} />
              <TeamNameLink
                name={data.home_team}
                sportKey={data.sport}
                className={`text-sm truncate hover:underline ${
                  isFinished
                    ? (homeWon ? "font-semibold text-text-primary" : "text-text-muted")
                    : `font-medium ${displayHomeProb !== null && displayHomeProb >= 0.5 ? "text-text-primary" : "text-text-secondary"}`
                }`}
              />
              {isFinished && data.home_score != null && (
                <span className={`ml-auto font-mono text-sm ${homeWon ? "font-bold text-text-primary" : "text-text-muted"}`}>
                  {data.home_score}
                </span>
              )}
            </div>
          </div>

          {/* Live/pregame probability chips — dropped on FINAL for the settled
              treatment (L2-112 Item 2: the score + bold winner tell the story). */}
          {!isFinished && displayHomeProb !== null && displayAwayProb !== null && (
            <div className="flex-shrink-0 text-right">
              {/* Away prob */}
              <div className={`font-mono text-sm font-bold mb-0.5 ${displayAwayProb >= 0.5 ? "text-text-primary" : "text-text-muted"}`}>
                {formatProbability(displayAwayProb, { rendered: awayPct })}
              </div>
              {/* Home prob */}
              <div className={`font-mono text-sm font-bold ${displayHomeProb >= 0.5 ? "text-text-primary" : "text-text-muted"}`}>
                {formatProbability(displayHomeProb, { rendered: homePct })}
              </div>
            </div>
          )}
        </div>

        {/* Probability bar — current odds for live/scheduled; dropped on FINAL
            (the settled card shows score + winner, not a live-style split). The
            pre-game context survives as the muted "Opened X/Y" text below. */}
        {!isFinished && barHomeProb !== null && barAwayProb !== null && (
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
                <span className="text-[11px] text-text-muted flex-shrink-0">{openedContext}</span>
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

  // ── #2088 criterion 3: the card rule, on the surface a reader actually reads ──
  //
  // This list is where a two-outcome market prints BOTH of its numbers — the
  // Discover futures card shows only the hero leader, so the pair, and therefore
  // the sum, is visible here (`/categories/*`, `/sports`, `/my-stuff`) and not
  // there. Until now every row rounded independently: `Math.round(p * 100)`,
  // inline, which is the fourth copy of the rule #2060 exists to replace and the
  // one place it had never reached.
  //
  // MEASURED ON THE DEPLOYED FEED 2026-08-29 across every pair-printing surface:
  // 7 distinct two-outcome cards, of which SIX are wrong today — `Which party will
  // win the U.S. House?` (85 + 16) and `Will Neuralink's valuation hit (HIGH)
  // $47.5B` (73 + 28) print 101, and four more print an unexplained non-100
  // (83, 51, 41, 22). Only `Will Netanyahu visit New York City by...?` (52 + 48)
  // is already right, and it correctly gains nothing.
  //
  // The served reason WINS, including when it is null ("checked, and they do total
  // 100"). The fallback keys on the KEY BEING ABSENT rather than on the value being
  // falsy — `?? derive()` would re-derive on every correct card and make the
  // server's answer decorative. Same discipline as `LabelingCard`.
  const printedOutcomes = leaderFirstSlice(data.top_outcomes ?? [], 3);
  const fallbackPercents = renderedCardPercents(
    printedOutcomes.map((o) => o.probability)
  );
  const sumExplanation = cardSumExplanation(
    "card_sum_reason" in data
      ? data.card_sum_reason
      : cardSumReason(printedOutcomes.map((o) => o.probability))
  );
  // The headline's own percent, looked up BY IDENTITY rather than by position:
  // `leader` is `top_outcomes[0]` (unsorted) while `printedOutcomes` is
  // leader-first, so the two indices are not the same list. `leaderFirst` returns
  // the original row objects, so `indexOf` is exact. Null when the headline is not
  // among the printed rows at all, which leaves `formatProbability` on its
  // pre-existing behaviour rather than inventing a number.
  //
  // UX-P162 lifted that dance into `renderedLeaderPercent` unchanged, because the
  // Discover hero needed the identical three decisions and a second hand-copy is
  // how the two surfaces would have drifted back apart. Same slice (leader-first,
  // 3) and therefore the same answer as the inline form it replaces.
  const heroPercent = renderedLeaderPercent(data.top_outcomes, leader);

  // Category emoji
  const catKey = data.llm_sport_category ?? "";
  const catEmoji = catKey ? getEmojiForCategory(catKey) : "📊";
  const catName = catKey ? getNameForCategory(catKey) : "Futures";

  // Entity image detection
  const isNonSports = isNonSportsCategory(catKey || null);

  // UX-P054 (#1719) — the SAME timing line the Discover futures card prints.
  //
  // This card ran its own ladder until now, and its last branch printed a
  // month-day with NO YEAR. On the live Sports tab that was 29 of the 41 dated
  // futures cards stating the wrong year by omission: "2030 FIFA World Cup
  // Champion" rendered "Resolves Jan 14" about January 2031. The authority's own
  // docstring names that exact string as the misreading it exists to prevent.
  //
  // Ninth instance of the #1620 shape on this lane, and the ninth time the answer
  // already lived in a sibling module. `resolvesLabel` is the futures/comparison
  // card's line, so the Sports tab and Discover now print the identical string
  // from the identical field rather than disagreeing by tab.
  const resolvesText = resolvesLabel(data.resolution_date);

  const { track } = useAnalyticsContext();

  return (
    <Link href={`/futures/${data.id}`} aria-label={`${data.name}`} onClick={() => {
      track('futures_card_click', {
        market_id: data.id,
        category: data.llm_sport_category || 'unknown',
        position_index: 0,
        source_section: 'feed',
      });
    }}>
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
              <span className="text-[11px] text-text-muted">
                {resolvesText}
              </span>
            )}
            {data.source_count > 1 && (
              <span className="text-[11px] bg-accent-futures/10 text-accent-futures px-1.5 py-0.5 rounded font-medium">
                {data.source_count} sources
              </span>
            )}
          </div>
        </div>

        {/* Main row */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-text-primary line-clamp-2">
              {data.name}
            </div>
            <p className="text-xs text-text-secondary mt-0.5 line-clamp-2">{item.reason}</p>
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
              {/* Queue 283's invariant, kept: ONE outcome never renders two
                  different numbers on one card. The row below now prints the
                  card-rule percent, so the headline must take the SAME integer
                  rather than rounding the probability again — otherwise a pair
                  summing to 0.99 shows 57% here and 58% one line down. Same
                  `{ rendered }` channel the event card already uses. */}
              <div className="font-mono text-sm font-bold text-text-primary">
                {formatProbability(leaderProb, { rendered: heroPercent })}
              </div>
              <div className="flex items-center justify-end gap-1 text-[11px] text-text-muted truncate max-w-[100px]">
                {isNonSports && leader && (
                  <EntityImage type="wikipedia" name={leader.name} size={14} />
                )}
                {leader.name}
              </div>
              {leader.movement !== null && leader.movement !== undefined && leader.movement !== 0 && (
                <div className={`text-[11px] font-medium ${
                  leader.movement > 0 ? "text-accent-live" : "text-accent-danger"
                }`}>
                  {leader.movement > 0 ? "+" : ""}{(leader.movement * 100).toFixed(1)}%
                </div>
              )}
            </div>
          )}
        </div>

        {/* Top outcomes with probability bars */}
        {data.top_outcomes.length > 1 && (
          <div className="mt-2 pt-2 border-t border-surface-border/50 space-y-1.5">
            {/* #1526: leader-first before truncating — i === 0 is styled as
                THE favorite below, so an unsorted slice bolds an also-ran. */}
            {printedOutcomes.map((outcome, i) => {
              // #2060/#2088: the served percent wins; `fallbackPercents` is the
              // pre-#2088 payload's answer and is computed over the SAME
              // leader-first slice, so index i lines up either way.
              const pct =
                "rendered_percent" in outcome
                  ? outcome.rendered_percent
                  : fallbackPercents[i];
              return (
              <div key={outcome.id} className="flex items-center gap-2">
                <span
                  title={outcome.name}
                  className={`text-[11px] w-20 truncate shrink-0 ${i === 0 ? "font-semibold text-text-primary" : "text-text-secondary"}`}
                >
                  {/* L2-243 Item 1 — show the real outcome name (CSS-truncated),
                      not the trailing word only, which turned "Costa Rica" into
                      "Rica" and "…World Cup?" into "Cup?". */}
                  {outcome.name}
                </span>
                {/* The bar WIDTH stays on the raw probability — it is a length,
                    not a printed number — but `aria-valuenow` is the number that
                    is printed, so a screen reader hears the card, not a second
                    rounding of it. */}
                <div className="flex-1 h-1.5 rounded-full bg-surface-border overflow-hidden" role="progressbar" aria-valuenow={pct ?? undefined} aria-valuemin={0} aria-valuemax={100} aria-label={`${outcome.name} probability`}>
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${i === 0 ? "bg-accent-brand" : "bg-text-muted/30"}`}
                    style={{ width: `${(outcome.probability ?? 0) * 100}%` }}
                  />
                </div>
                {pct !== null && pct !== undefined && (
                  <span className="font-mono tabular-nums text-[11px] font-bold text-text-primary w-8 text-right">
                    {pct}%
                  </span>
                )}
              </div>
              );
            })}
            {sumExplanation && (
              <p
                className="text-[10px] text-text-muted leading-relaxed pt-0.5"
                data-testid="card-sum-explanation"
              >
                {sumExplanation}
              </p>
            )}
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

// ============================================================================
// Event Concept Feed Card (#999 B3 / L2-84) — a card/tournament teaser that
// links to /event/{key}. Marquee-badged for numbered cards; probability-free
// (the card is a hub, not a single market).
// ============================================================================

function ConceptFeedCard({ item, data }: { item: FeedItem; data: FeedConceptData }) {
  const { track } = useAnalyticsContext();
  // L2-159: a just-settled marquee concept (T+36h WHAT-HIT window, #235 flag)
  // leads with THE RESULT — settled-means-settled grammar ("cards show results").
  // The flag can only be true post-settlement, so it wins over any live framing.
  const whatHit = data.marquee_whathit === true;
  const isLive = !whatHit && data.status === "live";
  const winner = data.winner?.trim() || null;
  const resultSummary = data.result_summary?.trim() || null;
  // #1939 — guarded exactly as the admitting classifier guards it, never laxer.
  const leader =
    !whatHit && data.leader && (data.leader.name ?? "").trim() &&
    typeof data.leader.probability === "number"
      ? data.leader
      : null;
  const movementLabel = formatConceptMovement(leader?.movement_24h);
  return (
    <Link
      href={eventPath(data.key)}
      aria-label={whatHit ? `${data.name} — final result` : data.name}
      onClick={() =>
        track("concept_card_click", {
          market_id: 0,
          category: data.domain || "unknown",
          position_index: 0,
          source_section: "feed",
        })
      }
    >
      <div
        className={`rounded-card border border-surface-border bg-surface-card p-3 hover:bg-surface-elevated transition-all cursor-pointer ${
          isLive ? "ring-1 ring-accent-live/20" : ""
        }`}
      >
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-1.5 min-w-0">
            {whatHit && (
              <span className="flex items-center gap-1 bg-accent-brand/15 text-accent-brand px-2 py-0.5 rounded text-[11px] font-semibold flex-shrink-0">
                <span aria-hidden>🏁</span>
                FINAL
              </span>
            )}
            {isLive && (
              <span className="flex items-center gap-1 bg-accent-live/15 text-accent-live px-1.5 py-0.5 rounded text-[11px] font-semibold flex-shrink-0">
                <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
                LIVE
              </span>
            )}
            {data.is_major && (
              <span className="bg-accent-futures/15 text-accent-futures px-2 py-0.5 rounded text-[11px] font-semibold flex-shrink-0">
                Marquee
              </span>
            )}
            {/* WHAT-HIT suppresses the live/countdown headline — the result is the story. */}
            {item.headline && !isLive && !whatHit && (
              <span className="bg-accent-warning/15 text-accent-warning px-2 py-0.5 rounded text-[11px] font-semibold flex-shrink-0">
                {item.headline}
              </span>
            )}
            <span className="text-[11px] text-text-muted tracking-wide truncate">
              <span className="mr-0.5">🥊</span>
              {data.domain?.toUpperCase() || "EVENT"}
            </span>
          </div>
        </div>

        <div className="text-sm font-semibold text-text-primary line-clamp-2">
          {data.name}
        </div>
        {whatHit ? (
          // Result-first: champion name + "won" chip where the payload provides it;
          // otherwise an honest settled line inviting the recap. Never fabricated.
          winner ? (
            <div className="flex items-center flex-wrap gap-1.5 mt-1">
              <span className="text-sm font-bold text-text-primary truncate">{winner}</span>
              <span className="bg-accent-brand/15 text-accent-brand px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide flex-shrink-0">
                Won
              </span>
              {resultSummary && (
                <span className="text-xs text-text-secondary truncate">{resultSummary}</span>
              )}
            </div>
          ) : (
            <p className="text-xs text-text-secondary mt-0.5">
              {resultSummary || "Final result — see the recap"}
            </p>
          )
        ) : leader ? (
          // #1939: the favourite. The Discover concept card gained this in the
          // same commit — this surface is admitted by the SAME predicate
          // (`feedItemSuppressionReason`), so if only one of the two renderers
          // learned to print a leader, the other would start showing the bare
          // tile that #1935 just removed. Two renderers, one gate: they change
          // together or the gate is wrong for one of them.
          <div className="flex items-center flex-wrap gap-1.5 mt-1">
            <span className="text-sm font-bold text-text-primary truncate">
              {leader.name}
            </span>
            <span className="bg-accent-brand/15 text-accent-brand px-1.5 py-0.5 rounded text-[10px] font-bold flex-shrink-0">
              {Math.round(leader.probability * 100)}%
            </span>
            {movementLabel && (
              <span className="text-[11px] font-bold text-text-secondary flex-shrink-0">
                {movementLabel}
              </span>
            )}
            {typeof leader.field_size === "number" && leader.field_size > 2 && (
              <span className="text-[11px] text-text-muted flex-shrink-0">
                of {leader.field_size}
              </span>
            )}
          </div>
        ) : (
          item.reason && (
            <p className="text-xs text-text-secondary mt-0.5">{item.reason}</p>
          )
        )}
      </div>
    </Link>
  );
}
