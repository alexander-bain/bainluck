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
  type MilestoneCard,
  type MilestoneRung,
  type NflEventCard,
} from "@/lib/nflEventCardDeck";
import {
  defaultLadderIndex,
  ladderCaption,
  ladderTitle,
  marginWords,
  type LadderCard,
  type LadderPoint,
} from "@/lib/nbaEventCards";

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

export function FinishCardView({ card, teams, expanded = false }: { card: FinishCard; teams: CardTeams; expanded?: boolean }) {
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
  const rows = [
    { name: teams.awayName, label: teams.awayShort || teams.awayName, color: teams.awayColor, pregame: card.pregame.away, later: later?.away },
    { name: teams.homeName, label: teams.homeShort || teams.homeName, color: teams.homeColor, pregame: card.pregame.home, later: later?.home },
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
      <p className="text-xs font-bold uppercase tracking-wide" style={{ color: textColor(teams.homeColor) }}>
        {finishKicker(card)}
      </p>
      <h3 className="text-lg font-bold text-text-primary leading-snug">{headline}</h3>
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

function readoutText(card: MilestoneCard, rung: MilestoneRung): string {
  const none = card.basis === "pregamePrice" ? "No recent price" : "No pregame chance";
  return `${targetLabel(rung.threshold)} · ${rung.chance !== null ? formatProbability(rung.chance) : none}`;
}

function verdictText(card: MilestoneCard, rung: MilestoneRung, expanded: boolean): string {
  const more = expanded ? " · details" : "";
  // The site's one settled vocabulary (UX-P106), not the phone's wording.
  if (rung.hit !== null) return `${propVerdictLabel(rung.hit)}${more}`;
  if (rung.chance === null) {
    if (!expanded) return "";
    return card.basis === "pregamePrice" ? "Last quote in details" : "Details";
  }
  return (card.basis === "pregamePrice" ? "Pregame chance" : "Before kickoff") + more;
}

function MilestoneProfileChart({
  card,
  selected,
  color,
  expanded,
}: {
  card: MilestoneCard;
  selected: number | null;
  color: string;
  expanded: boolean;
}) {
  const [boxRef, box] = usePlotBox();
  const profile = milestoneProfile(card);
  if (!profile) {
    return (
      <p
        className={`flex items-center justify-center text-sm text-text-secondary ${expanded ? "min-h-[120px]" : "min-h-[60px]"}`}
      >
        No recent prices
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
}: {
  card: MilestoneCard;
  color: string | null | undefined;
  selected: number | null;
  onMove: (delta: number) => void;
  /** Full size only: opens the selected line's exact details. */
  onDetails?: (rowId: string) => void;
  expanded?: boolean;
}) {
  const rung = selected !== null ? card.rungs[selected] : null;
  const ink = inkColor(color);
  const readout = rung ? (
    <span className="flex flex-col items-center">
      <span
        className="text-sm font-semibold tabular-nums"
        style={{ color: rung.chance === null ? undefined : textColor(color) }}
      >
        {readoutText(card, rung)}
      </span>
      <span className="text-[11px] text-text-secondary">{verdictText(card, rung, expanded)}</span>
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
      </div>
      <p className="text-xs text-text-secondary">{milestoneCaption(card)}</p>
      <MilestoneProfileChart card={card} selected={selected} color={ink} expanded={expanded} />
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
        {expanded && onDetails && rung ? (
          <button
            type="button"
            onClick={() => onDetails(rung.rowId)}
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

function ladderReadout(card: LadderCard, p: LadderPoint): { main: string; sub: string } {
  // Before tip-off a missing dot is a stale price; afterwards the caption already
  // says the pregame chance is unavailable, so the readout does not repeat it.
  const main =
    p.chance !== null
      ? `${p.label} · ${formatProbability(p.chance)}`
      : card.phase === "before"
        ? `${p.label} · No recent price`
        : p.label;
  // A final names its pregame chance apart from the verdict: "Before tip-off · MISS".
  // A line with none, on a card where others have one, says so itself.
  const parts: string[] = [];
  if (p.chance !== null) parts.push(card.phase === "before" ? "Pregame chance" : "Before tip-off");
  else if (card.phase === "after" && card.points.some((q) => q.chance !== null)) parts.push("Pregame chance unavailable");
  if (p.result !== null) parts.push(propVerdictLabel(p.result));
  if (p.now !== null) parts.push(`now ${formatProbability(p.now)}`);
  return { main, sub: parts.join(" · ") };
}

function LadderChart({
  card,
  selected,
  teams,
  expanded,
}: {
  card: LadderCard;
  selected: number | null;
  teams: CardTeams;
  expanded: boolean;
}) {
  const [boxRef, box] = usePlotBox();
  const W = box.width;
  const font = box.font;
  const margin = card.family === "margin";
  // With no chance to draw (a final with no admitted pin) there is no chance axis:
  // the plot collapses to a strip of the lines with the actual marked on it.
  const hasDots = card.points.some((p) => p.chance !== null);
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
          <line x1={x(card.forecast)} x2={x(card.forecast)} y1={top - 4} y2={top + plotH} stroke="#4B5563" strokeWidth={1.5} strokeDasharray="4 3" data-mark="forecast" data-forecast={card.forecast} />
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
                  <circle cx={x(p.x)} cy={y(p.chance)} r={isSelected ? 6 : 4} fill="#FFFFFF" stroke={isSelected ? c : "#6B7280"} strokeWidth={isSelected ? 2.5 : 1.5} />
                </>
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
}: {
  card: LadderCard;
  teams: CardTeams;
  selected: number | null;
  onMove: (delta: number) => void;
  onDetails?: (optionKey: string) => void;
  expanded?: boolean;
}) {
  const margin = card.family === "margin";
  const point = selected !== null ? card.points[selected] : null;
  const readout = point ? ladderReadout(card, point) : null;
  const actualText = card.actual === null ? null : margin ? marginWords(card, card.actual) : String(card.actual);
  const forecastText = card.forecast === null ? null : margin ? marginWords(card, card.forecast) : String(card.forecast);
  const pointInk = point ? (point.side === "away" ? teams.awayColor : teams.homeColor) : null;
  const body = readout ? (
    <span className="flex flex-col items-center">
      <span className="text-sm font-semibold tabular-nums" style={{ color: point?.chance !== null ? textColor(pointInk) : undefined }}>{readout.main}</span>
      <span className="text-[11px] text-text-secondary">{readout.sub}{expanded && onDetails ? (readout.sub ? " · details" : "details") : ""}</span>
    </span>
  ) : null;
  return (
    <div className="flex flex-col gap-2" data-card-kind={`ladder-${card.family}`}>
      <p className="text-xs font-bold uppercase tracking-wide text-text-secondary">{ladderTitle(card)}</p>
      {(actualText || forecastText) && (
        <div className="flex gap-6">
          {actualText && (
            <div className="flex flex-col">
              <span className="text-[11px] text-text-secondary">{card.phase === "after" ? "Actual final" : "So far"}</span>
              <strong className="text-lg font-bold tabular-nums text-text-primary">{actualText}{!margin ? " points" : ""}</strong>
            </div>
          )}
          {forecastText && (
            <div className="flex flex-col">
              <span className="text-[11px] text-text-secondary">Pregame projection</span>
              <strong className="text-lg font-bold tabular-nums text-text-primary">{forecastText}{!margin ? " points" : ""}</strong>
            </div>
          )}
        </div>
      )}
      <p className="text-xs text-text-secondary">{ladderCaption(card)}</p>
      <LadderChart card={card} selected={selected} teams={teams} expanded={expanded} />
      <div className="flex items-center gap-1">
        <button type="button" onClick={() => onMove(-1)} disabled={selected === null || selected === 0} aria-label="Previous line" className="w-11 h-11 shrink-0 flex items-center justify-center rounded-md text-text-primary hover:bg-surface-elevated disabled:text-text-muted disabled:hover:bg-transparent">
          <span aria-hidden="true">‹</span>
        </button>
        {expanded && onDetails && point ? (
          <button type="button" onClick={() => onDetails(point.optionKey)} className="flex-1 min-h-11 rounded-md hover:bg-surface-elevated">
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

// ─── One card, either family ───────────────────────────────────────────────

export function EventCardView({
  card,
  teams,
  selection,
  onSelect,
  onDetails,
  expanded = false,
}: {
  card: NflEventCard;
  teams: CardTeams;
  selection: CardSelection;
  onSelect: (cardId: string, rowId: string) => void;
  onDetails?: (rowId: string) => void;
  expanded?: boolean;
}) {
  if (card.kind === "finish") return <FinishCardView card={card} teams={teams} expanded={expanded} />;
  if (card.kind === "ladder") {
    const index = selectedLadderIndex(card, selection);
    return (
      <LadderCardView
        card={card}
        teams={teams}
        selected={index}
        expanded={expanded}
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
}: {
  cards: NflEventCard[];
  teams: CardTeams;
  selection: CardSelection;
  onSelect: (cardId: string, rowId: string) => void;
  onOpen: (cardId: string) => void;
  /** Registers each card's Open control, so Back returns focus to it. */
  openerRef: (cardId: string, el: HTMLButtonElement | null) => void;
  headingRef?: Ref<HTMLHeadingElement>;
}) {
  const { rowRef, touchProps } = useDeckLeadInView(cards[0]?.id ?? null);
  if (cards.length === 0) return null;
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
              <EventCardView card={card} teams={teams} selection={selection} onSelect={onSelect} />
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
