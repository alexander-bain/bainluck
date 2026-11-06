"use client";

/**
 * #9483 — the NFL page's game-story cards on web (design freeze v328), drawn
 * compact in the deck under the chart and full size in `EventCardReader`.
 * Compact and full size read the same card value and the same selection, so
 * opening a card never changes what it says. Decisions live in
 * `lib/nflEventCardDeck.ts`; this file only draws them.
 */

import { forwardRef, useEffect, useLayoutEffect, useRef, useState, type Ref } from "react";
import { formatProbability } from "@/lib/api";
import { propVerdictLabel } from "@/lib/propGrade";
import { teamTextColor } from "@/lib/teamColors";
import AtlasDetailsSheet, { type AtlasDetailsSheetProps } from "@/components/atlas/AtlasDetailsSheet";
import { ATLAS_STATE_COPY } from "@/components/atlas/atlasStateCopy";
import {
  cardTitle,
  defaultRungIndex,
  finishHeadline,
  finishKicker,
  formatPoints,
  milestoneCaption,
  milestoneProfile,
  statDomain,
  targetLabel,
  type FinishCard,
  type MilestoneBasis,
  type MilestoneCard,
  type MilestoneRung,
  type NflEventCard,
  type NflPropRow,
} from "@/lib/nflEventCardDeck";
import {
  defaultLadderIndex,
  ladderCaption,
  ladderTitle,
  marginWords,
  type LadderCard,
  type LadderPoint,
  type OptionDetail,
} from "@/lib/nbaEventCards";
import {
  mlbHomeRunHeadline,
  mlbHomeRunReason,
  mlbVenueResultLabel,
  type MlbExtraInningsCard,
  type MlbHomeRunCard,
  type MlbSeriesCard,
} from "@/lib/mlbEventCards";
import {
  nhlScoringHeadline,
  nhlScoringReason,
  type NhlScoringCard,
} from "@/lib/nhlEventCards";
import {
  soccerThreeWayHeadline,
  soccerThreeWayReason,
  type SoccerExactScoreCard,
  type SoccerThreeWayCard,
} from "@/lib/soccerEventCards";
import {
  type TennisExactScoreCard,
  type TennisSetsCard,
} from "@/lib/tennisEventCards";

/** Selected original row per milestone card, keyed by card id. */
export type CardSelection = Record<string, string>;

export interface CardTeams {
  awayName: string;
  homeName: string;
  /** The hero's short names ("Seahawks"). Row labels beside number columns use
   *  them; at phone width the full name truncated to "Seattle Se…" (#11098). */
  awayShort?: string | null;
  homeShort?: string | null;
  /** Served primary colours; may be absent or too light for text. */
  awayColor?: string | null;
  homeColor?: string | null;
}

const NEUTRAL = "#4B5563";

/** Ink for marks: the served colour, or neutral when absent. */
function inkColor(hex: string | null | undefined): string {
  return hex || NEUTRAL;
}

/** Text colour: the served colour only where it is legible on the card. */
function textColor(hex: string | null | undefined): string {
  return teamTextColor(hex) ?? NEUTRAL;
}

/**
 * The selected rung: the stored row when it is still on the card, nothing when
 * that row left (never a neighbouring line), else the default entry point.
 */
export function selectedRungIndex(card: MilestoneCard, selection: CardSelection): number | null {
  const row = selection[card.id];
  if (row === undefined) return defaultRungIndex(card);
  const index = card.rungs.findIndex((r) => r.rowId === row);
  return index >= 0 ? index : null;
}

/** Axis labels centred on their ticks; when they would collide, whole labels drop in priority order. */
export function axisLabelPlacements(
  ticks: number[],
  widths: number[],
  plotWidth: number,
  keep: number | null,
  minGap = 4,
): { index: number; center: number }[] {
  const count = Math.min(ticks.length, widths.length);
  if (count === 0) return [];
  const centers = ticks.slice(0, count).map((x, i) => Math.min(Math.max(x, widths[i] / 2), plotWidth - widths[i] / 2));
  const order: number[] = [];
  for (const i of [keep, 0, count - 1]) if (i !== null && i >= 0 && i < count && !order.includes(i)) order.push(i);
  for (let i = 0; i < count; i++) if (!order.includes(i)) order.push(i);
  const kept: number[] = [];
  for (const i of order) {
    const clear = kept.every((k) => Math.abs(centers[i] - centers[k]) >= (widths[i] + widths[k]) / 2 + minGap);
    if (clear) kept.push(i);
  }
  return kept.sort((a, b) => a - b).map((i) => ({ index: i, center: centers[i] }));
}

const AXIS_FONT = 11;
const labelWidth = (text: string, font = AXIS_FONT) => text.length * font * 0.6;

/**
 * The plot is drawn at the width it actually has, never scaled as an image:
 * scaled, its axis labels printed at twice the card's text on a wide reader and
 * did not grow at all with enlarged text. The label size follows the root font
 * size, so a reader who enlarges text gets larger labels too. 320 × 11 until
 * the first measurement (and in server markup).
 */
export function usePlotBox(): [Ref<HTMLDivElement>, { width: number; font: number }] {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ width: 320, font: AXIS_FONT });
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const read = () => {
      const width = Math.round(Math.min(Math.max(el.clientWidth, 240), 720));
      const root = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      const font = Math.round(AXIS_FONT * (root / 16) * 10) / 10;
      setBox((prev) => (prev.width === width && prev.font === font ? prev : { width, font }));
    };
    read();
    const observer = new ResizeObserver(read);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, box];
}

// ─── Projected finish ──────────────────────────────────────────────────────

export function FinishCardView({
  card,
  teams,
  expanded = false,
  atlasMode = false,
  onDetails,
}: {
  card: FinishCard;
  teams: CardTeams;
  expanded?: boolean;
  atlasMode?: boolean;
  onDetails?: (rowId: string) => void;
}) {
  const later = card.final ?? card.projectedNow;
  const laterLabel = card.final ? "Final" : card.projectedNow ? "Projected now" : null;
  const values = [card.pregame.away, card.pregame.home, later?.away ?? 0, later?.home ?? 0];
  const domainMax = Math.max(14, Math.ceil(Math.max(...values) / 7) * 7 + 3.5);
  const [boxRef, box] = usePlotBox();
  const W = box.width;
  const font = box.font;
  const rowH = expanded ? 64 : 34;
  const left = 8;
  const right = 8;
  const top = 8;
  const plotW = W - left - right;
  const H = top + rowH * 2 + font * 2;
  const x = (v: number) => left + (v / domainMax) * plotW;
  const ticks: number[] = [];
  for (let t = 0; t <= domainMax; t += 7) ticks.push(t);
  const finalWinnerSide: "away" | "home" | null =
    card.final && card.final.away !== card.final.home
      ? card.final.away > card.final.home
        ? "away"
        : "home"
      : null;
  const rows = [
    { side: "away" as const, name: teams.awayName, label: teams.awayShort || teams.awayName, color: teams.awayColor, pregame: card.pregame.away, later: later?.away },
    { side: "home" as const, name: teams.homeName, label: teams.homeShort || teams.homeName, color: teams.homeColor, pregame: card.pregame.home, later: later?.home },
  ];
  const headline = finishHeadline(card, teams.awayName, teams.homeName);
  const placements = axisLabelPlacements(
    ticks.map((t) => x(t) - left),
    ticks.map((t) => labelWidth(String(t), font)),
    plotW,
    null,
  );
  const spoken = [
    finishKicker(card),
    headline,
    `Pregame projection ${teams.awayName} ${formatPoints(card.pregame.away)}, ${teams.homeName} ${formatPoints(card.pregame.home)}`,
    ...(later && laterLabel
      ? [`${laterLabel} ${teams.awayName} ${formatPoints(later.away)}, ${teams.homeName} ${formatPoints(later.home)}`]
      : []),
  ].join(". ");
  return (
    <div className="flex flex-col gap-2" data-card-kind="finish">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-wide" style={{ color: textColor(teams.homeColor) }}>
          {finishKicker(card)}
        </p>
        {atlasMode && onDetails && (
          <button
            type="button"
            onClick={() => onDetails("finish")}
            aria-label={`Details for ${finishKicker(card)}`}
            data-testid="atlas-story-card-details-button"
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[11px] font-semibold text-text-secondary hover:text-text-primary"
          >
            i
          </button>
        )}
      </div>
      <h3 className="text-lg font-bold text-text-primary leading-snug">{headline}</h3>
      {atlasMode && (
        <div
          data-testid="atlas-story-card-mark-key"
          className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-text-secondary"
        >
          <span className="inline-flex items-center gap-1">
            <span aria-hidden="true" className="inline-block h-2.5 w-2.5 border-2 border-text-secondary bg-surface-card" />
            <span>Pregame</span>
          </span>
          {card.projectedNow && !card.final && (
            <>
              <span className="inline-flex items-center gap-1">
                <span aria-hidden="true" className="inline-block h-2.5 w-2.5 bg-text-primary" />
                <span>Recorded</span>
              </span>
              <span className="inline-flex items-center gap-1">
                <span aria-hidden="true" className="inline-block h-0.5 w-3 bg-text-secondary" />
                <span>Change</span>
              </span>
            </>
          )}
          {card.final && (
            <>
              <span className="inline-flex items-center gap-1">
                <span aria-hidden="true" className="inline-block h-2.5 w-0.5 bg-text-primary" />
                <span>Final</span>
              </span>
              {finalWinnerSide && (
                <span className="font-semibold text-accent-live">{ATLAS_STATE_COPY.wonWithCheck}</span>
              )}
            </>
          )}
        </div>
      )}
      <div ref={boxRef} className="w-full max-w-[720px]">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width={W}
        height={H}
        role="img"
        aria-label={spoken}
        className="block max-w-full"
        data-testid="finish-card-plot"
      >
        {ticks.map((t) => (
          <line key={t} x1={x(t)} x2={x(t)} y1={top} y2={top + rowH * 2} stroke="rgba(0,0,0,0.08)" />
        ))}
        {rows.map((row, i) => {
          const cy = top + rowH * i + rowH / 2;
          const ink = inkColor(row.color);
          return (
            <g key={row.name}>
              {atlasMode && row.later !== undefined && (
                <line
                  x1={x(row.pregame)}
                  x2={x(row.later)}
                  y1={cy}
                  y2={cy}
                  stroke={ink}
                  strokeWidth={1.75}
                  strokeOpacity={0.55}
                  data-mark="finish-connector"
                />
              )}
              <rect
                x={x(row.pregame) - 5}
                y={cy - 5}
                width={10}
                height={10}
                fill="none"
                stroke={ink}
                strokeWidth={2}
                data-mark="pregame"
              />
              {row.later !== undefined && card.final && (
                <g stroke={ink} strokeWidth={2.5} data-mark="final">
                  <line x1={x(row.later) - 6} x2={x(row.later) + 6} y1={cy} y2={cy} />
                  <line x1={x(row.later)} x2={x(row.later)} y1={cy - 6} y2={cy + 6} />
                </g>
              )}
              {row.later !== undefined && !card.final && (
                <rect x={x(row.later) - 5} y={cy - 5} width={10} height={10} fill={ink} data-mark="projected-now" />
              )}
            </g>
          );
        })}
        {placements.map((p) => (
          <text
            key={ticks[p.index]}
            x={left + p.center}
            y={top + rowH * 2 + font * 1.4}
            fontSize={font}
            textAnchor="middle"
            fill="#4B5563"
          >
            {ticks[p.index]}
          </text>
        ))}
      </svg>
      </div>
      {rows.map((row) => (
        <div key={row.name} className="flex items-baseline gap-2">
          <span className="text-sm font-semibold min-w-0 flex-1 truncate" style={{ color: textColor(row.color) }}>
            {row.label}
          </span>
          {atlasMode && finalWinnerSide === row.side && (
            <span
              data-testid="finish-card-winner-badge"
              className="inline-flex items-center rounded bg-accent-live/15 px-1.5 py-0.5 text-[11px] font-semibold text-accent-live"
            >
              {ATLAS_STATE_COPY.wonWithCheck}
            </span>
          )}
          <span className="flex flex-col items-end">
            <span className="text-base font-semibold tabular-nums text-text-primary">{formatPoints(row.pregame)}</span>
            <span className="text-[11px] text-text-secondary">pregame projection</span>
          </span>
          {row.later !== undefined && laterLabel && (
            <span className="flex flex-col items-end min-w-[72px]">
              <span className="text-base font-semibold tabular-nums text-text-primary">{formatPoints(row.later)}</span>
              <span className="text-[11px] text-text-secondary">{laterLabel.toLowerCase()}</span>
            </span>
          )}
        </div>
      ))}
      <p className="text-[11px] text-text-secondary">
        {card.final
          ? "Points · outline = pregame · cross = final"
          : card.projectedNow
            ? "Points · outline = pregame · filled = projected now"
            : "Projected points"}
      </p>
    </div>
  );
}

// ─── Player milestones ─────────────────────────────────────────────────────

function readoutText(card: MilestoneCard, rung: MilestoneRung, atlasMode = false): string {
  const none =
    card.basis === "pregamePrice"
      ? atlasMode
        ? ATLAS_STATE_COPY.noRecentPrice
        : "No recent price"
      : "No pregame chance";
  return `${targetLabel(rung.threshold)} · ${rung.chance !== null ? formatProbability(rung.chance) : none}`;
}

function verdictText(card: MilestoneCard, rung: MilestoneRung, expanded: boolean, atlasMode = false, hasDetails = false): string {
  const more = expanded || (atlasMode && hasDetails) ? " · details" : "";
  // The site's one settled vocabulary (UX-P106), not the phone's wording.
  if (rung.hit !== null) {
    const prefix = atlasMode ? `${rung.hit ? "✓ " : "✗ "}` : "";
    return `${prefix}${propVerdictLabel(rung.hit)}${more}`;
  }
  if (rung.chance === null) {
    if (!expanded && !(atlasMode && hasDetails)) return "";
    return card.basis === "pregamePrice" ? "Last quote in details" : "Details";
  }
  return (card.basis === "pregamePrice" ? "Pregame chance" : "Before kickoff") + more;
}

function MilestoneProfileChart({
  card,
  selected,
  color,
  expanded,
  atlasMode = false,
}: {
  card: MilestoneCard;
  selected: number | null;
  color: string;
  expanded: boolean;
  atlasMode?: boolean;
}) {
  const [boxRef, box] = usePlotBox();
  const profile = milestoneProfile(card);
  if (!profile) {
    return (
      <p
        className={`flex items-center justify-center text-sm text-text-secondary ${expanded ? "min-h-[120px]" : "min-h-[60px]"}`}
      >
        {atlasMode ? ATLAS_STATE_COPY.noRecentPrice : "No recent prices"}
      </p>
    );
  }
  const [lo, hi] = statDomain(profile.domain, card.actual);
  const W = box.width;
  const font = box.font;
  const H = (expanded ? 220 : 140) + (font - AXIS_FONT) * 2;
  const left = Math.ceil(labelWidth("100%", font)) + 10;
  const right = 10;
  const top = 8;
  const bottom = Math.ceil(font * 2);
  const plotW = W - left - right;
  const plotH = H - top - bottom;
  const x = (v: number) => left + ((v - lo) / (hi - lo)) * plotW;
  const y = (p: number) => top + (1 - p) * plotH;
  const ticks = card.rungs.map((r) => x(r.threshold) - left);
  const placements = axisLabelPlacements(
    ticks,
    card.rungs.map((r) => labelWidth(targetLabel(r.threshold), font)),
    plotW,
    selected,
  );
  const spoken =
    `${card.stat}, chance to reach each line: ` +
    profile.points.map((p) => `${targetLabel(p.threshold)} ${formatProbability(p.chance)}`).join(", ") +
    (card.actual !== null ? `. Final ${formatPoints(card.actual)}` : "");
  return (
    <div ref={boxRef} className="w-full max-w-[720px]">
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={spoken} className="block max-w-full" data-testid="milestone-profile">
      {([[0, "0%"], [0.5, "50%"], [1, "100%"]] as const).map(([p, label]) => (
        <g key={p}>
          <line
            x1={left}
            x2={W - right}
            y1={y(p)}
            y2={y(p)}
            stroke={p === 0.5 ? "rgba(0,0,0,0.25)" : "rgba(0,0,0,0.08)"}
            strokeDasharray={p === 0.5 ? "3 3" : undefined}
          />
          <text x={left - 6} y={y(p) + font * 0.35} fontSize={font} textAnchor="end" fill="#4B5563">
            {label}
          </text>
        </g>
      ))}
      {card.actual !== null && (
        <g data-mark="final-actual" data-actual={card.actual}>
          <rect x={x(lo)} y={top} width={Math.max(0, x(card.actual) - x(lo))} height={plotH} fill={color} fillOpacity={0.07} />
          <line x1={x(card.actual)} x2={x(card.actual)} y1={top} y2={top + plotH} stroke={color} strokeWidth={2} />
        </g>
      )}
      {profile.points.map((p) => {
        const isSelected = p.index === selected;
        return (
          <g key={card.rungs[p.index].rowId} data-mark="milestone" data-threshold={p.threshold} data-selected={isSelected || undefined}>
            <line
              x1={x(p.threshold)}
              x2={x(p.threshold)}
              y1={y(0)}
              y2={y(p.chance)}
              stroke={color}
              strokeOpacity={isSelected ? 0.9 : 0.3}
              strokeWidth={isSelected ? 2 : 1.5}
            />
            <circle
              cx={x(p.threshold)}
              cy={y(p.chance)}
              r={isSelected ? 6 : 4}
              fill="#FFFFFF"
              stroke={isSelected ? color : "#6B7280"}
              strokeWidth={isSelected ? 2.5 : 1.5}
            />
          </g>
        );
      })}
      {card.rungs.map((r) => (
        <line
          key={r.rowId}
          x1={x(r.threshold)}
          x2={x(r.threshold)}
          y1={top + plotH}
          y2={top + plotH + 4}
          stroke="rgba(0,0,0,0.45)"
        />
      ))}
      {placements.map((p) => (
        <text
          key={card.rungs[p.index].rowId}
          x={left + p.center}
          y={H - font * 0.5}
          fontSize={font}
          textAnchor="middle"
          fill="#111827"
        >
          {targetLabel(card.rungs[p.index].threshold)}
        </text>
      ))}
    </svg>
    </div>
  );
}

export function MilestoneCardView({
  card,
  color,
  selected,
  onMove,
  onDetails,
  expanded = false,
  atlasMode = false,
}: {
  card: MilestoneCard;
  color: string | null | undefined;
  selected: number | null;
  onMove: (delta: number) => void;
  /** Opens the selected line's exact details. */
  onDetails?: (rowId: string) => void;
  expanded?: boolean;
  atlasMode?: boolean;
}) {
  const rung = selected !== null ? card.rungs[selected] : null;
  const ink = inkColor(color);
  const hasSettled = card.rungs.some((r) => r.hit !== null);
  const canOpenDetails = Boolean(onDetails && rung && (expanded || atlasMode));
  const readout = rung ? (
    <span className="flex flex-col items-center">
      <span
        className="text-sm font-semibold tabular-nums"
        style={{ color: rung.chance === null ? undefined : textColor(color) }}
      >
        {readoutText(card, rung, atlasMode)}
      </span>
      <span className="text-[11px] text-text-secondary">
        {verdictText(card, rung, expanded, atlasMode, Boolean(onDetails))}
      </span>
    </span>
  ) : null;
  return (
    <div className="flex flex-col gap-2" data-card-kind="milestone">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-text-secondary">{card.stat}</p>
          <h3 className="text-lg font-bold text-text-primary leading-snug line-clamp-2">{card.player}</h3>
        </div>
        {card.actual !== null && (
          <div className="flex flex-col items-end shrink-0">
            <span className="text-2xl font-bold tabular-nums" style={{ color: textColor(color) }}>
              {formatPoints(card.actual)}
            </span>
            <span className="text-[11px] text-text-secondary">final</span>
          </div>
        )}
        {atlasMode && onDetails && rung && (
          <button
            type="button"
            onClick={() => onDetails(rung.rowId)}
            aria-label={`Details for ${card.player} ${targetLabel(rung.threshold)}`}
            data-testid="atlas-story-card-details-button"
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[11px] font-semibold text-text-secondary hover:text-text-primary"
          >
            i
          </button>
        )}
      </div>
      <p className="text-xs text-text-secondary">{milestoneCaption(card)}</p>
      {atlasMode && (
        <div
          data-testid="atlas-story-card-mark-key"
          className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-text-secondary"
        >
          <span className="inline-flex items-center gap-1">
            <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full border-2 border-text-secondary bg-surface-card" />
            <span>Pregame</span>
          </span>
          {card.actual !== null && (
            <span className="inline-flex items-center gap-1">
              <span aria-hidden="true" className="inline-block h-2.5 w-0.5 bg-text-primary" />
              <span>Actual</span>
            </span>
          )}
          {hasSettled && (
            <span className="inline-flex items-center gap-1">
              <span className="font-semibold text-accent-live">✓ {propVerdictLabel(true)}</span>
              <span>/</span>
              <span className="font-semibold text-text-secondary">✗ {propVerdictLabel(false)}</span>
            </span>
          )}
        </div>
      )}
      <MilestoneProfileChart card={card} selected={selected} color={ink} expanded={expanded} atlasMode={atlasMode} />
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onMove(-1)}
          disabled={selected === null || selected === 0}
          aria-label="Previous line"
          className="w-11 h-11 shrink-0 flex items-center justify-center rounded-md text-text-primary hover:bg-surface-elevated disabled:text-text-muted disabled:hover:bg-transparent"
        >
          <span aria-hidden="true">‹</span>
        </button>
        {canOpenDetails && rung ? (
          <button
            type="button"
            onClick={() => onDetails!(rung.rowId)}
            className="flex-1 min-h-11 rounded-md hover:bg-surface-elevated"
          >
            {readout}
            <span className="sr-only">Opens this line&apos;s details</span>
          </button>
        ) : (
          <div className="flex-1 min-h-11 flex items-center justify-center" aria-live="polite">
            {readout}
          </div>
        )}
        <button
          type="button"
          onClick={() => onMove(1)}
          disabled={selected === null || selected >= card.rungs.length - 1}
          aria-label="Next line"
          className="w-11 h-11 shrink-0 flex items-center justify-center rounded-md text-text-primary hover:bg-surface-elevated disabled:text-text-muted disabled:hover:bg-transparent"
        >
          <span aria-hidden="true">›</span>
        </button>
      </div>
    </div>
  );
}

// ─── NBA ladders: scoring expectations and winning margin ──────────────────

/** The selected ladder point: the stored option while still on the card, nothing if it left, else the default. */
export function selectedLadderIndex(card: LadderCard, selection: CardSelection): number | null {
  const key = selection[card.id];
  if (key === undefined) return defaultLadderIndex(card);
  const index = card.points.findIndex((p) => p.optionKey === key);
  return index >= 0 ? index : null;
}

function ladderReadout(card: LadderCard, p: LadderPoint, atlasMode = false): { main: string; sub: string } {
  // Before tip-off a missing dot is a stale price; afterwards the caption already
  // says the pregame chance is unavailable, so the readout does not repeat it.
  const noPriceLabel = atlasMode ? ATLAS_STATE_COPY.noRecentPrice : "No recent price";
  const main =
    p.chance !== null
      ? `${p.label} · ${formatProbability(p.chance)}`
      : card.phase === "before"
        ? `${p.label} · ${noPriceLabel}`
        : p.label;
  // A final names its pregame chance apart from the verdict: "Before tip-off · MISS".
  // A line with none, on a card where others have one, says so itself.
  const parts: string[] = [];
  if (p.chance !== null) parts.push(card.phase === "before" ? "Pregame chance" : "Before tip-off");
  else if (card.phase === "after" && card.points.some((q) => q.chance !== null)) parts.push("Pregame chance unavailable");
  if (p.result !== null) {
    const prefix = atlasMode ? (p.result ? "✓ " : "✗ ") : "";
    parts.push(`${prefix}${propVerdictLabel(p.result)}`);
  }
  if (p.now !== null) parts.push(`now ${formatProbability(p.now)}`);
  return { main, sub: parts.join(" · ") };
}

function LadderChart({
  card,
  selected,
  teams,
  expanded,
  atlasMode = false,
}: {
  card: LadderCard;
  selected: number | null;
  teams: CardTeams;
  expanded: boolean;
  atlasMode?: boolean;
}) {
  const [boxRef, box] = usePlotBox();
  const W = box.width;
  const font = box.font;
  const margin = card.family === "margin";
  // With no chance to draw (a final with no admitted pin) there is no chance axis:
  // the plot collapses to a strip of the lines with the actual marked on it.
  const hasDots = card.points.some((p) => p.chance !== null || (atlasMode && p.now !== null));
  const H = hasDots
    ? (expanded ? 220 : 150) + (font - AXIS_FONT) * 2 + (margin ? font * 1.6 : 0)
    : font * (margin ? 5.6 : 4) + 28;
  const left = hasDots ? Math.ceil(labelWidth("100%", font)) + 10 : 10;
  const right = 10;
  const top = font + 10;
  const bottom = Math.ceil(font * (margin ? 3.6 : 2));
  const plotW = W - left - right;
  const plotH = H - top - bottom;
  const xs = [...card.points.map((p) => p.x), ...(card.actual !== null ? [card.actual] : []), ...(card.forecast !== null ? [card.forecast] : [])];
  const span = Math.max(...xs) - Math.min(...xs) || 1;
  const pad = Math.max(span * 0.06, 1);
  const lo = margin ? -Math.max(...xs.map(Math.abs)) - pad : Math.min(...xs) - pad;
  const hi = margin ? -lo : Math.max(...xs) + pad;
  const x = (v: number) => left + ((v - lo) / (hi - lo)) * plotW;
  const y = (p: number) => top + (1 - p) * plotH;
  const ink = (p: LadderPoint) =>
    inkColor(p.side === "home" ? teams.homeColor : p.side === "away" ? teams.awayColor : teams.homeColor);
  const step = margin ? (hi > 24 ? 10 : 5) : hi - lo > 60 ? 20 : 10;
  const ticks: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(t);
  const tickText = (t: number) => (margin ? (t === 0 ? "Tie" : String(Math.abs(t))) : String(t));
  const placements = axisLabelPlacements(
    ticks.map((t) => x(t) - left),
    ticks.map((t) => labelWidth(tickText(t), font)),
    plotW,
    null,
  );
  const drawn = card.points.filter((p) => p.chance !== null);
  const actualText = card.actual === null ? null : margin ? marginWords(card, card.actual) : String(card.actual);
  const spoken =
    `${ladderTitle(card)}. ${ladderCaption(card)}: ` +
    (drawn.length ? drawn.map((p) => `${p.label} ${formatProbability(p.chance!)}`).join(", ") : "none recorded") +
    (actualText ? `. ${card.phase === "after" ? "Final" : "So far"} ${actualText}` : "") +
    (card.forecast !== null ? `. Pregame projection ${margin ? marginWords(card, card.forecast) : card.forecast}` : "");
  return (
    <div ref={boxRef} className="w-full max-w-[720px]">
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={spoken} className="block max-w-full" data-testid={`ladder-${card.family}`}>
        {!hasDots && <line x1={left} x2={W - right} y1={top + plotH} y2={top + plotH} stroke="rgba(0,0,0,0.25)" />}
        {hasDots && ([[0, "0%"], [0.5, "50%"], [1, "100%"]] as const).map(([p, label]) => (
          <g key={p}>
            <line x1={left} x2={W - right} y1={y(p)} y2={y(p)} stroke={p === 0.5 ? "rgba(0,0,0,0.25)" : "rgba(0,0,0,0.08)"} strokeDasharray={p === 0.5 ? "3 3" : undefined} />
            <text x={left - 6} y={y(p) + font * 0.35} fontSize={font} textAnchor="end" fill="#4B5563">{label}</text>
          </g>
        ))}
        {margin && <line x1={x(0)} x2={x(0)} y1={top} y2={top + plotH} stroke="rgba(0,0,0,0.35)" />}
        {card.forecast !== null && (
          <g>
            <line x1={x(card.forecast)} x2={x(card.forecast)} y1={top - 4} y2={top + plotH} stroke="#4B5563" strokeWidth={1.5} strokeDasharray="4 3" data-mark="forecast" data-forecast={card.forecast} />
            {atlasMode && (
              <rect
                x={x(card.forecast) - 4}
                y={top + plotH - 4}
                width={8}
                height={8}
                fill="#FFFFFF"
                stroke="#4B5563"
                strokeWidth={1.75}
                data-mark="forecast-square"
              />
            )}
          </g>
        )}
        {card.actual !== null && (
          <line x1={x(card.actual)} x2={x(card.actual)} y1={top - 4} y2={top + plotH} stroke="#111827" strokeWidth={2} data-mark="actual" data-actual={card.actual} />
        )}
        {card.points.map((p, i) => {
          const isSelected = i === selected;
          const c = ink(p);
          return (
            <g key={p.optionKey} data-mark="ladder-line" data-x={p.x} data-selected={isSelected || undefined}>
              <line x1={x(p.x)} x2={x(p.x)} y1={top + plotH} y2={top + plotH + 4} stroke="rgba(0,0,0,0.45)" />
              {p.chance !== null && (
                <>
                  <line x1={x(p.x)} x2={x(p.x)} y1={y(0)} y2={y(p.chance)} stroke={c} strokeOpacity={isSelected ? 0.9 : 0.3} strokeWidth={isSelected ? 2 : 1.5} />
                  {atlasMode && p.now !== null && (
                    <line
                      x1={x(p.x)}
                      x2={x(p.x)}
                      y1={y(p.chance)}
                      y2={y(p.now)}
                      stroke={c}
                      strokeOpacity={isSelected ? 0.95 : 0.65}
                      strokeWidth={isSelected ? 2.5 : 1.75}
                      data-mark="ladder-connector"
                    />
                  )}
                  <circle cx={x(p.x)} cy={y(p.chance)} r={isSelected ? 6 : 4} fill="#FFFFFF" stroke={isSelected ? c : "#6B7280"} strokeWidth={isSelected ? 2.5 : 1.5} />
                </>
              )}
              {atlasMode && p.now !== null && (
                <circle
                  cx={x(p.x)}
                  cy={y(p.now)}
                  r={isSelected ? 5 : 3.5}
                  fill={c}
                  stroke="#FFFFFF"
                  strokeWidth={1}
                  data-mark="ladder-recorded"
                />
              )}
              {p.chance === null && isSelected && (
                <line x1={x(p.x)} x2={x(p.x)} y1={top + plotH - 10} y2={top + plotH} stroke={c} strokeWidth={2.5} />
              )}
            </g>
          );
        })}
        {placements.map((pl) => (
          <text key={ticks[pl.index]} x={left + pl.center} y={top + plotH + font * 1.5} fontSize={font} textAnchor="middle" fill="#111827">
            {tickText(ticks[pl.index])}
          </text>
        ))}
        {margin && (
          <>
            <text x={left} y={H - font * 0.4} fontSize={font} textAnchor="start" fill="#4B5563">← {card.awayShort} by</text>
            <text x={W - right} y={H - font * 0.4} fontSize={font} textAnchor="end" fill="#4B5563">{card.homeShort} by →</text>
          </>
        )}
      </svg>
    </div>
  );
}

export function LadderCardView({
  card,
  teams,
  selected,
  onMove,
  onDetails,
  expanded = false,
  atlasMode = false,
}: {
  card: LadderCard;
  teams: CardTeams;
  selected: number | null;
  onMove: (delta: number) => void;
  onDetails?: (optionKey: string) => void;
  expanded?: boolean;
  atlasMode?: boolean;
}) {
  const margin = card.family === "margin";
  const point = selected !== null ? card.points[selected] : null;
  const readout = point ? ladderReadout(card, point, atlasMode) : null;
  const actualText = card.actual === null ? null : margin ? marginWords(card, card.actual) : String(card.actual);
  const forecastText = card.forecast === null ? null : margin ? marginWords(card, card.forecast) : String(card.forecast);
  const pointInk = point ? (point.side === "away" ? teams.awayColor : teams.homeColor) : null;
  const canOpenDetails = Boolean(onDetails && point && (expanded || atlasMode));
  const hasRecordedNow = card.points.some((p) => p.now !== null);
  const hasSettled = card.points.some((p) => p.result !== null);
  const body = readout ? (
    <span className="flex flex-col items-center">
      <span className="text-sm font-semibold tabular-nums" style={{ color: point?.chance !== null ? textColor(pointInk) : undefined }}>{readout.main}</span>
      <span className="text-[11px] text-text-secondary">{readout.sub}{canOpenDetails ? (readout.sub ? " · details" : "details") : ""}</span>
    </span>
  ) : null;
  return (
    <div className="flex flex-col gap-2" data-card-kind={`ladder-${card.family}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-wide text-text-secondary">{ladderTitle(card)}</p>
        {atlasMode && onDetails && point && (
          <button
            type="button"
            onClick={() => onDetails(point.optionKey)}
            aria-label={`Details for ${point.label}`}
            data-testid="atlas-story-card-details-button"
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[11px] font-semibold text-text-secondary hover:text-text-primary"
          >
            i
          </button>
        )}
      </div>
      {(actualText || forecastText || (atlasMode && card.unit === "games" && card.phase === "after")) && (
        <div className="flex gap-6">
          {actualText ? (
            <div className="flex flex-col">
              <span className="text-[11px] text-text-secondary">{card.phase === "after" ? "Actual final" : "So far"}</span>
              <strong className="text-lg font-bold tabular-nums text-text-primary">{actualText}{!margin ? ` ${card.unit ?? "points"}` : ""}</strong>
            </div>
          ) : atlasMode && card.unit === "games" && card.phase === "after" ? (
            <div className="flex flex-col" data-testid="tennis-total-games-actual-absent">
              <span className="text-[11px] text-text-secondary">Actual final</span>
              <strong className="text-lg font-bold tabular-nums text-text-secondary">—</strong>
            </div>
          ) : null}
          {forecastText && (
            <div className="flex flex-col">
              <span className="text-[11px] text-text-secondary">Pregame projection</span>
              <strong className="text-lg font-bold tabular-nums text-text-primary">{forecastText}{!margin ? ` ${card.unit ?? "points"}` : ""}</strong>
            </div>
          )}
        </div>
      )}
      <p className="text-xs text-text-secondary">{ladderCaption(card)}</p>
      {atlasMode && (
        <div
          data-testid="atlas-story-card-mark-key"
          className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-text-secondary"
        >
          <span className="inline-flex items-center gap-1">
            <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full border-2 border-text-secondary bg-surface-card" />
            <span>Pregame</span>
          </span>
          {hasRecordedNow && (
            <>
              <span className="inline-flex items-center gap-1">
                <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full bg-text-primary" />
                <span>Recorded</span>
              </span>
              <span className="inline-flex items-center gap-1">
                <span aria-hidden="true" className="inline-block h-0.5 w-3 bg-text-secondary" />
                <span>Change</span>
              </span>
            </>
          )}
          {card.actual !== null && (
            <span className="inline-flex items-center gap-1">
              <span aria-hidden="true" className="inline-block h-2.5 w-0.5 bg-text-primary" />
              <span>Actual</span>
            </span>
          )}
          {card.forecast !== null && (
            <span className="inline-flex items-center gap-1">
              <span aria-hidden="true" className="inline-block h-2.5 w-2.5 border-2 border-text-secondary bg-surface-card" />
              <span>Projected</span>
            </span>
          )}
          {hasSettled && (
            <span className="inline-flex items-center gap-1">
              <span className="font-semibold text-accent-live">✓ {propVerdictLabel(true)}</span>
              <span>/</span>
              <span className="font-semibold text-text-secondary">✗ {propVerdictLabel(false)}</span>
            </span>
          )}
        </div>
      )}
      <LadderChart card={card} selected={selected} teams={teams} expanded={expanded} atlasMode={atlasMode} />
      <div className="flex items-center gap-1">
        <button type="button" onClick={() => onMove(-1)} disabled={selected === null || selected === 0} aria-label="Previous line" className="w-11 h-11 shrink-0 flex items-center justify-center rounded-md text-text-primary hover:bg-surface-elevated disabled:text-text-muted disabled:hover:bg-transparent">
          <span aria-hidden="true">‹</span>
        </button>
        {canOpenDetails && point ? (
          <button type="button" onClick={() => onDetails!(point.optionKey)} className="flex-1 min-h-11 rounded-md hover:bg-surface-elevated">
            {body}
            <span className="sr-only">Shows this line&apos;s exact quote</span>
          </button>
        ) : (
          <div className="flex-1 min-h-11 flex items-center justify-center" aria-live="polite">{body}</div>
        )}
        <button type="button" onClick={() => onMove(1)} disabled={selected === null || selected >= card.points.length - 1} aria-label="Next line" className="w-11 h-11 shrink-0 flex items-center justify-center rounded-md text-text-primary hover:bg-surface-elevated disabled:text-text-muted disabled:hover:bg-transparent">
          <span aria-hidden="true">›</span>
        </button>
      </div>
      {forecastText && (
        <p className="text-[11px] text-text-secondary">{card.actual !== null ? "Solid line = actual · dashed = pregame projection" : "Dashed line = pregame projection"}</p>
      )}
    </div>
  );
}

// ─── MLB story card views (#11974 Step E6a) ────────────────────────────────

export function MlbHomeRunCardView({
  card,
  teams,
  onDetails,
}: {
  card: MlbHomeRunCard;
  teams: CardTeams;
  onDetails?: (rowId: string) => void;
}) {
  const [boxRef, box] = usePlotBox();
  const W = box.width;
  const font = box.font;
  const left = 10;
  const right = 14;
  const plotW = Math.max(120, W - left - right);
  const x = (v: number) => left + (Math.min(Math.max(v, 0), card.scaleCeiling) / card.scaleCeiling) * plotW;
  const step = card.scaleCeiling <= 0.25 ? 0.05 : card.scaleCeiling <= 0.5 ? 0.1 : 0.25;
  const ticks: number[] = [];
  for (let t = 0; t <= card.scaleCeiling + 1e-9; t += step) {
    ticks.push(Number(t.toFixed(2)));
  }
  const firstEntry = card.entries[0];

  return (
    <div className="flex flex-col gap-2.5" data-card-kind="mlb-home-runs" data-testid="mlb-home-run-card">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-wide text-text-secondary">
          Home runs · chance of at least one
        </p>
        {onDetails && firstEntry && (
          <button
            type="button"
            onClick={() => onDetails(firstEntry.id)}
            aria-label="Details for Home runs"
            data-testid="atlas-story-card-details-button"
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[11px] font-semibold text-text-secondary hover:text-text-primary"
          >
            i
          </button>
        )}
      </div>
      <h3 className="text-lg font-bold text-text-primary leading-snug">{mlbHomeRunHeadline(card)}</h3>
      <p className="text-xs text-text-secondary">{mlbHomeRunReason(card)}</p>
      <div
        data-testid="atlas-story-card-mark-key"
        className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-text-secondary"
      >
        <span className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full border-2 border-text-secondary bg-surface-card" />
          <span>Pregame chance</span>
        </span>
        {card.phase === "after" && (
          <span className="inline-flex items-center gap-1">
            <span className="font-semibold text-accent-live">{ATLAS_STATE_COPY.wonWithCheck}</span>
            <span>/</span>
            <span className="font-semibold text-text-secondary">Official final</span>
          </span>
        )}
      </div>
      <div ref={boxRef} className="flex flex-col gap-2 w-full max-w-[720px]">
        {card.entries.map((entry, idx) => {
          const isLast = idx === card.entries.length - 1;
          const rawColor =
            entry.side === "home" ? teams.homeColor : entry.side === "away" ? teams.awayColor : null;
          const ink = inkColor(rawColor);
          const txt = textColor(rawColor);
          const svgH = isLast ? 42 : 24;
          const cy = 12;
          const finalText =
            entry.finalCount !== null
              ? `${entry.finalCount} HR · Final`
              : card.phase === "after"
                ? "Final unavailable"
                : "Pregame";
          const homered = entry.finalCount !== null && entry.finalCount >= 1;
          return (
            <button
              key={entry.id}
              type="button"
              onClick={() => onDetails?.(entry.id)}
              className="flex flex-col gap-1 rounded-md p-1.5 -mx-1.5 text-left hover:bg-surface-elevated"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="flex items-baseline gap-2 min-w-0">
                  <span className="text-sm font-semibold truncate" style={{ color: txt }}>
                    {entry.player}
                  </span>
                  <span className="text-xs font-semibold tabular-nums" style={{ color: txt }}>
                    {formatProbability(entry.saved)} pregame
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  {homered && (
                    <span className="inline-flex items-center rounded bg-accent-live/15 px-1.5 py-0.5 text-[11px] font-semibold text-accent-live">
                      {ATLAS_STATE_COPY.wonWithCheck}
                    </span>
                  )}
                  {!homered && entry.finalCount === 0 && (
                    <span className="inline-flex items-center rounded bg-surface-elevated px-1.5 py-0.5 text-[11px] font-semibold text-text-secondary">
                      {ATLAS_STATE_COPY.lostWithCross}
                    </span>
                  )}
                  <span className="text-xs font-bold tabular-nums text-text-primary">{finalText}</span>
                </div>
              </div>
              <svg viewBox={`0 0 ${W} ${svgH}`} width={W} height={svgH} className="block max-w-full" aria-hidden="true">
                {ticks.map((t) => (
                  <line
                    key={t}
                    x1={x(t)}
                    x2={x(t)}
                    y1={2}
                    y2={22}
                    stroke="rgba(0,0,0,0.08)"
                  />
                ))}
                <line
                  x1={x(0)}
                  x2={x(entry.saved)}
                  y1={cy}
                  y2={cy}
                  stroke={ink}
                  strokeOpacity={0.35}
                  strokeWidth={3}
                />
                <circle
                  cx={x(entry.saved)}
                  cy={cy}
                  r={5.5}
                  fill="#FFFFFF"
                  stroke={ink}
                  strokeWidth={2}
                  data-mark="pregame"
                />
                {isLast &&
                  ticks.map((t) => (
                    <text
                      key={t}
                      x={x(t)}
                      y={24 + font * 1.25}
                      fontSize={font}
                      textAnchor="middle"
                      fill="#4B5563"
                    >
                      {t === 0 ? "0%" : t === 1 ? "100%" : formatProbability(t)}
                    </text>
                  ))}
              </svg>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function MlbExtraInningsCardView({
  card,
  onDetails,
}: {
  card: MlbExtraInningsCard;
  onDetails?: (rowId: string) => void;
}) {
  const firstOutcome = card.outcomes[0];
  const hasPregame = card.outcomes.some((o) => o.pregameChance !== null);
  return (
    <div className="flex flex-col gap-2.5" data-card-kind="mlb-extra-innings" data-testid="mlb-extra-innings-card">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-wide text-text-secondary">
          Extra innings
        </p>
        {onDetails && firstOutcome && (
          <button
            type="button"
            onClick={() => onDetails(firstOutcome.id)}
            aria-label="Details for Extra innings"
            data-testid="atlas-story-card-details-button"
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[11px] font-semibold text-text-secondary hover:text-text-primary"
          >
            i
          </button>
        )}
      </div>
      <h3 className="text-lg font-bold text-text-primary leading-snug">Extra innings</h3>
      <p className="text-xs text-text-secondary">
        {hasPregame ? "Chance before first pitch and settled result" : "Pregame chance unavailable for this market"}
      </p>
      <div className="flex flex-col divide-y divide-surface-border">
        {card.outcomes.map((outcome) => (
          <button
            key={outcome.id}
            type="button"
            onClick={() => onDetails?.(outcome.id)}
            className="flex items-center justify-between gap-2 py-2.5 text-left hover:bg-surface-elevated rounded-md px-1.5 -mx-1.5"
          >
            <div className="flex flex-col min-w-0">
              <span className="text-sm font-semibold text-text-primary">{outcome.label}</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {outcome.pregameChance !== null && (
                <span className="inline-flex items-center gap-1 text-xs font-semibold tabular-nums text-text-secondary">
                  <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full border-2 border-text-secondary bg-surface-card" />
                  <span>{formatProbability(outcome.pregameChance)} pregame</span>
                </span>
              )}
              {outcome.venueResult === "won" && (
                <span className="inline-flex items-center rounded bg-accent-live/15 px-1.5 py-0.5 text-[11px] font-semibold text-accent-live">
                  {ATLAS_STATE_COPY.wonWithCheck}
                </span>
              )}
              {outcome.venueResult === "lost" && (
                <span className="inline-flex items-center rounded bg-surface-elevated px-1.5 py-0.5 text-[11px] font-semibold text-text-secondary">
                  {ATLAS_STATE_COPY.lostWithCross}
                </span>
              )}
              {outcome.venueResult !== "won" && outcome.venueResult !== "lost" && (
                <span className="text-xs font-semibold text-text-secondary">
                  {mlbVenueResultLabel(outcome.venueResult)}
                </span>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export function MlbSeriesCardView({
  card,
  teams,
  selection,
  onSelect,
  onDetails,
}: {
  card: MlbSeriesCard;
  teams: CardTeams;
  selection: CardSelection;
  onSelect: (cardId: string, rowId: string) => void;
  onDetails?: (rowId: string) => void;
}) {
  const selectedKey = selection[card.id];
  const activeQuestion =
    card.questions.find((q) => q.questionKey === selectedKey || q.options.some((o) => o.optionKey === selectedKey)) ??
    card.questions[0] ??
    null;
  const firstOption = activeQuestion?.options[0];
  const optionCount = card.questions.reduce((sum, q) => sum + q.options.length, 0);
  const accent = textColor(teams.homeColor);

  return (
    <div className="flex flex-col gap-2.5" data-card-kind="mlb-series" data-testid="mlb-series-card">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-wide text-text-secondary">
          Series · separate from this game
        </p>
        {onDetails && firstOption && (
          <button
            type="button"
            onClick={() => onDetails(firstOption.optionKey)}
            aria-label="Details for The series"
            data-testid="atlas-story-card-details-button"
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[11px] font-semibold text-text-secondary hover:text-text-primary"
          >
            i
          </button>
        )}
      </div>
      <h3 className="text-lg font-bold text-text-primary leading-snug">
        {activeQuestion?.label ?? "The series"}
      </h3>
      <p className="text-xs text-text-secondary">Separate series markets</p>
      {card.questions.length > 1 && (
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {card.questions.map((q) => {
            const isSelected = q.questionKey === activeQuestion?.questionKey;
            return (
              <button
                key={q.questionKey}
                type="button"
                onClick={() => onSelect(card.id, q.questionKey)}
                aria-pressed={isSelected}
                className={`shrink-0 rounded-md px-2.5 py-1.5 text-xs font-semibold ${
                  isSelected
                    ? "bg-text-primary text-surface-card"
                    : "bg-surface-elevated text-text-primary hover:bg-surface-border"
                }`}
              >
                {q.label}
              </button>
            );
          })}
        </div>
      )}
      {activeQuestion && (() => {
        const anyPregame = activeQuestion.options.some((o) => o.pregame !== null);
        return (
          <div className="grid grid-cols-2 gap-2">
            {activeQuestion.options.map((opt) => {
              const isSelected = opt.optionKey === selectedKey;
              return (
                <button
                  key={opt.optionKey}
                  type="button"
                  onClick={() => {
                    onSelect(card.id, opt.optionKey);
                    onDetails?.(opt.optionKey);
                  }}
                  className={`flex flex-col items-start gap-1 rounded-lg border p-2.5 text-left ${
                    isSelected
                      ? "border-text-primary bg-surface-elevated"
                      : "border-surface-border bg-surface-card hover:bg-surface-elevated"
                  }`}
                >
                  <span className="text-xs font-bold text-text-primary line-clamp-2">{opt.label}</span>
                  {anyPregame && (
                    <div className="flex flex-col">
                      <span className="text-[10px] text-text-secondary">Chance before this game</span>
                      <span
                        className="text-sm font-bold tabular-nums"
                        style={{ color: opt.pregame !== null ? accent : undefined }}
                      >
                        {opt.pregame !== null ? formatProbability(opt.pregame) : "Unavailable"}
                      </span>
                    </div>
                  )}
                  <div className="flex items-center gap-1 text-[11px] text-text-secondary">
                    {opt.result === "won" && (
                      <span className="font-semibold text-accent-live">{ATLAS_STATE_COPY.wonWithCheck}</span>
                    )}
                    {opt.result === "lost" && (
                      <span className="font-semibold text-text-secondary">{ATLAS_STATE_COPY.lostWithCross}</span>
                    )}
                    {opt.result !== "won" && opt.result !== "lost" && (
                      <span>{mlbVenueResultLabel(opt.result)}</span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        );
      })()}
      <p className="text-[11px] text-text-secondary">
        {optionCount} series {optionCount === 1 ? "outcome" : "outcomes"} · all in the Series section
      </p>
    </div>
  );
}

// ─── NHL story card views (#11974 Step E6b) ────────────────────────────────

export function NhlScoringCardView({
  card,
  teams,
  onDetails,
}: {
  card: NhlScoringCard;
  teams: CardTeams;
  onDetails?: (rowId: string) => void;
}) {
  const [boxRef, box] = usePlotBox();
  const W = box.width;
  const font = box.font;
  const left = 10;
  const right = 14;
  const plotW = Math.max(120, W - left - right);
  const x = (v: number) => left + (Math.min(Math.max(v, 0), card.scaleCeiling) / card.scaleCeiling) * plotW;
  const step = card.scaleCeiling <= 0.4 ? 0.1 : 0.2;
  const ticks: number[] = [];
  for (let t = 0; t <= card.scaleCeiling + 1e-9; t += step) {
    ticks.push(Number(t.toFixed(2)));
  }
  const firstEntry = card.entries[0];

  return (
    <div className="flex flex-col gap-2.5" data-card-kind="nhl-scoring" data-testid="nhl-scoring-card">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-wide text-text-secondary">
          Player goals · 1+ goal chance
        </p>
        {onDetails && firstEntry && (
          <button
            type="button"
            onClick={() => onDetails(firstEntry.id)}
            aria-label="Details for Goalscorers"
            data-testid="atlas-story-card-details-button"
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[11px] font-semibold text-text-secondary hover:text-text-primary"
          >
            i
          </button>
        )}
      </div>
      <h3 className="text-lg font-bold text-text-primary leading-snug">{nhlScoringHeadline(card)}</h3>
      <p className="text-xs text-text-secondary">{nhlScoringReason(card)}</p>
      <div
        data-testid="atlas-story-card-mark-key"
        className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-text-secondary"
      >
        <span className="inline-flex items-center gap-1">
          <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full border-2 border-text-secondary bg-surface-card" />
          <span>Pregame chance</span>
        </span>
        {card.phase === "after" && (
          <span className="inline-flex items-center gap-1">
            <span className="font-semibold text-accent-live">{ATLAS_STATE_COPY.wonWithCheck}</span>
            <span>/</span>
            <span className="font-semibold text-text-secondary">Final goals</span>
          </span>
        )}
      </div>
      <div ref={boxRef} className="flex flex-col gap-2 w-full max-w-[720px]">
        {card.entries.map((entry, idx) => {
          const isLast = idx === card.entries.length - 1;
          const rawColor =
            entry.side === "home" ? teams.homeColor : entry.side === "away" ? teams.awayColor : null;
          const ink = inkColor(rawColor);
          const txt = textColor(rawColor);
          const svgH = isLast ? 42 : 24;
          const cy = 12;
          const scored = entry.actualGoals !== null && entry.actualGoals >= 1;
          const finalText =
            entry.actualGoals !== null
              ? `${entry.actualGoals} ${entry.actualGoals === 1 ? "goal" : "goals"} · Final`
              : card.phase === "after"
                ? "Final unavailable"
                : "Pregame";
          return (
            <button
              key={entry.id}
              type="button"
              onClick={() => onDetails?.(entry.id)}
              className="flex flex-col gap-1 rounded-md p-1.5 -mx-1.5 text-left hover:bg-surface-elevated"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <div className="flex items-baseline gap-2 min-w-0">
                  <span className="text-sm font-semibold truncate" style={{ color: txt }}>
                    {entry.player}
                  </span>
                  <span className="text-xs font-semibold tabular-nums" style={{ color: txt }}>
                    {entry.pregameChance !== null
                      ? `${formatProbability(entry.pregameChance)} pregame`
                      : "Pregame unavailable"}
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  {scored && (
                    <span className="inline-flex items-center rounded bg-accent-live/15 px-1.5 py-0.5 text-[11px] font-semibold text-accent-live">
                      {ATLAS_STATE_COPY.wonWithCheck}
                    </span>
                  )}
                  {!scored && entry.actualGoals === 0 && (
                    <span className="inline-flex items-center rounded bg-surface-elevated px-1.5 py-0.5 text-[11px] font-semibold text-text-secondary">
                      {ATLAS_STATE_COPY.lostWithCross}
                    </span>
                  )}
                  <span className="text-xs font-bold tabular-nums text-text-primary">{finalText}</span>
                </div>
              </div>
              <svg viewBox={`0 0 ${W} ${svgH}`} width={W} height={svgH} className="block max-w-full" aria-hidden="true">
                {ticks.map((t) => (
                  <line
                    key={t}
                    x1={x(t)}
                    x2={x(t)}
                    y1={2}
                    y2={22}
                    stroke="rgba(0,0,0,0.08)"
                  />
                ))}
                {entry.pregameChance !== null && (
                  <>
                    <line
                      x1={x(0)}
                      x2={x(entry.pregameChance)}
                      y1={cy}
                      y2={cy}
                      stroke={ink}
                      strokeOpacity={0.35}
                      strokeWidth={3}
                    />
                    <circle
                      cx={x(entry.pregameChance)}
                      cy={cy}
                      r={5.5}
                      fill="#FFFFFF"
                      stroke={ink}
                      strokeWidth={2}
                      data-mark="pregame"
                    />
                  </>
                )}
                {isLast &&
                  ticks.map((t) => (
                    <text
                      key={t}
                      x={x(t)}
                      y={24 + font * 1.25}
                      fontSize={font}
                      textAnchor="middle"
                      fill="#4B5563"
                    >
                      {t === 0 ? "0%" : t === 1 ? "100%" : formatProbability(t)}
                    </text>
                  ))}
              </svg>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Soccer story cards (#11974 Step E6c) ──────────────────────────────────

export function SoccerThreeWayCardView({
  card,
  teams,
  onDetails,
}: {
  card: SoccerThreeWayCard;
  teams: CardTeams;
  onDetails?: (rowId: string) => void;
}) {
  const headline = soccerThreeWayHeadline(card);
  const reason = soccerThreeWayReason(card);
  const homeTxt = teamTextColor(teams.homeColor) ?? "#1F2937";
  const awayTxt = teamTextColor(teams.awayColor) ?? "#1F2937";
  const drawTxt = "#0F766E";
  const W = 310;
  const padL = 10;
  const padR = 14;
  const x = (p: number) => padL + Math.max(0, Math.min(1, p)) * (W - padL - padR);
  const ticks = [0, 0.5, 1];

  return (
    <div className="flex flex-col gap-3" data-testid="soccer-three-way-card">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
            Three-way match outcome · 90 minutes
          </span>
          <h4 className="text-lg font-bold text-text-primary leading-snug">{headline}</h4>
          <span className="text-xs text-text-secondary">{reason}</span>
        </div>
        {onDetails && (
          <button
            type="button"
            onClick={() => onDetails(card.legs[0]?.role ?? "home")}
            aria-label={`Details for ${headline}`}
            data-testid="atlas-story-card-details-button"
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[11px] font-semibold text-text-secondary hover:text-text-primary"
          >
            i
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] font-medium text-text-secondary">
        <span className="inline-flex items-center gap-1">
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <circle cx="5" cy="5" r="3.5" fill="#FFFFFF" stroke="#4B5563" strokeWidth="1.75" />
          </svg>
          Pregame chance
        </span>
        {card.phase === "during" && (
          <span className="inline-flex items-center gap-1">
            <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
              <circle cx="5" cy="5" r="3.75" fill="#1F2937" />
            </svg>
            Recorded live
          </span>
        )}
        {card.phase === "after" && (
          <span>
            <span className="text-accent-live font-semibold">{ATLAS_STATE_COPY.wonWithCheck}</span>
            {" / "}
            <span className="text-text-muted font-semibold">{ATLAS_STATE_COPY.lostWithCross}</span>
          </span>
        )}
      </div>

      <div className="flex flex-col gap-2.5">
        {card.legs.map((leg, idx) => {
          const isLast = idx === card.legs.length - 1;
          const svgH = isLast ? 40 : 24;
          const cy = 12;
          const color =
            leg.role === "home" ? homeTxt : leg.role === "away" ? awayTxt : drawTxt;
          const activeChance =
            card.phase === "after"
              ? leg.pregameChance
              : (leg.quotedChance ?? leg.pregameChance);
          const pregameMark = leg.pregameChance;
          const liveMark = card.phase === "during" ? leg.quotedChance : null;

          return (
            <button
              key={leg.role}
              type="button"
              onClick={() => onDetails?.(leg.role)}
              className="flex flex-col gap-1 rounded-md p-1.5 -mx-1.5 text-left hover:bg-surface-elevated"
              data-testid={`soccer-three-way-leg-${leg.role}`}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-semibold truncate" style={{ color }}>
                  {leg.label}
                </span>
                <div className="flex items-center gap-1.5">
                  {card.phase === "after" && leg.result === "won" && (
                    <span className="inline-flex items-center rounded bg-accent-live/15 px-1.5 py-0.5 text-[11px] font-semibold text-accent-live">
                      {ATLAS_STATE_COPY.wonWithCheck}
                    </span>
                  )}
                  {card.phase === "after" && leg.result === "lost" && (
                    <span className="inline-flex items-center rounded bg-surface-elevated px-1.5 py-0.5 text-[11px] font-semibold text-text-muted">
                      {ATLAS_STATE_COPY.lostWithCross}
                    </span>
                  )}
                  <span className="text-xs font-bold tabular-nums text-text-primary">
                    {activeChance !== null
                      ? card.phase === "after"
                        ? `${formatProbability(activeChance)} pregame`
                        : formatProbability(activeChance)
                      : ATLAS_STATE_COPY.noRecentPrice}
                  </span>
                </div>
              </div>
              <svg viewBox={`0 0 ${W} ${svgH}`} width={W} height={svgH} className="block max-w-full" aria-hidden="true">
                {ticks.map((t) => (
                  <line
                    key={t}
                    x1={x(t)}
                    x2={x(t)}
                    y1={2}
                    y2={22}
                    stroke="rgba(0,0,0,0.08)"
                  />
                ))}
                {activeChance !== null && (
                  <line
                    x1={x(0)}
                    x2={x(activeChance)}
                    y1={cy}
                    y2={cy}
                    stroke={color}
                    strokeOpacity={0.35}
                    strokeWidth={3.5}
                  />
                )}
                {pregameMark !== null && (
                  <circle
                    cx={x(pregameMark)}
                    cy={cy}
                    r={5}
                    fill="#FFFFFF"
                    stroke={color}
                    strokeWidth={2}
                    data-mark="pregame"
                  />
                )}
                {liveMark !== null && (
                  <circle
                    cx={x(liveMark)}
                    cy={cy}
                    r={5}
                    fill={color}
                    stroke="#FFFFFF"
                    strokeWidth={1.25}
                    data-mark="live"
                  />
                )}
                {isLast &&
                  ticks.map((t) => (
                    <text
                      key={t}
                      x={x(t)}
                      y={24 + 10 * 1.25}
                      fontSize={10}
                      textAnchor="middle"
                      fill="#4B5563"
                    >
                      {t === 0 ? "0%" : t === 1 ? "100%" : formatProbability(t)}
                    </text>
                  ))}
              </svg>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function SoccerExactScoreCardView({
  card,
  selection,
  onSelect,
  onDetails,
}: {
  card: SoccerExactScoreCard;
  selection: CardSelection;
  onSelect: (cardId: string, rowId: string) => void;
  onDetails?: (rowId: string) => void;
}) {
  const selectedKey = selection[card.id] ?? card.defaultSelectedKey;
  const cellsByKey = new Map(card.cells.map((c) => [c.key, c]));
  const selectedCell =
    cellsByKey.get(selectedKey) ??
    cellsByKey.get(card.defaultSelectedKey) ??
    card.cells[0] ??
    null;
  const coords = Array.from({ length: card.maxGoals + 1 }, (_, i) => i);

  return (
    <div className="flex flex-col gap-3" data-testid="soccer-exact-score-card">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <span className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
            Exact score · recorded quotes
          </span>
          <h4 className="text-lg font-bold text-text-primary leading-snug">
            The exact-score landscape
          </h4>
          <span className="text-xs text-text-secondary">
            {card.homeShort} goals across · {card.awayShort} goals down · all supplied cells retained
          </span>
        </div>
        {onDetails && selectedCell && (
          <button
            type="button"
            onClick={() => onDetails(selectedCell.key)}
            aria-label={`Details for Exact score ${selectedCell.outcomeLabel}`}
            data-testid="atlas-story-card-details-button"
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[11px] font-semibold text-text-secondary hover:text-text-primary"
          >
            i
          </button>
        )}
      </div>

      <div
        className="grid gap-1 items-center"
        style={{
          gridTemplateColumns: `36px repeat(${coords.length}, minmax(0, 1fr))`,
        }}
        role="group"
        aria-label="Exact-score probability heatmap"
      >
        <div className="text-[9px] font-semibold uppercase leading-tight text-text-muted">
          {card.awayShort.slice(0, 3).toUpperCase()}↓
          <br />
          {card.homeShort.slice(0, 3).toUpperCase()}→
        </div>
        {coords.map((xGoal) => (
          <div
            key={`col-${xGoal}`}
            className="text-center text-[11px] font-bold tabular-nums text-text-secondary"
          >
            {xGoal}
          </div>
        ))}
        {coords.map((yGoal) => (
          <div key={`row-${yGoal}`} className="contents">
            <div className="text-center text-[11px] font-bold tabular-nums text-text-secondary">
              {yGoal}
            </div>
            {coords.map((xGoal) => {
              const key = `${xGoal}-${yGoal}`;
              const cell = cellsByKey.get(key);
              const isSelected = selectedCell?.key === key;
              const isWon = cell?.result === "won";
              const ratio =
                cell && cell.chance !== null && card.maxChance > 0
                  ? Math.min(1, Math.max(0.08, cell.chance / card.maxChance))
                  : isWon
                    ? 0.85
                    : 0;
              const pctText =
                cell && cell.chance !== null
                  ? `${Math.round(cell.chance * 1000) / 10}`
                  : isWon
                    ? "✓"
                    : cell
                      ? "·"
                      : "—";

              return (
                <button
                  key={key}
                  type="button"
                  disabled={!cell}
                  aria-pressed={isSelected}
                  aria-label={
                    cell
                      ? `${card.homeShort} ${xGoal} – ${yGoal} ${card.awayShort}: ${
                          cell.chance !== null ? formatProbability(cell.chance) : cell.result ?? "quoted"
                        }`
                      : `${xGoal}–${yGoal}: not listed`
                  }
                  onClick={() => cell && onSelect(card.id, cell.key)}
                  data-testid={`soccer-score-cell-${key}`}
                  className={`min-h-[38px] rounded-md text-[11px] font-semibold tabular-nums transition-colors flex items-center justify-center ${
                    !cell
                      ? "bg-surface-elevated/40 text-text-muted/50 cursor-default"
                      : isSelected
                        ? "ring-2 ring-text-primary font-bold"
                        : " border border-surface-border/70"
                  }`}
                  style={
                    cell
                      ? {
                          backgroundColor: `rgba(15, 118, 110, ${(0.08 + ratio * 0.68).toFixed(2)})`,
                          color: ratio > 0.55 ? "#FFFFFF" : "#111827",
                        }
                      : undefined
                  }
                >
                  {pctText}
                </button>
              );
            })}
          </div>
        ))}
      </div>

      {selectedCell && (
        <button
          type="button"
          onClick={() => onDetails?.(selectedCell.key)}
          data-testid="soccer-exact-score-readout"
          className="flex items-center justify-between gap-2 rounded-lg border border-surface-border bg-surface-elevated/60 px-3 py-2 text-left hover:bg-surface-elevated"
        >
          <div className="flex flex-col gap-0.5 min-w-0">
            <span className="text-xs font-bold text-text-primary truncate">
              {card.homeShort} {selectedCell.homeGoals} – {selectedCell.awayGoals} {card.awayShort}
            </span>
            <span className="text-[11px] text-text-secondary truncate">
              {selectedCell.outcomeLabel} · tap for contract details
            </span>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            {selectedCell.result === "won" && (
              <span className="inline-flex items-center rounded bg-accent-live/15 px-1.5 py-0.5 text-[11px] font-semibold text-accent-live">
                {ATLAS_STATE_COPY.wonWithCheck}
              </span>
            )}
            {selectedCell.result === "lost" && (
              <span className="inline-flex items-center rounded bg-surface-card px-1.5 py-0.5 text-[11px] font-semibold text-text-muted">
                {ATLAS_STATE_COPY.lostWithCross}
              </span>
            )}
            {selectedCell.chance !== null && (
              <span className="text-sm font-bold tabular-nums text-text-primary">
                {formatProbability(selectedCell.chance)}
              </span>
            )}
          </div>
        </button>
      )}
    </div>
  );
}

// ─── Tennis story cards (#11974 Step E6d) ──────────────────────────────────

export function TennisSetsCardView({
  card,
  teams,
  onDetails,
}: {
  card: TennisSetsCard;
  teams: CardTeams;
  onDetails?: (rowId: string) => void;
}) {
  const firstStep = card.sets[0];
  const homeInk = inkColor(teams.homeColor);
  const awayInk = inkColor(teams.awayColor);

  return (
    <div className="flex flex-col gap-3" data-testid="tennis-sets-card">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            {card.stage === "after" ? "RESOLVED SET WINNERS" : "SET-BY-SET PATH"}
          </span>
          <h4 className="text-base font-bold text-text-primary leading-snug">
            {card.title}
          </h4>
          <span className="text-xs text-text-secondary">{card.subtitle}</span>
        </div>
        {onDetails && firstStep && (
          <button
            type="button"
            onClick={() => onDetails(`set:${firstStep.setNumber}`)}
            aria-label={`Details for ${card.title}`}
            data-testid="atlas-story-card-details-button"
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[11px] font-semibold text-text-secondary hover:text-text-primary"
          >
            i
          </button>
        )}
      </div>

      <div className="flex flex-col gap-2" role="list" aria-label={card.title}>
        {card.sets.map((step) => {
          const isResolved = step.winnerSide !== null;
          const winnerOpt =
            step.winnerSide === "home"
              ? step.home
              : step.winnerSide === "away"
                ? step.away
                : null;

          if (isResolved && winnerOpt) {
            return (
              <button
                key={step.setNumber}
                type="button"
                onClick={() => onDetails?.(`set:${step.setNumber}`)}
                data-testid={`tennis-set-step-${step.setNumber}`}
                className="flex flex-col gap-1.5 rounded-lg border border-surface-border bg-surface-elevated/50 px-3 py-2.5 text-left hover:bg-surface-elevated"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-card border border-surface-border text-[11px] font-bold tabular-nums text-text-primary">
                      {step.setNumber}
                    </span>
                    <span className="text-xs font-medium text-text-secondary">
                      {step.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {winnerOpt.pregameProbability !== null && (
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium tabular-nums text-text-secondary">
                        <svg width="8" height="8" viewBox="0 0 10 10" aria-hidden="true">
                          <circle
                            cx="5"
                            cy="5"
                            r="3.5"
                            fill="var(--surface-card)"
                            stroke={step.winnerSide === "home" ? homeInk : awayInk}
                            strokeWidth="1.75"
                          />
                        </svg>
                        {formatProbability(winnerOpt.pregameProbability)} pregame
                      </span>
                    )}
                    <span className="inline-flex items-center rounded bg-accent-live/15 px-1.5 py-0.5 text-[11px] font-semibold text-accent-live">
                      {ATLAS_STATE_COPY.wonWithCheck}
                    </span>
                  </div>
                </div>
                <span className="pl-7 text-sm font-bold text-text-primary">
                  {winnerOpt.playerName}
                </span>
              </button>
            );
          }

          return (
            <button
              key={step.setNumber}
              type="button"
              onClick={() => onDetails?.(`set:${step.setNumber}`)}
              data-testid={`tennis-set-step-${step.setNumber}`}
              className="flex flex-col gap-1.5 rounded-lg border border-surface-border bg-surface-elevated/50 px-3 py-2.5 text-left hover:bg-surface-elevated"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 text-xs font-bold text-text-primary">
                  <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-surface-card border border-surface-border text-[11px] font-bold tabular-nums">
                    {step.setNumber}
                  </span>
                  {step.label}
                </span>
                {step.source && (
                  <span className="text-[11px] text-text-secondary">
                    {step.source}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 pt-0.5">
                {([step.home, step.away] as const).map((opt) => {
                  const chance = opt.liveProbability ?? opt.pregameProbability;
                  const ink = opt.side === "home" ? homeInk : awayInk;
                  return (
                    <div
                      key={opt.side}
                      className="flex items-center justify-between gap-1.5 rounded bg-surface-card px-2 py-1 border border-surface-border/70"
                    >
                      <span className="text-xs font-semibold text-text-primary truncate">
                        {opt.shortName}
                      </span>
                      <span className="inline-flex items-center gap-1 text-xs font-bold tabular-nums text-text-primary shrink-0">
                        {opt.result === "pending" && (
                          <span className="rounded bg-surface-elevated px-1.5 py-0.5 text-[10px] font-semibold text-text-secondary">
                            Pending
                          </span>
                        )}
                        {chance !== null ? (
                          <>
                            <svg width="8" height="8" viewBox="0 0 10 10" aria-hidden="true">
                              <circle
                                cx="5"
                                cy="5"
                                r="3.5"
                                fill={opt.liveProbability !== null ? ink : "var(--surface-card)"}
                                stroke={ink}
                                strokeWidth="1.75"
                              />
                            </svg>
                            {formatProbability(chance)}
                          </>
                        ) : opt.result !== "pending" ? (
                          <span className="text-[11px] font-medium text-text-muted">
                            {ATLAS_STATE_COPY.noRecentPrice}
                          </span>
                        ) : null}
                      </span>
                    </div>
                  );
                })}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function TennisExactScoreCardView({
  card,
  onDetails,
}: {
  card: TennisExactScoreCard;
  onDetails?: (rowId: string) => void;
}) {
  const defaultOutcome = card.winningOutcome ?? card.outcomes[0] ?? null;

  return (
    <div className="flex flex-col gap-3" data-testid="tennis-exact-score-card">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            EXACT MATCH SCORE · SETS
          </span>
          <h4 className="text-base font-bold text-text-primary leading-snug">
            {card.title}
          </h4>
          <span className="text-xs text-text-secondary">{card.subtitle}</span>
        </div>
        {onDetails && defaultOutcome && (
          <button
            type="button"
            onClick={() => onDetails(defaultOutcome.optionKey)}
            aria-label={`Details for ${card.title}`}
            data-testid="atlas-story-card-details-button"
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-surface-border bg-surface-elevated text-[11px] font-semibold text-text-secondary hover:text-text-primary"
          >
            i
          </button>
        )}
      </div>

      <div
        className="grid grid-cols-2 gap-2"
        role="group"
        aria-label="Exact match score outcomes"
      >
        {card.outcomes.map((outcome) => {
          const isWon = outcome.result === "won";
          const isLost = outcome.result === "lost";
          const isPending = outcome.result === "pending";
          const chance = outcome.liveProbability ?? outcome.pregameProbability;
          return (
            <button
              key={outcome.optionKey}
              type="button"
              onClick={() => onDetails?.(outcome.optionKey)}
              data-testid={`tennis-exact-score-tile-${outcome.winnerSide}-${outcome.winnerSets}-${outcome.loserSets}`}
              className={`flex flex-col justify-between gap-1.5 rounded-lg border px-3 py-2.5 text-left transition-colors ${
                isWon
                  ? "border-accent-live bg-accent-live/10"
                  : "border-surface-border bg-surface-elevated/50 hover:bg-surface-elevated"
              }`}
            >
              <div className="flex items-center justify-between gap-1.5">
                <span className="text-xs font-bold text-text-primary">
                  {outcome.winnerShort} {outcome.winnerSets}–{outcome.loserSets}
                </span>
                {isWon && (
                  <span className="inline-flex items-center rounded bg-accent-live/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent-live shrink-0">
                    {ATLAS_STATE_COPY.wonWithCheck}
                  </span>
                )}
                {isLost && (
                  <span className="inline-flex items-center rounded bg-surface-card px-1.5 py-0.5 text-[10px] font-semibold text-text-muted shrink-0">
                    {ATLAS_STATE_COPY.lostWithCross}
                  </span>
                )}
                {isPending && (
                  <span className="inline-flex items-center rounded bg-surface-card px-1.5 py-0.5 text-[10px] font-semibold text-text-secondary shrink-0">
                    Pending
                  </span>
                )}
              </div>
              <div className="flex items-center justify-between gap-1 text-[11px] text-text-secondary">
                <span>
                  {outcome.winnerSets}–{outcome.loserSets} sets
                </span>
                {chance !== null ? (
                  <span className="font-bold tabular-nums text-text-primary shrink-0">
                    {formatProbability(chance)}
                  </span>
                ) : (
                  <span className="text-[10px] text-text-muted shrink-0">
                    {isPending
                      ? "Pending"
                      : outcome.result
                        ? "Settled"
                        : ATLAS_STATE_COPY.noRecentPrice}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Shared Atlas details-sheet adapter (#11974 Step E3) ───────────────────

export function buildStoryCardDetailsSheetProps(opts: {
  card?: NflEventCard | null;
  rowId?: string | null;
  row?: NflPropRow | OptionDetail;
  lead?: { chance: number; basis: MilestoneBasis } | null;
  rows?: Record<string, NflPropRow>;
  teams: CardTeams;
}): Omit<AtlasDetailsSheetProps, "open" | "onClose"> | null {
  const { card, rowId, row, lead, rows, teams } = opts;
  if (card?.kind === "tennis-sets") {
    const step =
      card.sets.find((s) => `set:${s.setNumber}` === rowId) ??
      card.sets[0] ??
      null;
    if (!step) return null;
    const focusOpt =
      step.winnerSide === "away"
        ? step.away
        : step.winnerSide === "home"
          ? step.home
          : step.home;
    const isSettled = focusOpt.result === "won" || focusOpt.result === "lost";
    const settledResult =
      focusOpt.result === "won"
        ? "won"
        : focusOpt.result === "lost"
          ? "lost"
          : null;
    return {
      subjectName: `${step.label} · ${focusOpt.playerName}`,
      marketTitle: step.marketName,
      isSettled,
      settledResult,
      openingProbability: focusOpt.pregameProbability,
      openingObservedAt: focusOpt.pregameObservedAt ?? focusOpt.observedAt,
      lastProbability: !isSettled ? focusOpt.liveProbability : null,
      lastObservedAt: focusOpt.observedAt,
      source: focusOpt.source,
      sourceCount: 1,
      rulesText: `${step.label}: ${step.home.playerName} vs ${step.away.playerName}`,
    };
  }

  if (card?.kind === "tennis-exact-score") {
    const outcome =
      card.outcomes.find((o) => o.optionKey === rowId) ??
      card.winningOutcome ??
      card.outcomes[0] ??
      null;
    if (!outcome) return null;
    const isSettled = outcome.result === "won" || outcome.result === "lost";
    const settledResult =
      outcome.result === "won"
        ? "won"
        : outcome.result === "lost"
          ? "lost"
          : null;
    return {
      subjectName: outcome.outcomeName,
      marketTitle: outcome.marketName,
      isSettled,
      settledResult,
      openingProbability: outcome.pregameProbability,
      openingObservedAt: outcome.pregameObservedAt ?? outcome.observedAt,
      lastProbability: !isSettled ? outcome.liveProbability : null,
      lastObservedAt: outcome.observedAt,
      source: outcome.source,
      sourceCount: 1,
      rulesText: `Exact match score in sets (${outcome.scoreLabel}). Games handicaps and games totals stay in a separate unit-specific group.`,
    };
  }

  if (card?.kind === "soccer-three-way") {
    const leg = card.legs.find((l) => l.role === rowId) ?? card.legs[0] ?? null;
    if (!leg) return null;
    const isSettled = leg.result === "won" || leg.result === "lost";
    const settledResult = leg.result;
    const rulesLines = ["90-minute three-way match outcome (Home / Draw / Away)"];
    if (card.quotedSum !== null) {
      rulesLines.push(`Recorded three-way sum: ${(Math.round(card.quotedSum * 1000) / 10).toFixed(1)}% (unnormalized)`);
    }
    return {
      subjectName: leg.label,
      marketTitle: card.marketTitle,
      isSettled,
      settledResult,
      openingProbability: leg.pregameChance,
      openingObservedAt: leg.pregameObservedAt ?? leg.observedAt,
      lastProbability: !isSettled ? leg.quotedChance : null,
      lastObservedAt: leg.observedAt,
      source: leg.source ?? card.source ?? null,
      sourceCount: 1,
      rulesText: rulesLines.join("\n"),
    };
  }

  if (card?.kind === "soccer-exact-score") {
    const cell =
      card.cells.find((c) => c.key === rowId) ??
      card.cells.find((c) => c.key === card.defaultSelectedKey) ??
      card.cells[0] ??
      null;
    if (!cell) return null;
    const isSettled = cell.result === "won" || cell.result === "lost";
    return {
      subjectName: `${card.homeShort} ${cell.homeGoals} – ${cell.awayGoals} ${card.awayShort}`,
      marketTitle: cell.marketTitle,
      isSettled,
      settledResult: cell.result,
      openingProbability: cell.pregameChance ?? (card.phase === "before" ? cell.chance : null),
      openingObservedAt: cell.observedAt,
      lastProbability: !isSettled && card.phase === "during" ? cell.chance : null,
      lastObservedAt: cell.observedAt,
      source: cell.source ?? card.source ?? null,
      sourceCount: 1,
      rulesText: `Exact 90-minute score: ${cell.outcomeLabel} · Unlisted score cells are not inferred as 0%`,
    };
  }

  if (card?.kind === "nhl-scoring") {
    const entry = card.entries.find((e) => e.id === rowId || e.rowId === rowId) ?? card.entries[0] ?? null;
    if (!entry) return null;
    const isSettled = entry.hit !== null || entry.actualGoals !== null;
    const settledResult =
      entry.hit === true || (entry.actualGoals !== null && entry.actualGoals >= 1)
        ? "won"
        : entry.hit === false || entry.actualGoals === 0
          ? "lost"
          : null;
    const rulesLines: string[] = ["Line: 1+ goals"];
    if (entry.actualGoals !== null) {
      rulesLines.push(`Final goals: ${entry.actualGoals}`);
    }
    return {
      subjectName: entry.player,
      marketTitle: entry.marketTitle,
      isSettled,
      settledResult,
      openingProbability: entry.pregameChance,
      openingObservedAt: entry.observedAt,
      lastObservedAt: entry.observedAt,
      source: entry.source,
      sourceCount: entry.sourceCount,
      rulesText: rulesLines.join("\n"),
    };
  }

  if (card?.kind === "mlb-home-runs") {
    const entry = card.entries.find((e) => e.id === rowId) ?? card.entries[0] ?? null;
    if (!entry) return null;
    const isSettled =
      (entry.finalState === "final" && entry.finalCount !== null) ||
      entry.venueResult === "won" ||
      entry.venueResult === "lost";
    const settledResult =
      entry.finalCount !== null
        ? entry.finalCount >= 1
          ? "won"
          : "lost"
        : entry.venueResult === "won"
          ? "won"
          : entry.venueResult === "lost"
            ? "lost"
            : null;
    const rulesLines = [
      `Official final: ${
        entry.finalCount !== null
          ? `${entry.finalCount} home ${entry.finalCount === 1 ? "run" : "runs"}`
          : entry.finalState === "pending"
            ? "Pending"
            : "Unavailable"
      }`,
      `Result: ${mlbVenueResultLabel(entry.venueResult)}`,
    ];
    if (entry.finalSourceLabel && entry.finalCount !== null) {
      rulesLines.push(`Final source: ${entry.finalSourceLabel}`);
    }
    return {
      subjectName: entry.player,
      marketTitle: entry.marketTitle,
      isSettled,
      settledResult,
      openingProbability: entry.saved,
      openingObservedAt: entry.observedAt,
      lastObservedAt: entry.observedAt,
      source: "blended",
      sourceCount: entry.sourceCount,
      rulesText: rulesLines.join("\n"),
    };
  }

  if (card?.kind === "mlb-extra-innings") {
    const outcome = card.outcomes.find((o) => o.id === rowId) ?? card.outcomes[0] ?? null;
    if (!outcome) return null;
    const isSettled = outcome.venueResult === "won" || outcome.venueResult === "lost";
    const settledResult =
      outcome.venueResult === "won" ? "won" : outcome.venueResult === "lost" ? "lost" : null;
    return {
      subjectName: outcome.label,
      marketTitle: outcome.marketName,
      isSettled,
      settledResult,
      openingProbability: outcome.pregameChance,
      openingObservedAt: outcome.observedAt,
      lastObservedAt: outcome.observedAt,
      source: "blended",
      sourceCount: outcome.sourceCount,
      rulesText: `Result: ${mlbVenueResultLabel(outcome.venueResult)}`,
    };
  }

  if (card?.kind === "mlb-series") {
    const allOptions = card.questions.flatMap((q) => q.options);
    const opt = allOptions.find((o) => o.optionKey === rowId) ?? allOptions[0] ?? null;
    if (!opt) return null;
    const isSettled = opt.result === "won" || opt.result === "lost";
    const settledResult = opt.result === "won" ? "won" : opt.result === "lost" ? "lost" : null;
    return {
      subjectName: opt.label,
      marketTitle: opt.marketName,
      isSettled,
      settledResult,
      openingProbability: opt.pregame,
      openingObservedAt: opt.observedAt,
      lastObservedAt: opt.observedAt,
      source: "blended",
      sourceCount: opt.sourceCount,
      rulesText: `Separate series market · Result: ${mlbVenueResultLabel(opt.result)}`,
    };
  }

  if (card?.kind === "finish" || rowId === "finish") {
    if (card?.kind !== "finish") return null;
    const winnerSide =
      card.phase === "after" && card.final && card.final.home !== card.final.away
        ? card.final.home > card.final.away
          ? "home"
          : "away"
        : null;
    const lastAtMs = card.final?.at ?? card.projectedNow?.at ?? card.pregame.at;
    const rulesLines = [
      `Pregame projection: ${teams.awayName} ${formatPoints(card.pregame.away)}, ${teams.homeName} ${formatPoints(card.pregame.home)}`,
    ];
    if (card.projectedNow) {
      rulesLines.push(
        `Projected now: ${teams.awayName} ${formatPoints(card.projectedNow.away)}, ${teams.homeName} ${formatPoints(card.projectedNow.home)}`,
      );
    }
    if (card.final) {
      rulesLines.push(
        `Final score: ${teams.awayName} ${formatPoints(card.final.away)}, ${teams.homeName} ${formatPoints(card.final.home)}`,
      );
    }
    return {
      subjectName: finishHeadline(card, teams.awayName, teams.homeName),
      marketTitle: `${teams.awayName} at ${teams.homeName} · ${finishKicker(card)}`,
      isSettled: winnerSide !== null,
      settledResult: winnerSide !== null ? "won" : null,
      lastObservedAt: lastAtMs ? new Date(lastAtMs).toISOString() : null,
      source: "sportsbooks",
      sourceCount: 1,
      rulesText: rulesLines.join("\n"),
    };
  }

  if ((row && "detail" in row) || card?.kind === "ladder") {
    const point =
      card?.kind === "ladder"
        ? (card.points.find((p) => p.optionKey === rowId) ?? card.points[0] ?? null)
        : null;
    const detail: OptionDetail | undefined = row && "detail" in row ? row : point?.detail;
    if (!detail) return null;
    const isSettled = detail.result !== null;
    const settledResult = detail.result === true ? "won" : detail.result === false ? "lost" : null;
    const openingProbability =
      detail.baseline ?? (card?.kind === "ladder" && card.phase === "before" ? (point?.chance ?? null) : null);
    const openingObservedAt =
      detail.baselineObservedAt ??
      (card?.kind === "ladder" && card.phase === "before" ? (point?.observedAt ?? null) : null);
    const lastProbability = point?.now ?? (!isSettled ? detail.quoted : null);
    const rulesLines: string[] = [];
    if (card?.kind === "ladder") {
      const margin = card.family === "margin";
      const unitLabel = card.unit ?? "points";
      const actualText =
        card.actual === null ? null : margin ? marginWords(card, card.actual) : `${card.actual} ${unitLabel}`;
      const forecastText =
        card.forecast === null ? null : margin ? marginWords(card, card.forecast) : `${card.forecast} ${unitLabel}`;
      if (actualText) {
        rulesLines.push(`${card.phase === "after" ? "Actual final" : "So far"}: ${actualText}`);
      }
      if (forecastText) {
        rulesLines.push(`Pregame projection: ${forecastText}`);
      }
    }
    return {
      subjectName: detail.label,
      marketTitle: detail.marketName,
      isSettled,
      settledResult,
      openingProbability,
      openingObservedAt,
      lastProbability,
      lastObservedAt: detail.observedAt,
      source: detail.source ?? "sportsbooks",
      sourceCount: 1,
      rulesText: rulesLines.length > 0 ? rulesLines.join("\n") : null,
    };
  }

  const propRow: NflPropRow | undefined =
    (row && !("detail" in row) ? row : undefined) ?? (rowId && rows ? rows[rowId] : undefined);
  const rung =
    card?.kind === "milestone"
      ? (card.rungs.find((r) => r.rowId === rowId) ?? card.rungs[0] ?? null)
      : null;
  if (!propRow && !rung) return null;
  const hit = typeof propRow?.hit === "boolean" ? propRow.hit : (rung?.hit ?? null);
  const isSettled = hit !== null;
  const settledResult = hit === true ? "won" : hit === false ? "lost" : null;
  const openingProbability = lead ? lead.chance : (rung?.chance ?? propRow?.pregame_mark ?? null);
  const lastProbability =
    !isSettled && typeof propRow?.over_probability === "number" ? propRow.over_probability : null;
  const actualVal =
    typeof propRow?.actual === "number"
      ? propRow.actual
      : card?.kind === "milestone"
        ? card.actual
        : null;
  const thresholdVal =
    typeof propRow?.threshold === "number" ? propRow.threshold : (rung?.threshold ?? null);
  const rulesLines: string[] = [];
  if (thresholdVal !== null) rulesLines.push(`Line: ${targetLabel(thresholdVal)}`);
  if (actualVal !== null) rulesLines.push(`Final actual: ${formatPoints(actualVal)}`);
  return {
    subjectName:
      propRow?.outcome_name ??
      (card?.kind === "milestone" && rung ? `${card.player}: ${targetLabel(rung.threshold)}` : "Player milestone"),
    marketTitle:
      propRow?.market_name ?? (card?.kind === "milestone" ? `${card.player} · ${card.stat}` : "Player prop"),
    isSettled,
    settledResult,
    openingProbability,
    lastProbability,
    lastObservedAt: propRow?.observed_at ?? rung?.observedAt ?? null,
    source: propRow?.source ?? "sportsbooks",
    sourceCount: 1,
    rulesText: rulesLines.length > 0 ? rulesLines.join("\n") : null,
  };
}

// ─── One card, either family ───────────────────────────────────────────────

export function EventCardView({
  card,
  teams,
  selection,
  onSelect,
  onDetails,
  expanded = false,
  atlasMode = false,
}: {
  card: NflEventCard;
  teams: CardTeams;
  selection: CardSelection;
  onSelect: (cardId: string, rowId: string) => void;
  onDetails?: (rowId: string) => void;
  expanded?: boolean;
  atlasMode?: boolean;
}) {
  if (card.kind === "tennis-sets") {
    return <TennisSetsCardView card={card} teams={teams} onDetails={onDetails} />;
  }
  if (card.kind === "tennis-exact-score") {
    return <TennisExactScoreCardView card={card} onDetails={onDetails} />;
  }
  if (card.kind === "soccer-three-way") {
    return <SoccerThreeWayCardView card={card} teams={teams} onDetails={onDetails} />;
  }
  if (card.kind === "soccer-exact-score") {
    return (
      <SoccerExactScoreCardView
        card={card}
        selection={selection}
        onSelect={onSelect}
        onDetails={onDetails}
      />
    );
  }
  if (card.kind === "nhl-scoring") {
    return <NhlScoringCardView card={card} teams={teams} onDetails={onDetails} />;
  }
  if (card.kind === "mlb-home-runs") {
    return <MlbHomeRunCardView card={card} teams={teams} onDetails={onDetails} />;
  }
  if (card.kind === "mlb-extra-innings") {
    return <MlbExtraInningsCardView card={card} onDetails={onDetails} />;
  }
  if (card.kind === "mlb-series") {
    return (
      <MlbSeriesCardView
        card={card}
        teams={teams}
        selection={selection}
        onSelect={onSelect}
        onDetails={onDetails}
      />
    );
  }
  if (card.kind === "finish") {
    return (
      <FinishCardView
        card={card}
        teams={teams}
        expanded={expanded}
        atlasMode={atlasMode}
        onDetails={onDetails}
      />
    );
  }
  if (card.kind === "ladder") {
    const index = selectedLadderIndex(card, selection);
    return (
      <LadderCardView
        card={card}
        teams={teams}
        selected={index}
        expanded={expanded}
        atlasMode={atlasMode}
        onDetails={onDetails}
        onMove={(delta) => {
          if (index === null) return;
          const next = card.points[index + delta];
          if (next) onSelect(card.id, next.optionKey);
        }}
      />
    );
  }
  const color = card.side === "home" ? teams.homeColor : card.side === "away" ? teams.awayColor : null;
  const selected = selectedRungIndex(card, selection);
  return (
    <MilestoneCardView
      card={card}
      color={color}
      selected={selected}
      expanded={expanded}
      atlasMode={atlasMode}
      onDetails={onDetails}
      onMove={(delta) => {
        if (selected === null) return;
        const next = card.rungs[selected + delta];
        if (next) onSelect(card.id, next.rowId);
      }}
    />
  );
}

// ─── The deck under the chart ──────────────────────────────────────────────

/**
 * #11120: whether the deck returns to its start when its lead card changes.
 * The finish card can arrive after the prop cards and is inserted in front of
 * them; a snapping row keeps the card it had snapped to, so the new lead
 * opened off-screen to the left. Untouched, the deck shows its lead; once the
 * reader has swiped, tapped or focused inside it, their position is theirs.
 */
export function deckReturnsToStart(prevLeadId: string | null, nextLeadId: string | null, touched: boolean): boolean {
  return !touched && prevLeadId !== null && nextLeadId !== null && prevLeadId !== nextLeadId;
}

function useDeckLeadInView(leadId: string | null) {
  const rowRef = useRef<HTMLDivElement>(null);
  const touched = useRef(false);
  const prevLead = useRef(leadId);
  useLayoutEffect(() => {
    const el = rowRef.current;
    if (el && deckReturnsToStart(prevLead.current, leadId, touched.current)) el.scrollLeft = 0;
    prevLead.current = leadId;
  }, [leadId]);
  const touch = () => {
    touched.current = true;
  };
  return { rowRef, touchProps: { onPointerDown: touch, onTouchStart: touch, onWheel: touch, onKeyDown: touch, onFocus: touch } };
}

/**
 * The compact cards side by side, each with an explicit "Open full size"
 * control: the page scrolls vertically, so a tap on a chart inside a card is
 * never taken as a request to expand it.
 */
export function NFLEventCardDeck({
  cards,
  teams,
  selection,
  onSelect,
  onOpen,
  openerRef,
  headingRef,
  atlasMode = false,
  rows,
}: {
  cards: NflEventCard[];
  teams: CardTeams;
  selection: CardSelection;
  onSelect: (cardId: string, rowId: string) => void;
  onOpen: (cardId: string) => void;
  /** Registers each card's Open control, so Back returns focus to it. */
  openerRef: (cardId: string, el: HTMLButtonElement | null) => void;
  headingRef?: Ref<HTMLHeadingElement>;
  atlasMode?: boolean;
  rows?: Record<string, NflPropRow>;
}) {
  const { rowRef, touchProps } = useDeckLeadInView(cards[0]?.id ?? null);
  const [atlasSheetTarget, setAtlasSheetTarget] = useState<{
    card: NflEventCard;
    rowId: string;
  } | null>(null);
  if (cards.length === 0) return null;
  const sheetProps =
    atlasMode && atlasSheetTarget
      ? buildStoryCardDetailsSheetProps({
          card: atlasSheetTarget.card,
          rowId: atlasSheetTarget.rowId,
          rows,
          teams,
        })
      : null;
  return (
    <section aria-labelledby="nfl-game-stories-heading" className="flex flex-col gap-2" data-testid="nfl-game-stories">
      <div className="flex items-baseline justify-between px-1">
        <DeckHeading ref={headingRef} />
        <span className="text-xs text-text-secondary">{cards.length === 1 ? "1 card" : `${cards.length} cards`}</span>
      </div>
      <div ref={rowRef} {...touchProps} className="flex gap-3 overflow-x-auto snap-x snap-mandatory pb-1 -mx-1 px-1">
        {cards.map((card) => (
          <div
            key={card.id}
            className={`snap-start shrink-0 flex flex-col gap-1 ${cards.length > 1 ? "w-[86%] sm:w-[360px]" : "w-full sm:w-[420px]"}`}
            data-card-id={card.id}
          >
            <div className="bg-surface-card rounded-card shadow-card border border-surface-border p-4 flex-1">
              <EventCardView
                card={card}
                teams={teams}
                selection={selection}
                onSelect={onSelect}
                atlasMode={atlasMode}
                onDetails={
                  atlasMode ? (rowId) => setAtlasSheetTarget({ card, rowId }) : undefined
                }
              />
            </div>
            <button
              type="button"
              ref={(el) => openerRef(card.id, el)}
              onClick={() => onOpen(card.id)}
              aria-label={`Open ${cardTitle(card)} full size`}
              className="min-h-11 rounded-md text-xs font-semibold text-text-primary hover:bg-surface-elevated focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-brand"
            >
              Open full size
            </button>
          </div>
        ))}
      </div>
      {atlasMode && sheetProps && (
        <AtlasDetailsSheet
          open
          onClose={() => setAtlasSheetTarget(null)}
          {...sheetProps}
        />
      )}
    </section>
  );
}

const DeckHeading = forwardRef<HTMLHeadingElement>(function DeckHeading(_props, ref) {
  return (
    <h2 id="nfl-game-stories-heading" ref={ref} tabIndex={-1} className="text-base font-semibold text-text-primary">
      Game stories
    </h2>
  );
});
