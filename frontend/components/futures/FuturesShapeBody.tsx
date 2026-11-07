"use client";

import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { FuturesOutcome } from "@/lib/types";
import { formatProbabilityPercent, probabilityParts } from "@/lib/probabilityDisplay";
import {
  boardOutcomeLabel,
  hasCurrentPrice,
  readableOpeningProbability,
} from "@/lib/futuresDetailDisplay";
import {
  SHAPE_CLAIM,
  SHAPE_CONTAINER_MEMBER,
  SHAPE_DUEL,
  SHAPE_FIELD,
  SHAPE_PARTICIPATION,
  SHAPE_QUANTITY,
  SHAPE_UNSHAPED,
  type MarketShape,
} from "@/lib/marketShape";
import { outcomeRowVerdict } from "@/components/futures/OutcomeRow";
import { ATLAS_STATE_COPY } from "@/components/atlas/atlasStateCopy";
import { SERIES_COLORS } from "@/lib/seriesColors";

/**
 * Retain each continuing contender's color slot across cohort changes
 * (#883 Step F5, Decide 47: E — `docs/designs/event-page-atlas-2026-10/src/contenderColors.ts`).
 */
export function retainContenderColors(
  previous: Record<string, number>,
  ids: readonly string[],
  capacity = 3,
): Record<string, number> {
  const shown = ids.slice(0, capacity);
  const next: Record<string, number> = {};
  const used = new Set<number>();

  for (const id of shown) {
    const prev = previous[id];
    if (
      typeof prev === "number" &&
      prev >= 0 &&
      prev < capacity &&
      !used.has(prev)
    ) {
      next[id] = prev;
      used.add(prev);
    }
  }

  let free = 0;
  for (const id of shown) {
    if (next[id] !== undefined) continue;
    while (used.has(free) && free < capacity) free += 1;
    next[id] = free < capacity ? free : 0;
    used.add(next[id]);
  }

  return next;
}

/**
 * Build the leader cohort (`beforeCohort` pattern from `dunhillBefore.ts`,
 * #883 Step F5, Decide 47: E): defaults to the top `capacity` leaders; when a
 * contender outside the top `capacity` is chosen from the "N more" sheet,
 * pins that contender beside the top `capacity - 1` other leaders.
 */
export function buildAtlasFieldCohort<T extends { id: number }>(
  orderedPool: readonly T[],
  selectedOutcomeId: number | null | undefined,
  capacity = 3,
): T[] {
  const top = orderedPool.slice(0, capacity);
  if (selectedOutcomeId == null) return top;
  const chosen = orderedPool.find((row) => row.id === selectedOutcomeId);
  if (!chosen || top.some((row) => row.id === chosen.id)) {
    return top;
  }
  return [
    chosen,
    ...orderedPool
      .filter((row) => row.id !== chosen.id)
      .slice(0, Math.max(0, capacity - 1)),
  ];
}

export type AtlasBodyKind =
  | "one-leg"
  | "duel"
  | "field"
  | "qualifier"
  | "quantity"
  | null;

export interface RenderedPair {
  current: number | null;
  opening: number | null;
}

/**
 * Resolve which Atlas body presentation applies for a market's stored shape
 * and outcome set (#883 Step F2).
 *
 * - 1 supplied outcome -> "one-leg" (never invents a "No" side)
 * - quantity shape or threshold groups -> "quantity" (handled by QuantityGroup
 *   or plain list when ladder_treatment_refused is true per #11942)
 * - 2 outcomes (duel / claim / container_member / unshaped) -> "duel" (two-sided dial)
 * - participation or non-mutually-exclusive field -> "qualifier" ("do not add to 100")
 * - mutually exclusive multi-outcome field -> "field" (top 3 + searchable full list)
 */
export function resolveAtlasBodyKind(params: {
  marketShape: MarketShape | null;
  outcomeCount: number;
  mutuallyExclusive?: boolean | null;
  hasThresholdGroups?: boolean;
}): AtlasBodyKind {
  const {
    marketShape,
    outcomeCount,
    mutuallyExclusive,
    hasThresholdGroups = false,
  } = params;

  if (outcomeCount <= 0) return null;
  if (marketShape === SHAPE_QUANTITY || hasThresholdGroups) {
    return "quantity";
  }
  if (outcomeCount === 1) {
    return "one-leg";
  }
  if (
    outcomeCount === 2 &&
    (marketShape === SHAPE_DUEL ||
      marketShape === SHAPE_CLAIM ||
      marketShape === SHAPE_CONTAINER_MEMBER ||
      marketShape === SHAPE_UNSHAPED ||
      marketShape === null)
  ) {
    return "duel";
  }
  if (
    marketShape === SHAPE_PARTICIPATION ||
    (mutuallyExclusive === false && marketShape !== SHAPE_DUEL)
  ) {
    return "qualifier";
  }
  if (marketShape === SHAPE_FIELD || outcomeCount > 2) {
    return mutuallyExclusive === false ? "qualifier" : "field";
  }
  return "duel";
}

function formatServerChance(
  probability: number | null | undefined,
  rendered?: number | null,
): string {
  if (probability == null || !Number.isFinite(probability)) {
    return ATLAS_STATE_COPY.noRecentPrice;
  }
  return formatProbabilityPercent(probability, {
    rendered: rendered ?? undefined,
  });
}

function effectivePercentNumber(
  probability: number | null | undefined,
  rendered?: number | null,
): number | null {
  if (probability == null || !Number.isFinite(probability)) return null;
  if (rendered != null && Number.isFinite(rendered)) return rendered;
  const parts = probabilityParts(probability);
  const parsed = Number(parts.digits);
  return Number.isFinite(parsed) ? parsed : Math.round(probability * 100);
}

function MarkLegend() {
  return (
    <div
      data-testid="atlas-body-mark-key"
      className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-text-secondary"
    >
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden="true"
          className="inline-block h-2.5 w-2.5 rounded-full border-2 border-text-primary bg-surface-card"
        />
        <span>Opening</span>
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden="true"
          className="inline-block h-2.5 w-2.5 rounded-full bg-text-primary"
        />
        <span>Recorded</span>
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          aria-hidden="true"
          className="inline-block h-0.5 w-3.5 bg-text-primary"
        />
        <span>Connector · change in points</span>
      </span>
    </div>
  );
}

function MovementRail({
  name,
  opening,
  recorded,
  renderedOpening,
  renderedCurrent,
  color,
}: {
  name: string;
  opening: number | null;
  recorded: number | null;
  renderedOpening?: number | null;
  renderedCurrent?: number | null;
  color?: string;
}) {
  const x = (p: number) => 5 + Math.max(0, Math.min(1, p)) * 90;
  const openLabel =
    opening == null
      ? "unavailable"
      : formatServerChance(opening, renderedOpening);
  const recLabel =
    recorded == null
      ? "unavailable"
      : formatServerChance(recorded, renderedCurrent);

  return (
    <svg
      viewBox="0 0 100 20"
      role="img"
      aria-label={`${name}. Opening ${openLabel}. Recorded ${recLabel}.`}
      className="h-5 w-28 shrink-0 sm:w-36"
    >
      <line
        x1="5"
        x2="95"
        y1="10"
        y2="10"
        stroke="currentColor"
        strokeWidth="1.5"
        className="text-surface-border"
      />
      {opening != null && recorded != null && (
        <line
          x1={x(opening)}
          x2={x(recorded)}
          y1="10"
          y2="10"
          stroke={color ?? "currentColor"}
          strokeWidth="2"
          className={color ? undefined : "text-accent-brand"}
        />
      )}
      {opening != null && (
        <circle
          cx={x(opening)}
          cy="10"
          r="3.5"
          stroke={color ?? "currentColor"}
          strokeWidth="1.75"
          className={`fill-surface-card ${color ? "" : "text-text-primary"}`}
        />
      )}
      {recorded != null && (
        <circle
          cx={x(recorded)}
          cy="10"
          r="3.5"
          fill={color ?? "currentColor"}
          className={color ? undefined : "text-accent-brand"}
        />
      )}
    </svg>
  );
}

export interface FuturesShapeBodyProps {
  outcomes: FuturesOutcome[];
  sortedOutcomes: FuturesOutcome[];
  pricedOutcomes: FuturesOutcome[];
  renderedById: Map<number, RenderedPair>;
  marketName: string;
  marketShape: MarketShape | null;
  mutuallyExclusive?: boolean | null;
  isResolved: boolean;
  sourceCount?: number | null;
  hasThresholdGroups?: boolean;
  independenceNote?: string | null;
  selectedOutcomeId?: number | null;
  outcomeColors?: Map<number, string>;
  onSelectOutcome?: (outcomeId: number) => void;
  onOpenDetails?: () => void;
}

export default function FuturesShapeBody({
  outcomes,
  sortedOutcomes,
  pricedOutcomes,
  renderedById,
  marketName,
  marketShape,
  mutuallyExclusive,
  isResolved,
  sourceCount = 1,
  hasThresholdGroups = false,
  independenceNote = null,
  selectedOutcomeId = null,
  outcomeColors,
  onSelectOutcome,
  onOpenDetails,
}: FuturesShapeBodyProps) {
  const bodyKind = resolveAtlasBodyKind({
    marketShape,
    outcomeCount: outcomes.length,
    mutuallyExclusive,
    hasThresholdGroups,
  });

  const orderedOutcomes = useMemo(
    () => (sortedOutcomes.length > 0 ? sortedOutcomes : outcomes),
    [sortedOutcomes, outcomes],
  );

  const [activeId, setActiveId] = useState<number | null>(
    selectedOutcomeId ?? orderedOutcomes[0]?.id ?? null,
  );
  const [sheetOpen, setSheetOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [mounted, setMounted] = useState(false);
  const sheetTitleId = useId();
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const colorSlotsRef = useRef<Record<string, number>>({});

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (
      selectedOutcomeId != null &&
      outcomes.some((o) => o.id === selectedOutcomeId)
    ) {
      setActiveId(selectedOutcomeId);
    } else if (
      activeId == null ||
      !outcomes.some((o) => o.id === activeId)
    ) {
      setActiveId(orderedOutcomes[0]?.id ?? null);
    }
  }, [selectedOutcomeId, outcomes, orderedOutcomes, activeId]);

  useEffect(() => {
    if (!sheetOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setSheetOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [sheetOpen]);

  if (!bodyKind || bodyKind === "quantity") {
    return null;
  }

  const isMultiVenue = (sourceCount ?? 1) > 1;
  const activeOutcome =
    orderedOutcomes.find((o) => o.id === activeId) ?? orderedOutcomes[0];

  const handleChooseOutcome = (id: number) => {
    setActiveId(id);
    onSelectOutcome?.(id);
  };

  if (bodyKind === "one-leg" || bodyKind === "duel") {
    const dialRows = bodyKind === "one-leg" ? outcomes.slice(0, 1) : orderedOutcomes.slice(0, 2);
    const selected =
      dialRows.find((r) => r.id === activeOutcome?.id) ?? dialRows[0];
    if (!selected) return null;

    const selectedRendered = renderedById.get(selected.id);
    const rawOpening = readableOpeningProbability(selected);
    const opening = !isMultiVenue && rawOpening != null ? rawOpening : null;
    const verdict = outcomeRowVerdict(selected, isResolved);
    const recorded =
      !isResolved && hasCurrentPrice(selected) ? selected.probability : null;

    const openPctNum = effectivePercentNumber(
      opening,
      selectedRendered?.opening ?? null,
    );
    const recPctNum = effectivePercentNumber(
      recorded,
      selectedRendered?.current ?? null,
    );
    const changePoints =
      openPctNum != null && recPctNum != null ? recPctNum - openPctNum : null;

    const pointOnArc = (p: number) => {
      const clamped = Math.max(0, Math.min(1, p));
      return {
        x: Number((150 + 112 * Math.cos(Math.PI * (1 - clamped))).toFixed(2)),
        y: Number((138 - 112 * Math.sin(Math.PI * (1 - clamped))).toFixed(2)),
      };
    };

    const startPt = opening == null ? null : pointOnArc(opening);
    const endPt = recorded == null ? null : pointOnArc(recorded);
    const selectedLabel = boardOutcomeLabel(selected.name, marketName);

    return (
      <section
        data-testid={
          bodyKind === "one-leg" ? "atlas-one-leg-body" : "atlas-duel-body"
        }
        aria-label={
          bodyKind === "one-leg"
            ? "One market, one supplied side"
            : "Two sides of the market"
        }
        className="rounded-card border border-surface-border bg-surface-card p-5 shadow-card"
      >
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            {isResolved ? "Opening → result" : "Opening → recorded"}
          </span>
          {onOpenDetails && (
            <button
              type="button"
              onClick={onOpenDetails}
              aria-label="Selected outcome details"
              className="text-xs font-medium text-text-secondary hover:text-text-primary"
            >
              ⓘ Details
            </button>
          )}
        </div>
        <h2 className="mb-3 text-title-3 font-semibold text-text-primary">
          {bodyKind === "one-leg"
            ? "One market, one supplied side"
            : "Two sides of the market"}
        </h2>

        <div data-testid="atlas-binary-dial">
          {/* Side selector pills — never invents a second side on a one-leg market */}
          <div
            role="group"
            aria-label="Named outcomes"
            data-testid="atlas-dial-sides"
            className="mb-4 flex flex-wrap gap-2"
          >
            {dialRows.map((row) => {
              const rowVerdict = outcomeRowVerdict(row, isResolved);
              const rowRendered = renderedById.get(row.id);
              const rowLabel = boardOutcomeLabel(row.name, marketName);
              const isSelected = row.id === selected.id;
              const sideValueText = rowVerdict
                ? rowVerdict === "won"
                  ? ATLAS_STATE_COPY.wonWithCheck
                  : ATLAS_STATE_COPY.lostWithCross
                : !isResolved && hasCurrentPrice(row)
                  ? formatServerChance(row.probability, rowRendered?.current)
                  : ATLAS_STATE_COPY.noRecentPrice;

              return (
                <button
                  key={row.id}
                  type="button"
                  aria-pressed={isSelected}
                  data-testid="atlas-dial-side-button"
                  onClick={() => handleChooseOutcome(row.id)}
                  className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs font-semibold transition-colors ${
                    isSelected
                      ? "border-text-primary bg-text-primary text-surface-card"
                      : "border-surface-border bg-surface-elevated text-text-primary hover:bg-surface-border"
                  }`}
                >
                  <span>{rowLabel}</span>
                  <span
                    className={`tabular-nums ${
                      isSelected ? "text-surface-card/90" : "text-text-secondary"
                    }`}
                  >
                    {sideValueText}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Opening vs Recorded / Result comparison */}
          <div
            data-testid="atlas-dial-comparison"
            className={`mb-3 grid gap-3 rounded-xl border border-surface-border bg-surface-deep p-3.5 ${
              opening != null ? "grid-cols-2" : "grid-cols-1"
            }`}
          >
            {opening != null && (
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-secondary">
                  <span
                    aria-hidden="true"
                    className="inline-block h-2.5 w-2.5 rounded-full border-2 border-text-primary bg-surface-card"
                  />
                  <span>Opening</span>
                </div>
                <div
                  data-testid="atlas-dial-opening-value"
                  className="mt-1 text-lg font-bold tabular-nums text-text-primary"
                >
                  {formatServerChance(opening, selectedRendered?.opening)}
                </div>
                <div className="mt-0.5 text-[11px] text-text-muted">
                  Opening chance
                </div>
              </div>
            )}

            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-text-secondary">
                {verdict ? (
                  <span>Result</span>
                ) : (
                  <>
                    <span
                      aria-hidden="true"
                      className="inline-block h-2.5 w-2.5 rounded-full bg-accent-brand"
                    />
                    <span>Recorded</span>
                  </>
                )}
              </div>
              <div
                data-testid="atlas-dial-recorded-value"
                className={`mt-1 text-lg font-bold tabular-nums ${
                  verdict === "won"
                    ? "text-accent-live"
                    : verdict === "lost"
                      ? "text-text-secondary"
                      : "text-text-primary"
                }`}
              >
                {verdict
                  ? verdict === "won"
                    ? ATLAS_STATE_COPY.wonWithCheck
                    : ATLAS_STATE_COPY.lostWithCross
                  : recorded == null
                    ? ATLAS_STATE_COPY.noRecentPrice
                    : formatServerChance(recorded, selectedRendered?.current)}
              </div>
              <div className="mt-0.5 truncate text-[11px] text-text-muted">
                {verdict ? "Confirmed grade" : selectedLabel}
              </div>
            </div>
          </div>

          {/* Semicircle dial SVG */}
          <svg
            viewBox="0 0 300 173"
            role="img"
            aria-label={`${selectedLabel}. Hollow is opening; solid is recorded; connector is change in points. Zero to 100 percent.`}
            className="mx-auto block w-full max-w-[320px]"
          >
            <path
              d="M38 138 A112 112 0 0 1 262 138"
              fill="none"
              stroke="currentColor"
              strokeWidth="8"
              strokeLinecap="round"
              className="text-surface-border"
            />
            {[0, 0.5, 1].map((p) => {
              const pt = pointOnArc(p);
              return (
                <circle
                  key={p}
                  cx={pt.x}
                  cy={pt.y}
                  r="2.5"
                  fill="currentColor"
                  className="text-text-muted"
                />
              );
            })}
            {startPt && endPt && changePoints != null && changePoints !== 0 && (
              <path
                data-testid="atlas-dial-connector"
                d={`M${startPt.x} ${startPt.y} A112 112 0 0 ${
                  recorded! > opening! ? 1 : 0
                } ${endPt.x} ${endPt.y}`}
                fill="none"
                stroke="currentColor"
                strokeWidth="8"
                strokeLinecap="round"
                className="text-accent-brand"
              />
            )}
            {startPt && (
              <circle
                data-testid="atlas-dial-opening-dot"
                cx={startPt.x}
                cy={startPt.y}
                r="6"
                stroke="currentColor"
                strokeWidth="2.5"
                className="fill-surface-card text-text-primary"
              />
            )}
            {endPt && (
              <circle
                data-testid="atlas-dial-recorded-dot"
                cx={endPt.x}
                cy={endPt.y}
                r="5.5"
                fill="currentColor"
                className="text-accent-brand"
              />
            )}
            <text
              x="150"
              y="98"
              textAnchor="middle"
              data-testid="atlas-dial-summary"
              className="fill-text-primary text-[22px] font-bold"
            >
              {verdict
                ? verdict === "won"
                  ? ATLAS_STATE_COPY.wonWithCheck
                  : ATLAS_STATE_COPY.lostWithCross
                : changePoints != null
                  ? `${changePoints > 0 ? "+" : ""}${changePoints} pp`
                  : recorded != null
                    ? formatServerChance(recorded, selectedRendered?.current)
                    : "—"}
            </text>
            <text
              x="150"
              y="119"
              textAnchor="middle"
              className="fill-text-secondary text-[11px]"
            >
              {verdict
                ? "Confirmed result"
                : changePoints != null
                  ? "since opening"
                  : recorded == null
                    ? ATLAS_STATE_COPY.noRecentPrice
                    : "Recorded chance"}
            </text>
            <text
              x="38"
              y="161"
              textAnchor="middle"
              className="fill-text-muted text-[11px]"
            >
              0%
            </text>
            <text
              x="150"
              y="14"
              textAnchor="middle"
              className="fill-text-muted text-[11px]"
            >
              50%
            </text>
            <text
              x="262"
              y="161"
              textAnchor="middle"
              className="fill-text-muted text-[11px]"
            >
              100%
            </text>
          </svg>
        </div>
      </section>
    );
  }

  // Field ("field") or Qualifier ("qualifier")
  const isQualifier = bodyKind === "qualifier";
  const baseLeaderPool =
    pricedOutcomes.length > 0 ? pricedOutcomes : orderedOutcomes;
  const shownCount = isQualifier ? 6 : 3;
  const topLeaderIds = new Set(
    baseLeaderPool.slice(0, shownCount).map((row) => row.id),
  );
  const leadingRows = buildAtlasFieldCohort(
    baseLeaderPool,
    activeOutcome?.id ?? null,
    shownCount,
  );
  const retainedSlots = retainContenderColors(
    colorSlotsRef.current,
    leadingRows.map((row) => String(row.id)),
    shownCount,
  );
  colorSlotsRef.current = retainedSlots;
  const remainingCount = Math.max(0, outcomes.length - leadingRows.length);

  const normalizedQuery = searchQuery.trim().toLocaleLowerCase();
  const filteredSheetRows = orderedOutcomes.filter((row) => {
    if (!normalizedQuery) return true;
    const label = boardOutcomeLabel(row.name, marketName).toLocaleLowerCase();
    return (
      label.includes(normalizedQuery) ||
      row.name.toLocaleLowerCase().includes(normalizedQuery)
    );
  });

  const openSearchSheet = () => {
    setSheetOpen(true);
  };

  const closeSearchSheet = () => {
    setSheetOpen(false);
    triggerRef.current?.focus();
  };

  return (
    <section
      data-testid={isQualifier ? "atlas-qualifier-body" : "atlas-field-body"}
      aria-label={
        isQualifier ? "Independent qualification chances" : "Leading contenders"
      }
      className="rounded-card border border-surface-border bg-surface-card p-5 shadow-card"
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
          {isQualifier
            ? "Independent qualification chances"
            : isResolved
              ? "Opening → result"
              : "Opening → recorded"}
        </span>
        <button
          ref={triggerRef}
          type="button"
          onClick={openSearchSheet}
          data-testid="atlas-field-open-list"
          className="text-xs font-medium text-accent-brand hover:underline"
        >
          All outcomes · {outcomes.length}
        </button>
      </div>

      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-title-3 font-semibold text-text-primary">
          {isQualifier ? "Qualification field" : "Top three contenders"}
        </h2>
        {isQualifier && (
          <span
            data-testid="atlas-qualifier-do-not-add"
            className="inline-flex items-center rounded-full border border-surface-border bg-surface-elevated px-2.5 py-0.5 text-xs font-medium text-text-secondary"
          >
            Independent chances · do not add to 100%
          </span>
        )}
      </div>

      {isQualifier && (
        <p
          data-testid="atlas-qualifier-note"
          className="mb-3 text-xs text-text-secondary"
        >
          {independenceNote ||
            "Each outcome can qualify independently. These chances do not add to 100%."}
        </p>
      )}

      <MarkLegend />

      <div
        data-testid={
          isQualifier ? "atlas-qualifier-leading-rows" : "atlas-field-top-three"
        }
        className="divide-y divide-surface-border rounded-xl border border-surface-border bg-surface-deep"
      >
        {leadingRows.map((row) => {
          const rowVerdict = outcomeRowVerdict(row, isResolved);
          const rowRendered = renderedById.get(row.id);
          const rowLabel = boardOutcomeLabel(row.name, marketName);
          const rowOpening = !isMultiVenue
            ? readableOpeningProbability(row)
            : null;
          const rowRecorded =
            !isResolved && hasCurrentPrice(row) ? row.probability : null;
          const isSelected = row.id === activeOutcome?.id;
          const colorSlot = retainedSlots[String(row.id)] ?? 0;
          const rowColor =
            outcomeColors?.get(row.id) ??
            SERIES_COLORS[colorSlot % SERIES_COLORS.length];
          const isPinned = !topLeaderIds.has(row.id);

          return (
            <button
              key={row.id}
              type="button"
              aria-pressed={isSelected}
              data-testid="atlas-field-leader-row"
              data-outcome-id={row.id}
              data-color-slot={colorSlot}
              data-series-color={rowColor}
              onClick={() => handleChooseOutcome(row.id)}
              className={`flex w-full items-center justify-between gap-3 px-3.5 py-3 text-left transition-colors ${
                isSelected
                  ? "bg-surface-card"
                  : "hover:bg-surface-card/70"
              }`}
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    data-testid="atlas-field-leader-swatch"
                    className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: rowColor }}
                  />
                  <span className="truncate text-sm font-semibold text-text-primary">
                    {rowLabel}
                  </span>
                  {isPinned && (
                    <span
                      data-testid="atlas-field-pinned-badge"
                      className="shrink-0 rounded bg-surface-elevated px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-secondary"
                    >
                      Pinned
                    </span>
                  )}
                </div>
                <div className="mt-0.5 pl-4 text-xs tabular-nums">
                  {rowVerdict === "won" ? (
                    <span className="font-semibold text-accent-live">
                      {ATLAS_STATE_COPY.wonWithCheck}
                    </span>
                  ) : rowVerdict === "lost" ? (
                    <span className="font-semibold text-text-secondary">
                      {ATLAS_STATE_COPY.lostWithCross}
                    </span>
                  ) : rowRecorded == null ? (
                    <span className="text-text-secondary">
                      {ATLAS_STATE_COPY.noRecentPrice}
                    </span>
                  ) : (
                    <span className="font-bold text-text-primary">
                      {formatServerChance(rowRecorded, rowRendered?.current)}
                    </span>
                  )}
                </div>
              </div>

              <MovementRail
                name={rowLabel}
                opening={rowOpening}
                recorded={rowRecorded}
                renderedOpening={rowRendered?.opening}
                renderedCurrent={rowRendered?.current}
                color={rowColor}
              />
            </button>
          );
        })}
      </div>

      {remainingCount > 0 && (
        <button
          type="button"
          onClick={openSearchSheet}
          data-testid="atlas-field-more-button"
          className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-surface-border bg-surface-elevated px-3.5 py-2 text-xs font-semibold text-text-primary transition-colors hover:bg-surface-border"
        >
          <span>{remainingCount} more</span>
          <span aria-hidden="true">·</span>
          <span>Search all {outcomes.length} outcomes</span>
        </button>
      )}

      <p className="mt-2.5 text-xs text-text-secondary">
        {isQualifier
          ? "Each contender can qualify. These chances do not add to 100%."
          : "Full-field shares. Every outcome prints the server's number."}
      </p>

      {mounted &&
        sheetOpen &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            data-testid="atlas-field-sheet-backdrop"
            onClick={(e) => {
              if (e.target === e.currentTarget) closeSearchSheet();
            }}
            className="fixed inset-0 z-50 flex items-end justify-center bg-text-primary/30 p-0 min-[760px]:items-center min-[760px]:p-6"
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby={sheetTitleId}
              data-testid="atlas-field-sheet"
              className="max-h-[82vh] w-full overflow-y-auto rounded-t-2xl border border-surface-border bg-surface-card p-5 shadow-xl min-[760px]:max-w-[520px] min-[760px]:rounded-2xl min-[760px]:p-6"
            >
              <div
                aria-hidden="true"
                className="mx-auto mb-3 h-1 w-9 rounded-full bg-surface-border min-[760px]:hidden"
              />
              <div className="flex items-start justify-between gap-4 border-b border-surface-border pb-3.5">
                <div>
                  <h2
                    id={sheetTitleId}
                    className="text-base font-bold text-text-primary"
                  >
                    All {outcomes.length} outcomes
                  </h2>
                  <p className="mt-0.5 text-xs text-text-secondary">
                    {isQualifier
                      ? "Independent qualification chances · do not add to 100%"
                      : "Every supplied outcome with its server-fed chance"}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closeSearchSheet}
                  aria-label="Close outcomes list"
                  data-testid="atlas-field-sheet-close"
                  className="shrink-0 rounded-lg border border-surface-border bg-surface-elevated px-2.5 py-1 text-xs font-medium text-text-secondary hover:text-text-primary"
                >
                  Close
                </button>
              </div>

              <div className="my-3">
                <label className="block text-xs font-medium text-text-secondary">
                  <span className="sr-only">Find an outcome</span>
                  <input
                    type="search"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Find an outcome…"
                    aria-label="Find an outcome"
                    data-testid="atlas-field-search-input"
                    className="w-full rounded-lg border border-surface-border bg-surface-deep px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-text-primary focus:outline-none"
                  />
                </label>
              </div>

              <div className="divide-y divide-surface-border">
                {filteredSheetRows.map((row) => {
                  const rowVerdict = outcomeRowVerdict(row, isResolved);
                  const rowRendered = renderedById.get(row.id);
                  const rowLabel = boardOutcomeLabel(row.name, marketName);
                  const rowRecorded =
                    !isResolved && hasCurrentPrice(row)
                      ? row.probability
                      : null;
                  const isSelected = row.id === activeOutcome?.id;

                  return (
                    <button
                      key={row.id}
                      type="button"
                      aria-pressed={isSelected}
                      data-testid="atlas-field-sheet-row"
                      onClick={() => {
                        handleChooseOutcome(row.id);
                        closeSearchSheet();
                      }}
                      className={`flex w-full items-center justify-between gap-3 py-2.5 text-left text-sm transition-colors ${
                        isSelected
                          ? "font-semibold text-accent-brand"
                          : "text-text-primary hover:bg-surface-elevated/50"
                      }`}
                    >
                      <span className="min-w-0 flex-1 break-words">
                        {rowLabel}
                      </span>
                      <strong className="shrink-0 font-semibold tabular-nums">
                        {rowVerdict === "won"
                          ? ATLAS_STATE_COPY.wonWithCheck
                          : rowVerdict === "lost"
                            ? ATLAS_STATE_COPY.lostWithCross
                            : rowRecorded == null
                              ? ATLAS_STATE_COPY.noRecentPrice
                              : formatServerChance(
                                  rowRecorded,
                                  rowRendered?.current,
                                )}
                      </strong>
                    </button>
                  );
                })}
                {filteredSheetRows.length === 0 && (
                  <p
                    data-testid="atlas-field-no-matches"
                    className="py-4 text-center text-xs text-text-secondary"
                  >
                    No matching outcomes.
                  </p>
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </section>
  );
}
