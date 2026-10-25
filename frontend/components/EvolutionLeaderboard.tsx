"use client";

import { useMemo, useState, useRef, useEffect } from "react";
import type {
  FuturesOutcomeHistory,
  DataGolfLeaderboardEntry,
} from "@/lib/types";
import {
  SERIES_COLORS,
  ELIMINATED_SERIES_COLOR,
} from "@/lib/seriesColors";
import { splitSettlementPoints, type SettlementResult } from "@/lib/chartSettlementPoints";
import { latestOutcomeProb, outcomesByLatestProb } from "@/lib/eventConceptDisplay";
import { LOST_LEGEND_WORD_CLASS } from "@/components/FuturesChart";
import { SettledMark } from "@/components/SettledOutcomeMark";

/**
 * Fallback dot palette — the canonical shared series palette (L2-157). When
 * EvolutionView supplies `outcomeColors` (L2-149) the dots use that shared map so
 * they match the FuturesChart lines exactly; this registry palette only applies
 * when no map is passed (and is the same one EvolutionView builds its map from).
 */
const EVOLUTION_COLORS = SERIES_COLORS;

interface EvolutionLeaderboardProps {
  historyData: FuturesOutcomeHistory[];
  selectedOutcomeIds: Set<number>;
  onToggleOutcome: (outcomeId: number) => void;
  onAddOutcome: (outcomeId: number) => void;
  highlightedOutcomeId?: number | null;
  onHoverOutcome?: (outcomeId: number | null) => void;
  leaderboard?: DataGolfLeaderboardEntry[] | null;
  /** Label for the sidebar header and search placeholder */
  entityLabel?: string;
  /** L2-149: shared color map keyed by outcome_id. When supplied, the sidebar
   *  dots use exactly the colors the chart draws (EvolutionView passes the same
   *  map to FuturesChart), so the leaderboard and the lines never drift. Falls
   *  back to the local index palette when absent. */
  outcomeColors?: Map<number, string>;
  className?: string;
}

interface SidebarRow {
  outcomeId: number;
  name: string;
  /** Last REAL reading; null when the leg has none. Never a settlement point. */
  currentProbability: number | null;
  currentPriceAvailable?: boolean;
  /** The leg's served grade, when its history ends in a settlement point. */
  result?: SettlementResult;
  color: string;
  eliminated?: boolean;
}

/** The leg's last real reading, or null — a settlement point is skipped and an
 *  empty history is not a 0%. */
function lastReading(o: FuturesOutcomeHistory): number | null {
  const p = latestOutcomeProb(o);
  return p < 0 ? null : p;
}

/**
 * #10955 (360): what the sidebar prints beside a name. EvolutionView draws its
 * chart with no legend, so this column IS the legend, and it reads results in
 * the chart legend's own vocabulary:
 *
 * - a graded leg shows its RESULT ("Won" / "Lost"), never the settlement point's
 *   1 or 0 dressed up as a latest chance. A settlement value that is neither 1
 *   nor 0 says a result exists that the chart will not name: "Settled", no word
 *   for who won and no percent.
 * - an ungraded leg shows its last real reading — a genuinely observed 0% or
 *   100% is a price and prints as one.
 * - an ungraded leg with no reading prints a dash, not "0.0%".
 *
 * The result outranks "Unavailable now": a settled market has no current price
 * because it is settled.
 */
function Reading({
  result,
  probability,
  currentPriceAvailable,
}: {
  result?: SettlementResult;
  probability: number | null;
  currentPriceAvailable?: boolean;
}) {
  if (result === "won" || result === "lost") {
    return (
      <span
        data-testid="evolution-leaderboard-result"
        data-result={result}
        className={result === "lost" ? LOST_LEGEND_WORD_CLASS : undefined}
      >
        <SettledMark won={result === "won"} />
      </span>
    );
  }
  if (result === "recorded") {
    return (
      <span data-testid="evolution-leaderboard-result" data-result={result} title="Result recorded">
        Settled
      </span>
    );
  }
  if (currentPriceAvailable === false) return <>Unavailable now</>;
  if (probability === null) return <span title="No price recorded">—</span>;
  return <>{`${(probability * 100).toFixed(1)}%`}</>;
}

export function EvolutionLeaderboard({
  historyData,
  selectedOutcomeIds,
  onToggleOutcome,
  onAddOutcome,
  highlightedOutcomeId,
  onHoverOutcome,
  entityLabel = "Players",
  outcomeColors,
  className,
}: EvolutionLeaderboardProps) {
  // #10955 (360): each leg's served grade. Read from the full history the parent
  // passes (never windowed), so a result does not come and go with the range.
  const results = useMemo(() => splitSettlementPoints(historyData).results, [historyData]);

  // Build sidebar rows: only show selected outcomes. #10955: winner first, then
  // last real reading — the order EvolutionView assigns colors in.
  const selectedRows = useMemo(() => {
    const sorted = outcomesByLatestProb(
      historyData.filter((o) => selectedOutcomeIds.has(o.outcome_id)),
    );
    return sorted.map((o, i): SidebarRow => ({
      outcomeId: o.outcome_id,
      name: shortName(o.name),
      currentPriceAvailable: o.current_price_available,
      currentProbability: lastReading(o),
      result: results.get(o.outcome_id),
      // L2-149: prefer the shared map so a dot matches its line exactly; else
      // fall back to the local eliminated-grey / index palette.
      color:
        outcomeColors?.get(o.outcome_id) ??
        (o.eliminated ? ELIMINATED_SERIES_COLOR : EVOLUTION_COLORS[i % EVOLUTION_COLORS.length]),
      eliminated: o.eliminated,
    }));
  }, [historyData, selectedOutcomeIds, outcomeColors, results]);

  // Build unselected outcomes for the dropdown. A leg graded lost stays
  // addable — a result is not an elimination.
  const unselected = useMemo(() => {
    return outcomesByLatestProb(
      historyData.filter((o) => !selectedOutcomeIds.has(o.outcome_id) && !o.eliminated),
    );
  }, [historyData, selectedOutcomeIds]);

  return (
    <div className={`flex flex-col ${className || ""}`}>
      {/* Title */}
      <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted mb-1.5">
        {entityLabel}
      </div>

      {/* Searchable player picker */}
      {unselected.length > 0 && (
        <PlayerSearch
          unselected={unselected}
          results={results}
          onAddOutcome={onAddOutcome}
          entityLabel={entityLabel}
        />
      )}

      {/* Player list */}
      <div className="flex flex-col overflow-y-auto">
        {selectedRows.map((row) => {
          const isHighlighted = highlightedOutcomeId === row.outcomeId;
          return (
            <div
              key={row.outcomeId}
              className={`flex items-center gap-1.5 px-1 py-[4px] rounded text-xs cursor-default transition-colors ${
                isHighlighted ? "bg-surface-secondary" : "hover:bg-surface-secondary"
              }`}
              onMouseEnter={() => onHoverOutcome?.(row.outcomeId)}
              onMouseLeave={() => onHoverOutcome?.(null)}
            >
              {/* Color dot */}
              <span
                className="w-[7px] h-[7px] rounded-full flex-shrink-0"
                style={{ backgroundColor: row.color }}
              />

              {/* Name */}
              <span className={`flex-1 min-w-0 font-medium truncate ${
                row.eliminated ? "text-text-muted line-through" : "text-text-primary"
              }`}>
                {row.name}
              </span>

              {/* Probability */}
              <span className="text-[11px] text-text-secondary tabular-nums flex-shrink-0">
                <Reading
                  result={row.result}
                  probability={row.currentProbability}
                  currentPriceAvailable={row.currentPriceAvailable}
                />
              </span>

              {/* Remove button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleOutcome(row.outcomeId);
                }}
                className="text-text-muted hover:text-red-500 hover:bg-red-50 rounded px-0.5 text-xs leading-none transition-colors flex-shrink-0"
                title="Remove"
              >
                &times;
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Searchable player/team picker — replaces native <select> */
function PlayerSearch({
  unselected,
  results,
  onAddOutcome,
  entityLabel,
}: {
  unselected: FuturesOutcomeHistory[];
  results: Map<number, SettlementResult>;
  onAddOutcome: (outcomeId: number) => void;
  entityLabel: string;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = useMemo(() => {
    if (!query.trim()) return unselected.slice(0, 20);
    const q = query.toLowerCase();
    return unselected.filter((o) => o.name.toLowerCase().includes(q)).slice(0, 20);
  }, [unselected, query]);

  const placeholder = `Find ${entityLabel.toLowerCase().replace(/s$/, "")}...`;

  return (
    <div ref={ref} className="relative mb-1.5">
      <input
        type="text"
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
        className="w-full px-2 py-1.5 border border-surface-border rounded-[5px] text-[11.5px] text-text-secondary bg-surface-card outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-100"
      />
      {open && filtered.length > 0 && (
        <div className="absolute z-50 w-full mt-0.5 bg-surface-card border border-surface-border rounded-md shadow-lg max-h-48 overflow-y-auto">
          {filtered.map((o) => (
            <button
              key={o.outcome_id}
              onClick={() => {
                onAddOutcome(o.outcome_id);
                setQuery("");
                setOpen(false);
              }}
              className="w-full text-left px-2 py-1.5 text-[11.5px] text-text-secondary hover:bg-surface-secondary flex justify-between"
            >
              <span className="truncate">{shortName(o.name)}</span>
              <span className="text-text-muted tabular-nums ml-1 flex-shrink-0">
                <Reading
                  result={results.get(o.outcome_id)}
                  probability={lastReading(o)}
                  currentPriceAvailable={o.current_price_available}
                />
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * The shortest label a last-word abbreviation is allowed to produce.
 *
 * UX-1052 item 7. Alex, on the MLB league page's odds-movement chart: *"'AL/NL
 * Champ' tab shows a team called 'D'."* He was reading this list. Kalshi stores
 * its MLB team outcomes as city-plus-initial — `"Los Angeles D"`, `"New York
 * Y"`, `"Chicago C"` (gotcha #16) — and `"Los Angeles D"` is three words, so
 * the last-word rule below handed the reader the single letter `D` and called
 * it a team.
 *
 * The abbreviated NAMES are a data defect and belong to the identity lane; what
 * this component owns is not turning one into a label that names nothing. Three
 * characters is the floor because every real last word clears it ("Rays",
 * "Cardinals", "Thunder") and no initial or league suffix does ("D", "Y",
 * "FC") — and when a name cannot be shortened honestly, the full string is
 * still true.
 */
const MIN_SHORT_NAME_CHARS = 3;

/** Extract short display name — last word for long names, full for short. */
function shortName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  if (parts.length <= 2) return fullName;
  // For 3+ word names (e.g., "Oklahoma City Thunder"), use last word
  const last = parts[parts.length - 1];
  // …unless the last word is an initial or a bare suffix, in which case it is
  // not a shorter name for anything. Keep the whole string.
  if (last.replace(/[^\p{L}\p{N}]/gu, "").length < MIN_SHORT_NAME_CHARS) {
    return fullName;
  }
  return last;
}
