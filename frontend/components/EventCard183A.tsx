"use client";

import React from "react";
import Link from "next/link";
import type { Event, FeedEventData, FeedItem } from "@/lib/types";
import { getSportLabel } from "@/lib/sportCategories";
import { shouldWithholdProbability } from "@/lib/probabilityEvidence";
import { awayIsTheComplement, sportPricesADraw } from "@/lib/drawPricedWinner";
import { renderedDuelPercents } from "@/lib/renderedPercent";
import { servedDuelPercents } from "@/lib/servedDuelPercents";
import { ABOVE_NINETY_NINE_PERCENT, BELOW_ONE_PERCENT } from "@/lib/probabilityDisplay";
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
import { PinIcon } from "@/components/PinButton";

export interface ChartPoint183A {
  /** Normalized horizontal position in [0, 1] from pregame (0) to current/final (1). */
  t: number;
  /** Home win probability in [0, 1]. */
  p: number;
}

export interface TennisSetScore183A {
  away: number;
  home: number;
  tiebreak_away?: number | null;
  tiebreak_home?: number | null;
  current?: boolean;
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
  home_abbrev?: string | null;
  away_abbrev?: string | null;
  home_prob: number | null;
  away_prob: number | null;
  draw_prob?: number | null;
  served_home_pct?: number | null;
  served_away_pct?: number | null;
  pregame_home_pct: number | null;
  pregame_away_pct: number | null;
  pregame_draw_pct?: number | null;
  projected_home: number | null;
  projected_away: number | null;
  live_clock_label: string | null;
  reason_line?: string | null;
  chart_points?: ChartPoint183A[];
  tennis_sets?: TennisSetScore183A[];
  tennis_game_points?: { away: string; home: string } | null;
  serving?: "away" | "home" | null;
}

export interface EventCard183AProps {
  card: UnifiedGameCardData;
  surface: "standard" | "discover";
  isPinned?: boolean;
  pinDisabled?: boolean;
  onPinToggle?: () => void;
  onCardClick?: () => void;
}

function isTennisSport(sport: string | null | undefined): boolean {
  return typeof sport === "string" && sport.toLowerCase().startsWith("tennis_");
}

/**
 * Formats a single live probability to tenths (`"64.2%"`), matching iOS
 * `CompactGameCard12616.formatSingleLiveTenths`: never prints `0%`/`0.0%` or
 * `100%`/`100.0%` while live (delegates boundary clamps to `probabilityDisplay`).
 */
export function formatSingleLiveTenths(value: number | null | undefined): string | null {
  if (value == null || !Number.isFinite(value)) return null;
  const pct = value * 100;
  if (pct < 1) return BELOW_ONE_PERCENT;
  if (pct > 99) return ABOVE_NINETY_NINE_PERCENT;
  const tenths = Math.min(990, Math.max(10, Math.round((value * 10000) / 10)));
  return `${(tenths / 10).toFixed(1)}%`;
}

/**
 * Shared fitting font size for both competitor rows on a game card so longer
 * college school names ("Michigan State", "Mississippi State") shrink together
 * to fit at 390 px before ever hitting truncation.
 */
export function sharedGameCardTeamFontClass(
  awayLabel: string,
  homeLabel: string,
  hasThreeColumns: boolean,
): string {
  const maxLen = Math.max(awayLabel.length, homeLabel.length);
  if (hasThreeColumns) {
    if (maxLen <= 11) return "text-[15px]";
    if (maxLen <= 14) return "text-[13.5px]";
    if (maxLen <= 18) return "text-[12.5px]";
    return "text-[11.5px]";
  }
  if (maxLen <= 14) return "text-[15px]";
  if (maxLen <= 18) return "text-[13.5px]";
  return "text-[12.5px]";
}

/**
 * Formats a two-sided live duel to tenths (`[away, home]`), matching iOS
 * `CompactGameCard12616.liveTenthsStrings` so complement pairs in `[1%, 99%]`
 * sum to `100.0%` (`1000` tenths).
 */
export function formatLiveTenthsPair(
  away: number | null | undefined,
  home: number | null | undefined,
  awayWithheld: boolean,
): { away: string | null; home: string | null } {
  if (awayWithheld) {
    return { away: null, home: formatSingleLiveTenths(home) };
  }
  if (away == null || home == null || !Number.isFinite(away) || !Number.isFinite(home)) {
    return {
      away: formatSingleLiveTenths(away),
      home: formatSingleLiveTenths(home),
    };
  }
  const awayPct = away * 100;
  const homePct = home * 100;
  if (awayPct < 1 || awayPct > 99 || homePct < 1 || homePct > 99) {
    return {
      away: formatSingleLiveTenths(away),
      home: formatSingleLiveTenths(home),
    };
  }
  const total = away + home;
  if (Math.abs(total - 1) > 0.03) {
    return {
      away: formatSingleLiveTenths(away),
      home: formatSingleLiveTenths(home),
    };
  }
  if (away >= home) {
    const favTenths = Math.min(990, Math.max(10, Math.round(((away / total) * 10000) / 10)));
    const dogTenths = 1000 - favTenths;
    return {
      away: `${(favTenths / 10).toFixed(1)}%`,
      home: `${(dogTenths / 10).toFixed(1)}%`,
    };
  }
  const favTenths = Math.min(990, Math.max(10, Math.round(((home / total) * 10000) / 10)));
  const dogTenths = 1000 - favTenths;
  return {
    away: `${(dogTenths / 10).toFixed(1)}%`,
    home: `${(favTenths / 10).toFixed(1)}%`,
  };
}

function FeedPulseIcon({ active }: { active: boolean }) {
  return (
    <svg
      viewBox="0 0 22 12"
      className={active ? "h-3 w-5 text-accent-danger" : "h-3 w-5 text-text-muted"}
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
  sport,
  abbreviation,
  logoUrl,
  color,
}: {
  teamName: string;
  sport?: string | null;
  abbreviation?: string | null;
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
  const initials = teamCrestInitials(teamName, sport, abbreviation);
  return (
    <span
      className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-bold leading-none text-white ${
        initials.length >= 4
          ? "text-[7px] tracking-tighter"
          : initials.length === 3
            ? "text-[9px] tracking-tight"
            : "text-[10px]"
      }`}
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
  endPctLabel,
  endHeader,
  cardId,
}: {
  points: ChartPoint183A[];
  strokeColor: string;
  teamLabel: string;
  pregamePct: number;
  endPctLabel: string;
  endHeader: "Now" | "Final";
  cardId: number;
}) {
  const width = 326;
  const height = 122;
  const padLeft = 32;
  const padRight = 10;
  const padTop = 8;
  const padBottom = 8;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const clamped = points.map((pt) => ({
    x: padLeft + Math.min(1, Math.max(0, pt.t)) * plotW,
    y: padTop + (1 - Math.min(1, Math.max(0, pt.p))) * plotH,
  }));
  const polyD = clamped
    .map((pt, idx) => `${idx === 0 ? "M" : "L"}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`)
    .join(" ");
  const firstPt = clamped[0];
  const lastPt = clamped[clamped.length - 1];
  const areaD =
    firstPt && lastPt
      ? `${polyD} L${lastPt.x.toFixed(1)},${(padTop + plotH).toFixed(1)} L${firstPt.x.toFixed(1)},${(padTop + plotH).toFixed(1)} Z`
      : "";
  const gradId = `chart191a-grad-${cardId}`;

  return (
    <div
      className="mt-3 rounded-lg border border-surface-border bg-surface-elevated px-3 py-2.5"
      data-testid="discover-191a-chart-panel"
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-[124px] w-full overflow-visible"
        role="img"
        aria-label={`${teamLabel} win probability from pregame ${pregamePct}% to ${endHeader.toLowerCase()} ${endPctLabel}`}
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={strokeColor} stopOpacity={0.16} />
            <stop offset="100%" stopColor={strokeColor} stopOpacity={0.01} />
          </linearGradient>
        </defs>
        {[
          { label: "100%", frac: 0 },
          { label: "75%", frac: 0.25 },
          { label: "50%", frac: 0.5 },
          { label: "25%", frac: 0.75 },
          { label: "0%", frac: 1 },
        ].map((tick) => {
          const y = padTop + tick.frac * plotH;
          const isMid = tick.frac === 0.5;
          return (
            <g key={tick.label}>
              <text
                x={0}
                y={y + 3}
                className={`fill-current text-[9px] tabular-nums ${
                  isMid ? "font-semibold text-text-secondary" : "text-text-muted"
                }`}
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
        {areaD && <path d={areaD} fill={`url(#${gradId})`} />}
        <path
          d={polyD}
          fill="none"
          stroke={strokeColor}
          strokeWidth={2.25}
          strokeLinejoin="miter"
          strokeLinecap="round"
        />
        {firstPt && (
          <circle
            cx={firstPt.x}
            cy={firstPt.y}
            r={2.75}
            className="fill-surface-card"
            stroke={strokeColor}
            strokeWidth={1.75}
          />
        )}
        {lastPt && <circle cx={lastPt.x} cy={lastPt.y} r={3.5} fill={strokeColor} />}
      </svg>
      <div className="mt-1.5 flex items-center justify-between text-[11.5px] tabular-nums">
        <span className="text-text-muted">
          Pregame {pregamePct}% {teamLabel}
        </span>
        <span className="font-semibold" style={{ color: strokeColor }}>
          {endHeader} · {endPctLabel}
        </span>
      </div>
    </div>
  );
}

function extractTennisSets(espn: unknown): {
  sets?: TennisSetScore183A[];
  gamePoints?: { away: string; home: string } | null;
  serving?: "away" | "home" | null;
} {
  if (!espn || typeof espn !== "object") return {};
  const rec = espn as Record<string, unknown>;
  const rawSets = rec.tennis_sets ?? rec.set_scores;
  let sets: TennisSetScore183A[] | undefined;
  if (Array.isArray(rawSets) && rawSets.length > 0) {
    const parsed = rawSets
      .map((s) => {
        if (!s || typeof s !== "object") return null;
        const sr = s as Record<string, unknown>;
        if (typeof sr.away === "number" && typeof sr.home === "number") {
          return {
            away: sr.away,
            home: sr.home,
            tiebreak_away: typeof sr.tiebreak_away === "number" ? sr.tiebreak_away : null,
            tiebreak_home: typeof sr.tiebreak_home === "number" ? sr.tiebreak_home : null,
            current: sr.current === true,
          } as TennisSetScore183A;
        }
        return null;
      })
      .filter((x): x is TennisSetScore183A => x !== null);
    if (parsed.length > 0) sets = parsed;
  }
  const gp = rec.game_points as Record<string, unknown> | undefined;
  const gamePoints =
    gp && typeof gp.away === "string" && typeof gp.home === "string"
      ? { away: gp.away, home: gp.home }
      : null;
  const serving =
    rec.serving === "away" || rec.serving === "home" ? (rec.serving as "away" | "home") : null;
  return { sets, gamePoints, serving };
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
  const rawDraw = probWithheld
    ? null
    : ((event.current_odds as { draw_probability?: number | null } | undefined)?.draw_probability ??
        null);

  const pre = prematchReading(event);
  const [openAway, openHome] = pre
    ? [pre.awayPercent, pre.homePercent]
    : event.opening_odds
      ? renderedDuelPercents(
          event.opening_odds.away_probability ?? 1 - event.opening_odds.home_probability,
          event.opening_odds.home_probability,
        )
      : [null, null];

  const rawOpenDraw = (
    event.opening_odds as { draw_probability?: number | null } | null | undefined
  )?.draw_probability;
  const openDrawPct =
    rawOpenDraw != null && Number.isFinite(rawOpenDraw) && rawOpenDraw > 0 && rawOpenDraw < 1
      ? Math.round(rawOpenDraw * 100)
      : null;

  const tennis = isTennisSport(event.sport);
  const proj = tennis
    ? null
    : isLive
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

  const tennisExtra = tennis ? extractTennisSets(event.espn) : {};

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
    home_abbrev: event.home_team_data?.abbreviation ?? null,
    away_abbrev: event.away_team_data?.abbreviation ?? null,
    home_prob: rawHome,
    away_prob: rawAway,
    draw_prob: rawDraw,
    pregame_home_pct: openHome,
    pregame_away_pct: openAway,
    pregame_draw_pct: openDrawPct,
    projected_home: proj?.home ?? null,
    projected_away: proj?.away ?? null,
    live_clock_label: clockLabel,
    reason_line: event.highlight?.label ?? null,
    tennis_sets: tennisExtra.sets,
    tennis_game_points: tennisExtra.gamePoints ?? null,
    serving: tennisExtra.serving ?? null,
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
  const rawDraw = probWithheld
    ? null
    : ((data.current_odds as { draw_probability?: number | null } | undefined)?.draw_probability ??
        null);

  const pre = prematchReading(data);
  const rawOpenDraw = (
    data.opening_odds as { draw_probability?: number | null } | null | undefined
  )?.draw_probability;
  const openDrawPct =
    rawOpenDraw != null && Number.isFinite(rawOpenDraw) && rawOpenDraw > 0 && rawOpenDraw < 1
      ? Math.round(rawOpenDraw * 100)
      : null;

  const tennis = isTennisSport(data.sport);
  const proj = tennis
    ? null
    : isLive
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

  const tennisExtra = tennis ? extractTennisSets(data.espn) : {};

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
    home_abbrev: data.home_team_data?.abbreviation ?? null,
    away_abbrev: data.away_team_data?.abbreviation ?? null,
    home_prob: rawHome,
    away_prob: rawAway,
    draw_prob: rawDraw,
    served_home_pct: probWithheld ? null : data.current_odds?.home_rendered_percent,
    served_away_pct: probWithheld ? null : data.current_odds?.away_rendered_percent,
    pregame_home_pct: pre?.homePercent ?? null,
    pregame_away_pct: pre?.awayPercent ?? null,
    pregame_draw_pct: openDrawPct,
    projected_home: proj?.home ?? null,
    projected_away: proj?.away ?? null,
    live_clock_label: clockLabel,
    reason_line: item.reason ?? data.highlight?.label ?? null,
    tennis_sets: tennisExtra.sets,
    tennis_game_points: tennisExtra.gamePoints ?? null,
    serving: tennisExtra.serving ?? null,
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
  const tennis = isTennisSport(card.sport);
  const drawSport = sportPricesADraw(card.sport);

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

  // Explicit 3-way reading when `draw_prob` is provided or `away + home` leaves >= 2% draw share
  const inferredDraw =
    card.draw_prob != null && Number.isFinite(card.draw_prob) && card.draw_prob > 0
      ? card.draw_prob
      : card.home_prob != null &&
          card.away_prob != null &&
          1 - card.home_prob - card.away_prob >= 0.02
        ? 1 - card.home_prob - card.away_prob
        : null;
  const hasExplicitThreeWayCurrent = inferredDraw != null;

  const awayWithheld =
    !hasExplicitThreeWayCurrent && awayIsTheComplement(card.away_prob, card.home_prob, card.sport);
  const [awayWholePct, homeWholePct] = servedDuelPercents(
    card.away_prob,
    card.home_prob,
    card.served_away_pct,
    card.served_home_pct,
  );

  const liveTenths = isLive
    ? formatLiveTenthsPair(card.away_prob, card.home_prob, awayWithheld)
    : { away: null, home: null };
  const liveDrawTenths =
    isLive && inferredDraw != null ? formatSingleLiveTenths(inferredDraw) : null;
  const drawWholePct = inferredDraw != null ? Math.round(inferredDraw * 100) : null;

  const hasTennisSetBoxes =
    tennis &&
    (isLive || isDone) &&
    Array.isArray(card.tennis_sets) &&
    card.tennis_sets.length > 0;
  const showTennisPointsBox =
    hasTennisSetBoxes && isLive && card.tennis_game_points != null;

  const hasScore =
    !hasTennisSetBoxes &&
    isLive &&
    card.home_score != null &&
    card.away_score != null;

  const awayScoreCompare = hasTennisSetBoxes
    ? card.tennis_sets!.filter((s) => !s.current && s.away > s.home).length
    : card.away_score;
  const homeScoreCompare = hasTennisSetBoxes
    ? card.tennis_sets!.filter((s) => !s.current && s.home > s.away).length
    : card.home_score;

  const hasDecisiveComparison =
    awayScoreCompare != null && homeScoreCompare != null;
  const awayWon =
    isDone && hasDecisiveComparison && (awayScoreCompare as number) > (homeScoreCompare as number);
  const homeWon =
    isDone && hasDecisiveComparison && (homeScoreCompare as number) > (awayScoreCompare as number);
  const finishedLevelDraw =
    isDone &&
    drawSport &&
    hasDecisiveComparison &&
    awayScoreCompare === homeScoreCompare;

  // 187-A middle Draw row on soccer/draw-priced sports when explicit 3-way odds exist or match finished level
  const showsMiddleDrawRow =
    !isSuspended &&
    (hasExplicitThreeWayCurrent ||
      (isDone && (card.pregame_draw_pct != null || finishedLevelDraw)));

  const showPregameCol =
    (isLive || isDone) &&
    (card.pregame_away_pct != null ||
      card.pregame_home_pct != null ||
      card.pregame_draw_pct != null);
  const showProjColBefore =
    !tennis &&
    !isLive &&
    !isDone &&
    !isSuspended &&
    card.projected_away != null &&
    card.projected_home != null;

  const discoverReason =
    surface === "discover"
      ? cleanDiscoverGameReason(card.reason_line, card.home_team, card.away_team)
      : null;

  const canRenderChartPanel =
    surface === "discover" &&
    !isSuspended &&
    (isLive || isDone) &&
    card.pregame_home_pct != null &&
    (isDone ? homeWon || awayWon || finishedLevelDraw : homeWholePct != null);

  const finalHomePct = isDone
    ? homeWon
      ? 100
      : awayWon
        ? 0
        : 50
    : (homeWholePct ?? 50);
  const chartEndLabel = isDone
    ? homeWon
      ? "Won"
      : finishedLevelDraw
        ? "Draw"
        : "0%"
    : (liveTenths.home ?? `${homeWholePct ?? 50}%`);

  const chartPoints: ChartPoint183A[] =
    card.chart_points && card.chart_points.length >= 2
      ? card.chart_points
      : [
          { t: 0, p: (card.pregame_home_pct ?? 50) / 100 },
          { t: 1, p: finalHomePct / 100 },
        ];

  // Compact pregame / non-picture segmented bar (matches iOS DiscoverCompactSingleGameCard190CView)
  const showSegmentedBar =
    !canRenderChartPanel &&
    !isDone &&
    !isSuspended &&
    card.home_prob != null &&
    Number.isFinite(card.home_prob);

  const barShares = (() => {
    if (!showSegmentedBar || card.home_prob == null) return null;
    if (hasExplicitThreeWayCurrent && card.away_prob != null && inferredDraw != null) {
      const total = card.away_prob + inferredDraw + card.home_prob;
      if (total > 0) {
        return {
          away: (card.away_prob / total) * 100,
          draw: (inferredDraw / total) * 100,
          home: (card.home_prob / total) * 100,
          awayWithheld: false,
        };
      }
    }
    const rawA = awayWithheld || card.away_prob == null ? 1 - card.home_prob : card.away_prob;
    const total = rawA + card.home_prob;
    if (total <= 0) return null;
    return {
      away: (rawA / total) * 100,
      draw: null as number | null,
      home: (card.home_prob / total) * 100,
      awayWithheld,
    };
  })();

  const handlePin = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!pinDisabled && onPinToggle) {
      onPinToggle();
    }
  };

  const awayPrimaryDisplay = isDone
    ? awayScoreCompare != null
      ? String(awayScoreCompare)
      : awayWon
        ? "Won"
        : "—"
    : isLive
      ? awayWithheld || liveTenths.away == null
        ? "—"
        : liveTenths.away
      : awayWithheld || awayWholePct == null
        ? "—"
        : `${awayWholePct}%`;

  const homePrimaryDisplay = isDone
    ? homeScoreCompare != null
      ? String(homeScoreCompare)
      : homeWon
        ? "Won"
        : "—"
    : isLive
      ? liveTenths.home ?? "—"
      : homeWholePct == null
        ? "—"
        : `${homeWholePct}%`;

  const drawPrimaryDisplay = isDone
    ? "—"
    : isLive
      ? liveDrawTenths ?? (drawWholePct != null ? `${drawWholePct}%` : "—")
      : drawWholePct != null
        ? `${drawWholePct}%`
        : "—";

  const hasScoreOrSets = hasScore || hasTennisSetBoxes;
  const teamFontClass = sharedGameCardTeamFontClass(awayShort, homeShort, hasScoreOrSets);

  return (
    <Link
      href={`/events/${card.id}`}
      onClick={onCardClick}
      data-testid={`event-card-183a-${surface}`}
      className="block rounded-xl border border-surface-border bg-surface-card p-4 transition-shadow hover:shadow-sm"
    >
      {/* Top header: League · State / Clock · EKG feed pulse · Shared Bookmark pin */}
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2 text-xs">
          <span className="font-semibold uppercase tracking-wide text-text-secondary">
            {sportLabel}
          </span>
          {isLive ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-danger/10 px-2 py-0.5 font-semibold text-accent-danger">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-danger" />
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
          {isLive && <FeedPulseIcon active />}
          {onPinToggle && (
            <button
              type="button"
              onClick={handlePin}
              disabled={pinDisabled && !isPinned}
              aria-label={isPinned ? "Remove from saved" : "Save game"}
              className="rounded-md p-1 text-text-secondary transition-colors hover:bg-surface-elevated hover:text-text-primary disabled:opacity-40"
            >
              <span data-testid="bookmark-pin-icon" className="inline-flex">
                <PinIcon filled={isPinned} className="h-4 w-4" />
              </span>
            </button>
          )}
        </div>
      </div>

      {/* Column headers: 10.5px semibold uppercase tabular, 18px gutter after Score/Sets, 10px gap before Now */}
      <div className="mb-1.5 flex items-end justify-between border-b border-surface-border/60 pb-1 text-[10.5px] font-semibold uppercase tracking-wide text-text-muted">
        <span className="sr-only">Teams</span>
        <span aria-hidden="true" />
        <div className="flex items-center tabular-nums">
          {hasTennisSetBoxes && (
            <div className="flex items-center gap-1" data-testid="tennis-score-strip">
              {card.tennis_sets!.map((_, idx) => (
                <span key={idx} className="w-5 text-center">
                  S{idx + 1}
                </span>
              ))}
              {showTennisPointsBox && <span className="ml-0.5 w-7 text-right">Pts</span>}
            </div>
          )}
          {hasScore && (
            <span className="w-9 text-right" data-testid="col-header-score">
              {tennis ? "Sets" : "Score"}
            </span>
          )}
          {showProjColBefore && (
            <span className="w-12 text-right" data-testid="col-header-proj">
              Proj.
            </span>
          )}
          {showPregameCol && (
            <span
              className={`w-12 text-right ${hasScoreOrSets ? "ml-[14px]" : ""}`}
              data-testid="col-header-pregame"
            >
              Pregame
            </span>
          )}
          <span
            className="ml-[10px] w-[58px] text-right text-text-secondary"
            data-testid="col-header-now"
          >
            {isLive ? "Now" : isDone ? "Final" : "Chance"}
          </span>
        </div>
      </div>

      {/* Competitor rows (+ 187-A middle Draw row on 3-way soccer) */}
      <div className="space-y-2">
        {/* Away row */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <CrestBadge
              teamName={card.away_team}
              sport={card.sport}
              abbreviation={card.away_abbrev}
              logoUrl={card.away_logo}
              color={card.away_color}
            />
            <span
              className={`truncate ${teamFontClass} ${
                isDone && !awayWon && !finishedLevelDraw
                  ? "font-medium text-text-secondary"
                  : isDone && awayWon
                    ? "font-bold text-text-primary"
                    : "font-semibold text-text-primary"
              }`}
            >
              {awayShort}
            </span>
            {awayWon && (
              <span
                className="shrink-0 text-[13px] font-extrabold text-accent-brand"
                aria-label="Won"
                data-testid="winner-tick-away"
              >
                ✓
              </span>
            )}
            {tennis && isLive && card.serving === "away" && (
              <span
                className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-accent-brand"
                aria-label="Serving"
                data-testid="tennis-serving-away"
              />
            )}
          </div>

          <div className="flex shrink-0 items-baseline tabular-nums">
            {hasTennisSetBoxes && (
              <div className="flex items-baseline gap-1">
                {card.tennis_sets!.map((s, idx) => {
                  const wonSet = !s.current && s.away > s.home;
                  return (
                    <span
                      key={idx}
                      className={`w-5 text-center text-[15px] ${
                        s.current
                          ? "rounded bg-surface-elevated font-bold text-text-primary"
                          : wonSet
                            ? "font-semibold text-text-primary"
                            : "font-normal text-text-muted"
                      }`}
                    >
                      {s.away}
                      {s.tiebreak_away != null && (
                        <sup className="text-[9px] text-text-muted">{s.tiebreak_away}</sup>
                      )}
                    </span>
                  );
                })}
                {showTennisPointsBox && (
                  <span className="ml-0.5 w-7 text-right text-xs font-semibold text-text-secondary">
                    {card.tennis_game_points!.away}
                  </span>
                )}
              </div>
            )}
            {hasScore && (
              <span className="w-9 text-right text-[17px] font-semibold text-text-primary">
                {card.away_score}
              </span>
            )}
            {showProjColBefore && (
              <span className="w-12 text-right text-[16px] font-semibold text-text-secondary">
                {card.projected_away}
              </span>
            )}
            {showPregameCol && (
              <span
                className={`w-12 text-right text-[14px] font-normal text-text-muted ${
                  hasScoreOrSets ? "ml-[14px]" : ""
                }`}
              >
                {card.pregame_away_pct != null ? `${card.pregame_away_pct}%` : "—"}
              </span>
            )}
            <span
              className={`ml-[10px] w-[58px] text-right ${
                isDone
                  ? awayWon
                    ? "text-[18px] font-extrabold text-text-primary"
                    : finishedLevelDraw
                      ? "text-[18px] font-bold text-text-primary"
                      : "text-[18px] font-medium text-text-muted"
                  : "text-[18px] font-bold"
              }`}
              style={{
                color:
                  !isDone &&
                  !awayWithheld &&
                  (isLive ? liveTenths.away != null : awayWholePct != null)
                    ? awayInk
                    : undefined,
              }}
            >
              {awayPrimaryDisplay}
            </span>
          </div>
        </div>

        {/* 187-A middle Draw row aligned to the exact same columns */}
        {showsMiddleDrawRow && (
          <div
            className="flex items-center justify-between gap-2 py-0.5"
            data-testid="soccer-187a-centered-draw"
          >
            <div className="flex min-w-0 items-center gap-2">
              <span
                className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-elevated text-[11px] font-bold text-text-muted"
                aria-hidden="true"
              >
                =
              </span>
              <span
                className={`truncate text-[13.5px] ${
                  finishedLevelDraw
                    ? "font-bold text-text-primary"
                    : "font-medium text-text-secondary"
                }`}
              >
                Draw
              </span>
              {finishedLevelDraw && (
                <span
                  className="shrink-0 text-[13px] font-extrabold text-accent-brand"
                  aria-label="Drawn result"
                  data-testid="winner-tick-draw"
                >
                  ✓
                </span>
              )}
            </div>
            <div className="flex shrink-0 items-baseline tabular-nums">
              {hasScore && <span className="w-9 text-right text-xs text-text-muted">—</span>}
              {showProjColBefore && (
                <span className="w-12 text-right text-xs text-text-muted">—</span>
              )}
              {showPregameCol && (
                <span
                  className={`w-12 text-right text-[14px] font-normal text-text-muted ${
                    hasScoreOrSets ? "ml-[14px]" : ""
                  }`}
                >
                  {card.pregame_draw_pct != null ? `${card.pregame_draw_pct}%` : "—"}
                </span>
              )}
              <span
                className={`ml-[10px] w-[58px] text-right ${
                  isDone
                    ? "text-[15px] font-normal text-text-muted"
                    : "text-[16px] font-bold text-text-secondary"
                }`}
              >
                {drawPrimaryDisplay}
              </span>
            </div>
          </div>
        )}

        {/* Home row */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <CrestBadge
              teamName={card.home_team}
              sport={card.sport}
              abbreviation={card.home_abbrev}
              logoUrl={card.home_logo}
              color={card.home_color}
            />
            <span
              className={`truncate ${teamFontClass} ${
                isDone && !homeWon && !finishedLevelDraw
                  ? "font-medium text-text-secondary"
                  : isDone && homeWon
                    ? "font-bold text-text-primary"
                    : "font-semibold text-text-primary"
              }`}
            >
              {homeShort}
            </span>
            {homeWon && (
              <span
                className="shrink-0 text-[13px] font-extrabold text-accent-brand"
                aria-label="Won"
                data-testid="winner-tick-home"
              >
                ✓
              </span>
            )}
            {tennis && isLive && card.serving === "home" && (
              <span
                className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-accent-brand"
                aria-label="Serving"
                data-testid="tennis-serving-home"
              />
            )}
          </div>

          <div className="flex shrink-0 items-baseline tabular-nums">
            {hasTennisSetBoxes && (
              <div className="flex items-baseline gap-1">
                {card.tennis_sets!.map((s, idx) => {
                  const wonSet = !s.current && s.home > s.away;
                  return (
                    <span
                      key={idx}
                      className={`w-5 text-center text-[15px] ${
                        s.current
                          ? "rounded bg-surface-elevated font-bold text-text-primary"
                          : wonSet
                            ? "font-semibold text-text-primary"
                            : "font-normal text-text-muted"
                      }`}
                    >
                      {s.home}
                      {s.tiebreak_home != null && (
                        <sup className="text-[9px] text-text-muted">{s.tiebreak_home}</sup>
                      )}
                    </span>
                  );
                })}
                {showTennisPointsBox && (
                  <span className="ml-0.5 w-7 text-right text-xs font-semibold text-text-secondary">
                    {card.tennis_game_points!.home}
                  </span>
                )}
              </div>
            )}
            {hasScore && (
              <span className="w-9 text-right text-[17px] font-semibold text-text-primary">
                {card.home_score}
              </span>
            )}
            {showProjColBefore && (
              <span className="w-12 text-right text-[16px] font-semibold text-text-secondary">
                {card.projected_home}
              </span>
            )}
            {showPregameCol && (
              <span
                className={`w-12 text-right text-[14px] font-normal text-text-muted ${
                  hasScoreOrSets ? "ml-[14px]" : ""
                }`}
              >
                {card.pregame_home_pct != null ? `${card.pregame_home_pct}%` : "—"}
              </span>
            )}
            <span
              className={`ml-[10px] w-[58px] text-right ${
                isDone
                  ? homeWon
                    ? "text-[18px] font-extrabold text-text-primary"
                    : finishedLevelDraw
                      ? "text-[18px] font-bold text-text-primary"
                      : "text-[18px] font-medium text-text-muted"
                  : "text-[18px] font-bold"
              }`}
              style={{
                color:
                  !isDone && (isLive ? liveTenths.home != null : homeWholePct != null)
                    ? homeInk
                    : undefined,
              }}
            >
              {homePrimaryDisplay}
            </span>
          </div>
        </div>
      </div>

      {/* Compact pregame / standard segmented probability bar (omitted on settled cards & when 191-A chart renders) */}
      {barShares && (
        <div
          className={`mt-2.5 flex h-1.5 overflow-hidden rounded-full ${
            barShares.awayWithheld ? "justify-end bg-surface-border/40" : "gap-[2px]"
          }`}
          data-testid="compact-probability-bar"
        >
          {!barShares.awayWithheld && (
            <div
              className="h-full rounded-l-full"
              style={{ width: `${barShares.away}%`, backgroundColor: awayInk }}
            />
          )}
          {barShares.draw != null && (
            <div
              className="h-full bg-text-muted/45"
              style={{ width: `${barShares.draw}%` }}
            />
          )}
          <div
            className="h-full rounded-r-full"
            style={{ width: `${barShares.home}%`, backgroundColor: homeInk }}
          />
        </div>
      )}

      {/* Live projected final shown once (Alex plane-pack rule) */}
      {isLive && !tennis && card.projected_away != null && card.projected_home != null && (
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
          cardId={card.id}
          points={chartPoints}
          strokeColor={homeInk}
          teamLabel={homeShort}
          pregamePct={card.pregame_home_pct as number}
          endPctLabel={chartEndLabel}
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
