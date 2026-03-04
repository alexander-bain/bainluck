"use client";

import { useState, useMemo, useCallback } from "react";
import useSWR from "swr";
import { EvolutionChart } from "@/components/EvolutionChart";
import { EvolutionLeaderboard } from "@/components/EvolutionLeaderboard";
import { fetchFuturesHistory } from "@/lib/api";
import type { FuturesHistoryResponse } from "@/lib/types";

interface EvolutionViewProps {
  /** Futures market ID to display */
  marketId: number;
  /** Market name for header */
  marketName?: string;
  /** Number of outcomes to show by default */
  defaultTopN?: number;
  /** Hours of history to fetch */
  hours?: number;
  /** Optional class name */
  className?: string;
}

export function EvolutionView({
  marketId,
  marketName,
  defaultTopN = 8,
  hours = 168,
  className,
}: EvolutionViewProps) {
  const [highlightedOutcomeId, setHighlightedOutcomeId] = useState<number | null>(null);
  const [selectedOutcomeIds, setSelectedOutcomeIds] = useState<Set<number> | null>(null);

  // Fetch history data
  const { data, error, isLoading } = useSWR(
    `futures-evolution-${marketId}-${hours}`,
    () => fetchFuturesHistory(marketId, hours),
    { refreshInterval: 60_000 } // Refresh every minute
  );

  // Auto-select top N outcomes on first load
  const effectiveSelectedIds = useMemo(() => {
    if (selectedOutcomeIds !== null) return selectedOutcomeIds;
    if (!data?.outcomes) return new Set<number>();
    // Sort by latest probability (descending) and take top N
    const sorted = [...data.outcomes].sort((a, b) => {
      const aLast = a.history[a.history.length - 1]?.probability ?? 0;
      const bLast = b.history[b.history.length - 1]?.probability ?? 0;
      return bLast - aLast;
    });
    return new Set(sorted.slice(0, defaultTopN).map((o) => o.outcome_id));
  }, [data, selectedOutcomeIds, defaultTopN]);

  const handleToggleOutcome = useCallback(
    (outcomeId: number) => {
      setSelectedOutcomeIds((prev) => {
        const current = prev ?? new Set(effectiveSelectedIds);
        const next = new Set(current);
        if (next.has(outcomeId)) {
          next.delete(outcomeId);
        } else {
          next.add(outcomeId);
        }
        return next;
      });
    },
    [effectiveSelectedIds]
  );

  if (isLoading) {
    return (
      <div className={`animate-pulse ${className || ""}`}>
        <div className="h-8 bg-gray-800 rounded w-48 mb-4" />
        <div className="h-[400px] bg-gray-800/50 rounded-lg" />
      </div>
    );
  }

  if (error || !data || data.outcomes.length === 0) {
    return (
      <div className={`text-gray-500 text-sm ${className || ""}`}>
        {error ? "Failed to load chart data" : "No history data available"}
      </div>
    );
  }

  return (
    <div className={className}>
      {marketName && (
        <h3 className="text-lg font-semibold text-white mb-3">{marketName}</h3>
      )}

      {/* Responsive layout: stacked on mobile, side-by-side on desktop */}
      <div className="flex flex-col lg:flex-row gap-4">
        {/* Chart (takes most of the space) */}
        <div className="flex-1 min-w-0">
          <EvolutionChart
            historyData={data.outcomes}
            selectedOutcomeIds={effectiveSelectedIds}
            highlightedOutcomeId={highlightedOutcomeId}
            onHoverOutcome={setHighlightedOutcomeId}
            roundBoundaries={data.round_boundaries}
            height={400}
          />
        </div>

        {/* Leaderboard sidebar */}
        <div className="lg:w-[360px] lg:flex-shrink-0">
          <EvolutionLeaderboard
            historyData={data.outcomes}
            selectedOutcomeIds={effectiveSelectedIds}
            onToggleOutcome={handleToggleOutcome}
            highlightedOutcomeId={highlightedOutcomeId}
            onHoverOutcome={setHighlightedOutcomeId}
            leaderboard={data.leaderboard}
          />
        </div>
      </div>

      {/* Participant count */}
      <div className="mt-2 text-xs text-gray-500">
        Showing {effectiveSelectedIds.size} of {data.outcomes.length} participants
        {effectiveSelectedIds.size < data.outcomes.length && (
          <button
            onClick={() =>
              setSelectedOutcomeIds(
                new Set(data.outcomes.map((o) => o.outcome_id))
              )
            }
            className="ml-2 text-blue-400 hover:text-blue-300"
          >
            Show all
          </button>
        )}
        {selectedOutcomeIds !== null && (
          <button
            onClick={() => setSelectedOutcomeIds(null)}
            className="ml-2 text-gray-400 hover:text-gray-300"
          >
            Reset
          </button>
        )}
      </div>
    </div>
  );
}
