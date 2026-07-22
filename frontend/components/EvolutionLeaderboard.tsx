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
  currentProbability: number;
  color: string;
  eliminated?: boolean;
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
  // Build sidebar rows: only show selected outcomes
  const selectedRows = useMemo(() => {
    const sorted = historyData
      .filter((o) => selectedOutcomeIds.has(o.outcome_id))
      .sort((a, b) => {
        const aLast = a.history[a.history.length - 1]?.probability ?? 0;
        const bLast = b.history[b.history.length - 1]?.probability ?? 0;
        return bLast - aLast;
      });
    return sorted.map((o, i): SidebarRow => ({
      outcomeId: o.outcome_id,
      name: shortName(o.name),
      currentProbability: o.history[o.history.length - 1]?.probability ?? 0,
      // L2-149: prefer the shared map so a dot matches its line exactly; else
      // fall back to the local eliminated-grey / index palette.
      color:
        outcomeColors?.get(o.outcome_id) ??
        (o.eliminated ? ELIMINATED_SERIES_COLOR : EVOLUTION_COLORS[i % EVOLUTION_COLORS.length]),
      eliminated: o.eliminated,
    }));
  }, [historyData, selectedOutcomeIds, outcomeColors]);

  // Build unselected outcomes for the dropdown
  const unselected = useMemo(() => {
    return historyData
      .filter((o) => !selectedOutcomeIds.has(o.outcome_id) && !o.eliminated)
      .sort((a, b) => {
        const aLast = a.history[a.history.length - 1]?.probability ?? 0;
        const bLast = b.history[b.history.length - 1]?.probability ?? 0;
        return bLast - aLast;
      });
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
                {(row.currentProbability * 100).toFixed(1)}%
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
  onAddOutcome,
  entityLabel,
}: {
  unselected: FuturesOutcomeHistory[];
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
                {((o.history[o.history.length - 1]?.probability ?? 0) * 100).toFixed(1)}%
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Extract short display name — last word for long names, full for short */
function shortName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  if (parts.length <= 2) return fullName;
  // For 3+ word names (e.g., "Oklahoma City Thunder"), use last word
  return parts[parts.length - 1];
}
