"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import useSWR from "swr";
import { EvolutionChart } from "@/components/EvolutionChart";
import { EvolutionLeaderboard } from "@/components/EvolutionLeaderboard";
import { fetchFuturesHistory } from "@/lib/api";

type TimeRange = "full" | "7d" | "24h" | "today";

export interface PositionOption {
  key: string;   // "win", "top_5", "top_10", "top_20"
  label: string;  // "Win", "Top 5", "Top 10", "Top 20"
  marketId: number;
}

interface EvolutionViewProps {
  marketId: number;
  marketName?: string;
  defaultTopN?: number;
  hours?: number;
  className?: string;
  positionOptions?: PositionOption[];
  /** Label for sidebar — "Teams", "Players", etc. Defaults to "Players" */
  entityLabel?: string;
}

export function EvolutionView({
  marketId,
  marketName,
  defaultTopN = 8,
  hours = 168,
  className,
  positionOptions,
  entityLabel = "Players",
}: EvolutionViewProps) {
  const [highlightedOutcomeId, setHighlightedOutcomeId] = useState<number | null>(null);
  const [selectedOutcomeIds, setSelectedOutcomeIds] = useState<Set<number> | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [timeRange, setTimeRange] = useState<TimeRange>("7d");
  const [selectedPosition, setSelectedPosition] = useState<string>(
    positionOptions?.[positionOptions.length - 1]?.key || "win"
  );

  // Determine active market ID from position selection
  const activeMarketId = useMemo(() => {
    if (positionOptions) {
      const pos = positionOptions.find((p) => p.key === selectedPosition);
      if (pos) return pos.marketId;
    }
    return marketId;
  }, [positionOptions, selectedPosition, marketId]);

  // Reset selected outcomes when position changes
  useEffect(() => {
    setSelectedOutcomeIds(null);
  }, [activeMarketId]);

  // ESC to exit fullscreen
  useEffect(() => {
    if (!isFullscreen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsFullscreen(false);
    };
    document.addEventListener("keydown", handler);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = "";
    };
  }, [isFullscreen]);

  // Map time range to fetch hours:
  // "full" = full season (~6 months), "7d"/"24h"/"today" all use the shorter window
  // but filter client-side via EvolutionChart's timeRange prop.
  const fetchHours = timeRange === "full" ? 4320 : Math.max(hours, 168);

  // Fetch history data — always use the same key for non-full ranges
  // so switching between 7d/24h/today doesn't trigger a new fetch
  const { data, error, isLoading } = useSWR(
    `futures-evolution-${activeMarketId}-${timeRange === "full" ? "full" : "week"}`,
    () => fetchFuturesHistory(activeMarketId, fetchHours, undefined, 50),
    { refreshInterval: 60_000, keepPreviousData: true }
  );

  // Auto-select top N outcomes on first load
  const effectiveSelectedIds = useMemo(() => {
    if (selectedOutcomeIds !== null) return selectedOutcomeIds;
    if (!data?.outcomes) return new Set<number>();
    const sorted = [...data.outcomes].sort((a, b) => {
      const aLast = a.history[a.history.length - 1]?.probability ?? 0;
      const bLast = b.history[b.history.length - 1]?.probability ?? 0;
      return bLast - aLast;
    });
    const active = sorted.filter((o) => !o.eliminated);
    const selected = active.slice(0, defaultTopN).map((o) => o.outcome_id);
    return new Set(selected);
  }, [data, selectedOutcomeIds, defaultTopN]);

  const handleToggleOutcome = useCallback(
    (outcomeId: number) => {
      setSelectedOutcomeIds((prev) => {
        const current = prev ?? new Set(effectiveSelectedIds);
        const next = new Set(current);
        next.delete(outcomeId);
        return next;
      });
    },
    [effectiveSelectedIds]
  );

  const handleAddOutcome = useCallback(
    (outcomeId: number) => {
      setSelectedOutcomeIds((prev) => {
        const current = prev ?? new Set(effectiveSelectedIds);
        const next = new Set(current);
        next.add(outcomeId);
        return next;
      });
    },
    [effectiveSelectedIds]
  );

  // Current position label for footer
  const activePositionLabel =
    positionOptions?.find((p) => p.key === selectedPosition)?.label || "Win";

  const cardClasses = isFullscreen
    ? "fixed inset-0 z-[9999] bg-white flex flex-col"
    : "bg-white border border-gray-200 rounded-[10px] overflow-hidden";

  // Show the card shell immediately with a loading chart area inside,
  // so controls are visible and the layout doesn't jump.
  const chartContent = isLoading ? (
    <div className="flex-1 min-w-0 px-3 sm:px-4 pt-2 pb-1 flex items-center justify-center" style={{ minHeight: isFullscreen ? 600 : 300 }}>
      <div className="flex flex-col items-center gap-2 text-gray-400">
        <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span className="text-xs">Loading odds history...</span>
      </div>
    </div>
  ) : (!data || error || data.outcomes.length === 0) ? (
    <div className="flex-1 min-w-0 px-3 sm:px-4 pt-2 pb-1 flex items-center justify-center" style={{ minHeight: 200 }}>
      <span className="text-sm text-gray-400">No history data available</span>
    </div>
  ) : (
    <>
      <div className={`flex-1 min-w-0 px-3 sm:px-4 pt-2 pb-1 ${isFullscreen ? "min-h-0" : ""}`}>
        <EvolutionChart
          historyData={data.outcomes}
          selectedOutcomeIds={effectiveSelectedIds}
          highlightedOutcomeId={highlightedOutcomeId}
          onHoverOutcome={setHighlightedOutcomeId}
          roundBoundaries={data.round_boundaries}
          height={isFullscreen ? 600 : 300}
          className=""
          timeRange={timeRange}
        />
      </div>
      <div className="w-full sm:w-[180px] sm:flex-shrink-0 sm:border-l border-t sm:border-t-0 border-gray-100 px-3 py-2 sm:overflow-y-auto">
        <EvolutionLeaderboard
          historyData={data.outcomes}
          selectedOutcomeIds={effectiveSelectedIds}
          onToggleOutcome={handleToggleOutcome}
          onAddOutcome={handleAddOutcome}
          highlightedOutcomeId={highlightedOutcomeId}
          onHoverOutcome={setHighlightedOutcomeId}
          leaderboard={data.leaderboard}
          entityLabel={entityLabel}
        />
      </div>
    </>
  );

  return (
    <div className={className}>
      <div className={cardClasses}>
        {/* ── Header: controls + expand ── */}
        <div className="px-3 sm:px-4 py-2.5 border-b border-gray-100 flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3 flex-wrap">
            {/* Time Range control group */}
            <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
              Time Range
            </span>
            <div className="flex border border-gray-200 rounded-md overflow-hidden">
              {(["full", "7d", "24h", "today"] as TimeRange[]).map((range) => (
                <button
                  key={range}
                  onClick={() => setTimeRange(range)}
                  className={`px-3 py-1 text-[11.5px] font-medium border-r border-gray-100 last:border-r-0 transition-colors ${
                    timeRange === range
                      ? "bg-gray-900 text-white font-semibold"
                      : "text-gray-500 hover:bg-gray-50"
                  }`}
                >
                  {range === "full"
                    ? "Season"
                    : range === "7d"
                      ? "7 Days"
                      : range === "24h"
                        ? "24 Hours"
                        : "Today"}
                </button>
              ))}
            </div>

            {/* Position control group — only when multiple markets available */}
            {positionOptions && positionOptions.length > 1 && (
              <>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                  Stage
                </span>
                <div className="flex border border-gray-200 rounded-md overflow-hidden">
                  {positionOptions.map((pos) => (
                    <button
                      key={pos.key}
                      onClick={() => setSelectedPosition(pos.key)}
                      className={`px-3 py-1 text-[11.5px] font-medium border-r border-gray-100 last:border-r-0 transition-colors ${
                        selectedPosition === pos.key
                          ? "bg-gray-900 text-white font-semibold"
                          : "text-gray-500 hover:bg-gray-50"
                      }`}
                    >
                      {pos.label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Expand/collapse button */}
          <button
            onClick={() => setIsFullscreen((f) => !f)}
            className="w-8 h-8 rounded-md border border-gray-200 bg-white hover:bg-gray-50 hover:border-gray-300 flex items-center justify-center transition-colors flex-shrink-0"
            title={isFullscreen ? "Exit fullscreen" : "Expand"}
          >
            {isFullscreen ? (
              <svg className="w-4 h-4 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path d="M4 14h6v6m10-10h-6V4m0 16l6-6M14 4l-6 6" />
              </svg>
            ) : (
              <svg className="w-4 h-4 text-gray-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3" />
              </svg>
            )}
          </button>
        </div>

        {/* ── Main: chart + sidebar ── */}
        <div className={`flex flex-col sm:flex-row ${isFullscreen ? "flex-1 min-h-0" : ""}`}>
          {chartContent}
        </div>

        {/* ── Footer ── */}
        <div className="px-3 sm:px-4 py-1.5 border-t border-gray-100 bg-gray-50/80 flex justify-between text-[11px] text-gray-400">
          <span>{marketName || "Win Probability"} — {activePositionLabel}</span>
          <span>
            {effectiveSelectedIds.size} of {data?.outcomes.length ?? 0}
            {selectedOutcomeIds !== null && (
              <button
                onClick={() => setSelectedOutcomeIds(null)}
                className="ml-2 text-gray-400 hover:text-blue-600 transition-colors"
              >
                Reset
              </button>
            )}
          </span>
        </div>
      </div>
    </div>
  );
}
