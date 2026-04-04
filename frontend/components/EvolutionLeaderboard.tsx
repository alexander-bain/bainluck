"use client";

import { useMemo } from "react";
import type {
  FuturesOutcomeHistory,
  DataGolfLeaderboardEntry,
} from "@/lib/types";

/**
 * Color palette matching EvolutionChart — kept in sync for dot colors.
 */
const EVOLUTION_COLORS = [
  "#c41e3a", "#005eb8", "#1d4ed8", "#0e7490", "#b91c1c",
  "#0369a1", "#92400e", "#4338ca", "#be185d", "#065f46",
];

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
      color: o.eliminated ? "#b5b9c3" : EVOLUTION_COLORS[i % EVOLUTION_COLORS.length],
      eliminated: o.eliminated,
    }));
  }, [historyData, selectedOutcomeIds]);

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
      <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-1.5">
        {entityLabel}
      </div>

      {/* Add player dropdown */}
      {unselected.length > 0 && (
        <select
          className="w-full px-2 py-1.5 border border-gray-200 rounded-[5px] text-[11.5px] text-gray-700 bg-white cursor-pointer outline-none mb-1.5 focus:border-blue-500 focus:ring-1 focus:ring-blue-100"
          value=""
          onChange={(e) => {
            const id = parseInt(e.target.value, 10);
            if (!isNaN(id)) onAddOutcome(id);
          }}
        >
          <option value="">Find {entityLabel.toLowerCase().replace(/s$/, "")}...</option>
          {unselected.map((o) => (
            <option key={o.outcome_id} value={o.outcome_id}>
              {shortName(o.name)} — {((o.history[o.history.length - 1]?.probability ?? 0) * 100).toFixed(1)}%
            </option>
          ))}
        </select>
      )}

      {/* Player list */}
      <div className="flex flex-col overflow-y-auto">
        {selectedRows.map((row) => {
          const isHighlighted = highlightedOutcomeId === row.outcomeId;
          return (
            <div
              key={row.outcomeId}
              className={`flex items-center gap-1.5 px-1 py-[4px] rounded text-xs cursor-default transition-colors ${
                isHighlighted ? "bg-gray-100" : "hover:bg-gray-50"
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
                row.eliminated ? "text-gray-400 line-through" : "text-gray-900"
              }`}>
                {row.name}
              </span>

              {/* Probability */}
              <span className="text-[11px] text-gray-600 tabular-nums flex-shrink-0">
                {(row.currentProbability * 100).toFixed(1)}%
              </span>

              {/* Remove button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleOutcome(row.outcomeId);
                }}
                className="text-gray-300 hover:text-red-500 hover:bg-red-50 rounded px-0.5 text-xs leading-none transition-colors flex-shrink-0"
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

/** Extract short display name — last word for long names, full for short */
function shortName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  if (parts.length <= 2) return fullName;
  // For 3+ word names (e.g., "Oklahoma City Thunder"), use last word
  return parts[parts.length - 1];
}
