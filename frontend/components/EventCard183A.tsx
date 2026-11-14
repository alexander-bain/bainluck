"use client";

import React from "react";
import Link from "next/link";
import type { Event, FeedEventData, FeedItem } from "@/lib/types";
import { getSportLabel } from "@/lib/sportCategories";
import { shouldWithholdProbability } from "@/lib/probabilityEvidence";
import { awayIsTheComplement } from "@/lib/drawPricedWinner";
import { renderedDuelPercents } from "@/lib/renderedPercent";
import { servedDuelPercents } from "@/lib/servedDuelPercents";
import { probabilityBarPair } from "@/lib/probabilityBarPair";
import { prematchReading } from "@/lib/prematchReading";
import {
  cardProjectedFinal,
  liveCardProjectedFinal,
  type SportsbookProjectionFields,
} from "@/lib/projectedFinalPair";
import {
  formatFinishedGameLabel,
  formatLiveClockLabel,
  formatTbdStartLabel,
} from "@/lib/gameTimeLabel";
import { isFinishedStatus, isSuspendedStatus, SUSPENDED_LABEL } from "@/lib/eventState";
import { teamCrestInitials, teamShortNames } from "@/lib/teamShortName";
import { cleanDiscoverGameReason } from "@/lib/gameCard183AFlag";

export interface ChartPoint183A {
  /** Normalized horizontal position in [0, 1] from pregame (0) to current/final (1). */
  t: number;
  /** Home win probability in [0, 1]. */
  p: number;
}

export interface UnifiedGameCardData {
  id: number;
  sport: string | null;
  sport_name?: string | null;
  home_team: string;
  away_team: string;
  commence_time: string;
  start_is_tbd?: boolean | null;
  completed_at?: string | null;
  status: string;
  home_score: number | null;
  away_score: number | null;
  home_color: string;
  away_color: string;
  home_logo?: string | null;
  away_logo?: string | null;
  home_prob: number | null;
  away_prob: number | null;
  draw_prob?: number | null;
  served_home_pct?: number | null;
  served_away_pct?: number | null;
  pregame_home_pct: number | null;
  pregame_away_pct: number | null;
  projected_home: number | null;
  projected_away: number | null;
  live_clock_label: string | null;
  reason_line?: string | null;
  chart_points?: ChartPoint183A[];
}

export interface EventCard183AProps {
  card: UnifiedGameCardData;
  surface: "standard" | "discover";
  isPinned?: boolean;
  pinDisabled?: boolean;
  onPinToggle?: () => void;
  onCardClick?: () => void;
}

function BookmarkPinIcon({ filled }: { filled: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      data-testid="bookmark-pin-icon"
    >
      <path d="M6 3.75h12A1.25 1.25 0 0 1 19.25 5v15.25l-7.25-4.2-7.25 4.2V5A1.25 1.25 0 0 1 6 3.75Z" />
    </svg>
  );
}

function FeedPulseIcon({ active }: { active: boolean }) {
  return (
    <svg
      viewBox="0 0 22 12"
      className={active ? "h-3 w-5 text-accent-red" : "h-3 w-5 text-text-muted"}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      data-testid="ekg-feed-pulse"
    >
      <path d="M1 6h4.2l2.1-4 3.1 8 2.4-5.5 1.7 1.5H21" />
    </svg>
  );
}

function formatPregameKickoff(commenceTime: string, startIsTbd?: boolean | null): string {
  if (startIsTbd === true) {
    return formatTbdStartLabel(commenceTime);
  }
  const dt = new Date(commenceTime);
  if (Number.isNaN(dt.getTime())) return "";
  return dt.toLocaleString("en-US", {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

function CrestBadge({
  teamName,
  logoUrl,
  color,
}: {
  teamName: string;
  logoUrl?: string | null;
  color: string;
}) {
  if (logoUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={logoUrl}
        alt=""
        className="h-6 w-6 shrink-0 rounded-full object-contain bg-surface-elevated p-0.5"
      />
    );
  }
  const initials = teamCrestInitials(teamName);
  return (
    <span
      className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
      style={{ backgroundColor: color }}
      aria-hidden="true"
    >
      {initials}
    </span>
  );
}

/**
 * 191-A Discover chart panel: unsmoothed connected win-chance path from Pregame
 * to Now (live) or Final (settled), bold 50% dashed reference line, y-axis ticks,
 * and end labels.
 */
function DiscoverWinChancePanel({
  points,
  strokeColor,
  teamLabel,
  pregamePct,
  endPct,
  endHeader,
}: {
  points: ChartPoint183A[];
  strokeColor: string;
  teamLabel: string;
  pregamePct: number;
  endPct: number;
  endHeader: "Now" | "Final";
}) {
  const width = 326;
  const height = 112;
  const padLeft = 32;
  const padRight = 10;
  const padTop = 10;
  const padBottom = 14;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const clamped = points.map((pt) => ({
    x: padLeft + Math.min(1, Math.max(0, pt.t)) * plotW,
    y: padTop + (1 - Math.min(1, Math.max(0, pt.p))) * plotH,
  }));
  const polyD = clamped
    .map((pt, idx) => `${idx === 0 ? "M" : "L"}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`)
    .join(" ");
  const midY = padTop + 0.5 * plotH;
  const lastPt = clamped[clamped.length - 1];

  return (
    <div
      className="mt-3 rounded-lg border border-surface-border bg-surface-elevated px-3 py-2.5"
      data-testid="discover-191a-chart-panel"
    >
      <div className="mb-1.5 flex items-center justify-between text-[11px] text-text-secondary">
        <span className="font-medium text-text-primary">{teamLabel} win chance</span>
        <span className="tabular-nums text-text-muted">
          Pregame {pregamePct}% → {endHeader} {endPct}%
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-[118px] w-full overflow-visible"
        role="img"
        aria-label={`${teamLabel} win probability from pregame ${pregamePct}% to ${endHeader.toLowerCase()} ${endPct}%`}
      >
        {/* Y-axis labels & grid */}
        {[
          { label: "100%", frac: 0 },
          { label: "50%", frac: 0.5 },
          { label: "0%", frac: 1 },
        ].map((tick) => {
          const y = padTop + tick.frac * plotH;
          const isMid = tick.frac === 0.5;
          return (
            <g key={tick.label}>
              <text
                x={0}
                y={y + 3}
                className="fill-current text-[9px] text-text-muted tabular-nums"
              >
                {tick.label}
              </text>
              <line
                x1={padLeft}
                y1={y}
                x2={width - padRight}
                y2={y}
                stroke="currentColor"
                className={isMid ? "text-text-muted" : "text-surface-border"}
                strokeWidth={isMid ? 1.25 : 0.75}
                strokeDasharray={isMid ? "4 3" : undefined}
              />
            </g>
          );
        })}
        {/* Connected unsmoothed trajectory */}
        <path
          d={polyD}
          fill="none"
          stroke={strokeColor}
          strokeWidth={2.25}
          strokeLinejoin="miter"
          strokeLinecap="round"
        />
        {lastPt && (
          <circle
            cx={lastPt.x}
            cy={lastPt.y}
            r={3.5}
            fill={strokeColor}
          />
        )}
        <text
          x={padLeft}
          y={height - 1}
          className="fill-current text-[9px] text-text-muted"
        >
          Pregame
        </text>
        <text
          x={width - padRight}
          y={height - 1}
          textAnchor="end"
          className="fill-current text-[9px] font-medium text-text-secondary"
        >
          {endHeader}
        </text>
      </svg>
      <div hidden aria-hidden="true">{midY}</div>
    </div>
  );
}

export function buildUnifiedCardFromEvent(event: Event): UnifiedGameCardData {
  const isLive = event.status === "live";
  const isDone = isFinishedStatus(event.status);
  const probWithheld = shouldWithholdProbability(event);

  const rawHome = probWithheld
    ? null
    : (event.hero_probability ?? event.current_odds?.home_probability ?? null);
  const rawAway = probWithheld
    ? null
    : (event.hero_probability_away ?? event.current_odds?.away_probability ?? null);

  const pre = prematchReading(event);
  const [openAway, openHome] = pre
    ? [pre.awayPercent, pre.homePercent]
    : event.opening_odds
      ? renderedDuelPercents(
          event.opening_odds.away_probability ?? 1 - event.opening_odds.home_probability,
          event.opening_odds.home_probability,
        )
      : [null, null];

  const proj = isLive
    ? liveCardProjectedFinal(
        event.current_odds as SportsbookProjectionFields | undefined,
        event.sport,
        event.commence_time,
        { home: event.home_score, away: event.away_score },
      )
    : !isDone
      ? cardProjectedFinal(
          event.current_odds as SportsbookProjectionFields | undefined,
          event.sport,
        )
      : null;

  const clockLabel = isLive
    ? formatLiveClockLabel(event.espn?.period, event.espn?.game_clock, " · ", event.sport)
    : null;

  return {
    id: event.id,
    sport: event.sport,
    sport_name: event.sport_name,
    home_team: event.home_team,
    away_team: event.away_team,
    commence_time: event.commence_time,
    start_is_tbd: event.start_is_tbd,
    completed_at: event.completed_at,
    status: event.status,
    home_score: event.home_score,
    away_score: event.away_score,
    home_color: event.home_team_data?.primary_color || "#1d4ed8",
    away_color: event.away_team_data?.primary_color || "#475569",
    home_logo:
      event.home_team_data?.logo_small ??
      event.home_team_data?.logo_large ??
      event.home_image_url ??
      null,
    away_logo:
      event.away_team_data?.logo_small ??
      event.away_team_data?.logo_large ??
      event.away_image_url ??
      null,
    home_prob: rawHome,
    away_prob: rawAway,
    pregame_home_pct: openHome,
    pregame_away_pct: openAway,
    projected_home: proj?.home ?? null,
    projected_away: proj?.away ?? null,
    live_clock_label: clockLabel,
    reason_line: event.highlight?.label ?? null,
  };
}

export function buildUnifiedCardFromFeed(
  item: FeedItem,
  data: FeedEventData,
): UnifiedGameCardData {
  const isLive = data.status === "live";
  const isDone = isFinishedStatus(data.status);
  const probWithheld = shouldWithholdProbability(data);

  const rawHome = probWithheld ? null : (data.current_odds?.home_probability ?? null);
  const rawAway = probWithheld ? null : (data.current_odds?.away_probability ?? null);

  const pre = prematchReading(data);
  const proj = isLive
    ? liveCardProjectedFinal(
        data.current_odds as SportsbookProjectionFields | undefined,
        data.sport,
        data.commence_time,
        { home: data.home_score, away: data.away_score },
      )
    : !isDone
      ? cardProjectedFinal(
          data.current_odds as SportsbookProjectionFields | undefined,
          data.sport,
        )
      : null;

  const clockLabel = isLive
    ? formatLiveClockLabel(data.espn?.period, data.espn?.game_clock, " · ", data.sport)
    : null;

  return {
    id: data.id,
    sport: data.sport,
    sport_name: data.sport_name,
    home_team: data.home_team,
    away_team: data.away_team,
    commence_time: data.commence_time,
    start_is_tbd: data.start_is_tbd,
    completed_at: data.ended_at ?? null,
    status: data.status,
    home_score: data.home_score,
    away_score: data.away_score,
    home_color: data.home_team_data?.primary_color || "#1d4ed8",
    away_color: data.away_team_data?.primary_color || "#475569",
    home_logo:
      data.home_team_data?.logo_small ??
      data.home_team_data?.logo_large ??
      data.home_image_url ??
      null,
    away_logo:
      data.away_team_data?.logo_small ??
      data.away_team_data?.logo_large ??
      data.away_image_url ??
      null,
    home_prob: rawHome,
    away_prob: rawAway,
    served_home_pct: probWithheld ? null : data.current_odds?.home_rendered_percent,
    served_away_pct: probWithheld ? null : data.current_odds?.away_rendered_percent,
    pregame_home_pct: pre?.homePercent ?? null,
    pregame_away_pct: pre?.awayPercent ?? null,
    projected_home: proj?.home ?? null,
    projected_away: proj?.away ?? null,
    live_clock_label: clockLabel,
    reason_line: item.reason ?? data.highlight?.label ?? null,
  };
}

export default function EventCard183A({
  card,
  surface,
  isPinned = false,
  pinDisabled = false,
  onPinToggle,
  onCardClick,
}: EventCard183AProps) {
  const isLive = card.status === "live";
  const isDone = isFinishedStatus(card.status);
  const isSuspended = isSuspendedStatus(card.status);

  const { home: homeShort, away: awayShort } = teamShortNames(
    { name: card.home_team },
    { name: card.away_team },
    card.sport,
  );
  const sportLabel = getSportLabel(card.sport ?? "", card.sport_name);
  const { away: awayInk, home: homeInk } = probabilityBarPair(
    card.away_color,
    card.home_color,
    1,
  );

  const awayWithheld = awayIsTheComplement(card.away_prob, card.home_prob, card.sport);
  const [awayPct, homePct] = servedDuelPercents(
    card.away_prob,
    card.home_prob,
    card.served_away_pct,
    card.served_home_pct,
  );

  // 187-A centered Draw when explicit 3-way odds exist (`draw_prob` or non-complement 3-way sum < 0.98)
  const inferredDraw =
    card.draw_prob != null
      ? card.draw_prob
      : card.home_prob != null &&
          card.away_prob != null &&
          !awayWithheld &&
          1 - card.home_prob - card.away_prob >= 0.02
        ? 1 - card.home_prob - card.away_prob
        : null;
  const drawPct = inferredDraw != null ? Math.round(inferredDraw * 100) : null;

  const hasScore =
    (isLive || isDone) && card.home_score != null && card.away_score != null;
  const awayWon =
    isDone && hasScore && (card.away_score as number) > (card.home_score as number);
  const homeWon =
    isDone && hasScore && (card.home_score as number) > (card.away_score as number);

  const showPregameCol =
    (isLive || isDone) && (card.pregame_away_pct != null || card.pregame_home_pct != null);
  const showProjColBefore =
    !isLive && !isDone && card.projected_away != null && card.projected_home != null;

  const discoverReason =
    surface === "discover"
      ? cleanDiscoverGameReason(card.reason_line, card.home_team, card.away_team)
      : null;

  // Synthesize or pass-through 191-A connected chart trajectory for Discover live/after cards
  const canRenderChartPanel =
    surface === "discover" &&
    (isLive || isDone) &&
    card.pregame_home_pct != null &&
    (isDone ? homeWon || awayWon : homePct != null);

  const finalHomePct = isDone ? (homeWon ? 100 : 0) : (homePct ?? 50);
  const chartPoints: ChartPoint183A[] =
    card.chart_points && card.chart_points.length >= 2
      ? card.chart_points
      : [
          { t: 0, p: (card.pregame_home_pct ?? 50) / 100 },
          { t: 1, p: finalHomePct / 100 },
        ];

  const handlePin = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!pinDisabled && onPinToggle) {
      onPinToggle();
    }
  };

  return (
    <Link
      href={`/events/${card.id}`}
      onClick={onCardClick}
      data-testid={`event-card-183a-${surface}`}
      className="block rounded-xl border border-surface-border bg-surface-card p-4 transition-shadow hover:shadow-sm"
    >
      {/* Top header: League · State / Clock · EKG feed pulse · Bookmark pin */}
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2 text-xs">
          <span className="font-semibold uppercase tracking-wide text-text-secondary">
            {sportLabel}
          </span>
          {isLive ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-red/10 px-2 py-0.5 font-semibold text-accent-red">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-red" />
              {card.live_clock_label ? `LIVE · ${card.live_clock_label}` : "LIVE"}
            </span>
          ) : isSuspended ? (
            <span className="font-medium text-text-muted">{SUSPENDED_LABEL}</span>
          ) : isDone ? (
            <span className="font-medium text-text-muted">
              {formatFinishedGameLabel(card.completed_at ?? card.commence_time)}
            </span>
          ) : (
            <span className="text-text-muted">
              {formatPregameKickoff(card.commence_time, card.start_is_tbd)}
            </span>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <FeedPulseIcon active={isLive} />
          {onPinToggle && (
            <button
              type="button"
              onClick={handlePin}
              disabled={pinDisabled && !isPinned}
              aria-label={isPinned ? "Remove from saved" : "Save game"}
              className="rounded-md p-1 text-text-secondary transition-colors hover:bg-surface-elevated hover:text-text-primary disabled:opacity-40"
            >
              <BookmarkPinIcon filled={isPinned} />
            </button>
          )}
        </div>
      </div>

      {/* Column headers: aligned over tabular digits with breathing room between Score and Pregame */}
      <div className="mb-1 flex items-end justify-between text-[11px] font-medium text-text-muted">
        <span className="sr-only">Teams</span>
        <span aria-hidden="true" />
        <div className="flex items-center tabular-nums">
          {hasScore && (
            <span className="w-10 text-right" data-testid="col-header-score">
              Score
            </span>
          )}
          {showProjColBefore && (
            <span className="w-12 text-right" data-testid="col-header-proj">
              Proj.
            </span>
          )}
          {showPregameCol && (
            <span
              className={`w-16 text-right ${hasScore ? "ml-4" : ""}`}
              data-testid="col-header-pregame"
            >
              Pregame
            </span>
          )}
          <span className="ml-3 w-14 text-right text-text-secondary" data-testid="col-header-now">
            {isLive ? "Now" : isDone ? "Final" : "Chance"}
          </span>
        </div>
      </div>

      {/* Two aligned participant rows */}
      <div className="space-y-2">
        {/* Away row */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <CrestBadge
              teamName={card.away_team}
              logoUrl={card.away_logo}
              color={card.away_color}
            />
            <span
              className={`truncate text-sm ${
                isDone && !awayWon && homeWon
                  ? "font-medium text-text-secondary"
                  : "font-semibold text-text-primary"
              }`}
            >
              {awayShort}
            </span>
            {awayWon && (
              <span className="text-xs font-bold text-accent-green" aria-label="Winner">
                ✓
              </span>
            )}
          </div>

          <div className="flex shrink-0 items-baseline tabular-nums">
            {hasScore && (
              <span className="w-10 text-right text-base font-semibold text-text-primary">
                {card.away_score}
              </span>
            )}
            {showProjColBefore && (
              <span className="w-12 text-right text-sm font-semibold text-text-secondary">
                {card.projected_away}
              </span>
            )}
            {showPregameCol && (
              <span
                className={`w-16 text-right text-xs font-normal text-text-muted ${
                  hasScore ? "ml-4" : ""
                }`}
              >
                {card.pregame_away_pct != null ? `${card.pregame_away_pct}%` : "—"}
              </span>
            )}
            <span
              className="ml-3 w-14 text-right text-base font-bold"
              style={{
                color: isDone
                  ? awayWon
                    ? awayInk
                    : undefined
                  : awayPct != null && !awayWithheld
                    ? awayInk
                    : undefined,
              }}
            >
              {isDone
                ? awayWon
                  ? "Won"
                  : "—"
                : awayWithheld || awayPct == null
                  ? "—"
                  : `${awayPct}%`}
            </span>
          </div>
        </div>

        {/* 187-A centered Draw strip when 3-way draw probability is known */}
        {drawPct != null && !isDone && (
          <div
            className="flex items-center justify-center rounded-md bg-surface-elevated py-0.5 text-xs text-text-secondary tabular-nums"
            data-testid="soccer-187a-centered-draw"
          >
            Draw <span className="ml-1 font-semibold text-text-primary">{drawPct}%</span>
          </div>
        )}

        {/* Home row */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <CrestBadge
              teamName={card.home_team}
              logoUrl={card.home_logo}
              color={card.home_color}
            />
            <span
              className={`truncate text-sm ${
                isDone && !homeWon && awayWon
                  ? "font-medium text-text-secondary"
                  : "font-semibold text-text-primary"
              }`}
            >
              {homeShort}
            </span>
            {homeWon && (
              <span className="text-xs font-bold text-accent-green" aria-label="Winner">
                ✓
              </span>
            )}
          </div>

          <div className="flex shrink-0 items-baseline tabular-nums">
            {hasScore && (
              <span className="w-10 text-right text-base font-semibold text-text-primary">
                {card.home_score}
              </span>
            )}
            {showProjColBefore && (
              <span className="w-12 text-right text-sm font-semibold text-text-secondary">
                {card.projected_home}
              </span>
            )}
            {showPregameCol && (
              <span
                className={`w-16 text-right text-xs font-normal text-text-muted ${
                  hasScore ? "ml-4" : ""
                }`}
              >
                {card.pregame_home_pct != null ? `${card.pregame_home_pct}%` : "—"}
              </span>
            )}
            <span
              className="ml-3 w-14 text-right text-base font-bold"
              style={{
                color: isDone
                  ? homeWon
                    ? homeInk
                    : undefined
                  : homePct != null
                    ? homeInk
                    : undefined,
              }}
            >
              {isDone ? (homeWon ? "Won" : "—") : homePct == null ? "—" : `${homePct}%`}
            </span>
          </div>
        </div>
      </div>

      {/* Live projected final shown once (Alex plane-pack rule) */}
      {isLive && card.projected_away != null && card.projected_home != null && (
        <div
          className="mt-2 text-xs text-text-secondary tabular-nums"
          data-testid="live-projected-once"
        >
          Proj. final: {awayShort} {card.projected_away} – {homeShort} {card.projected_home}
        </div>
      )}

      {/* 191-A Discover chart panel during & after a game */}
      {canRenderChartPanel && (
        <DiscoverWinChancePanel
          points={chartPoints}
          strokeColor={homeInk}
          teamLabel={homeShort}
          pregamePct={card.pregame_home_pct as number}
          endPct={finalHomePct}
          endHeader={isDone ? "Final" : "Now"}
        />
      )}

      {/* 190-C Discover single-game reason line (omitted completely if filler) */}
      {discoverReason && (
        <p
          className="mt-2.5 border-t border-surface-border pt-2 text-xs leading-relaxed text-text-secondary"
          data-testid="discover-game-reason-line"
        >
          {discoverReason}
        </p>
      )}
    </Link>
  );
}
