"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import useSWR from "swr";
import { EvolutionChart } from "@/components/EvolutionChart";
import { EvolutionLeaderboard } from "@/components/EvolutionLeaderboard";
import { fetchFuturesHistory, fetchMultiMarketHistory } from "@/lib/api";

type TimeRange = "full" | "tournament" | "7d" | "24h" | "today";

export interface PositionOption {
  key: string;   // "win", "top_5", "top_10", "top_20"
  label: string;  // "Win", "Top 5", "Top 10", "Top 20"
  marketId: number;
  /** All market IDs for this stage (cross-source aggregation) */
  marketIds?: number[];
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
  /** Tournament start date (ISO) — enables "Tournament" range with day boundaries */
  tournamentStart?: string | null;
  /** Tournament end date (ISO) */
  tournamentEnd?: string | null;
}

export function EvolutionView({
  marketId,
  marketName,
  defaultTopN = 8,
  hours = 168,
  className,
  positionOptions,
  entityLabel = "Players",
  tournamentStart,
  tournamentEnd,
}: EvolutionViewProps) {
  // Tournament mode: enabled once the event has started, useful during the
  // event when the 7-day view becomes cluttered. Replaces "7d" in the picker.
  const hasTournament = !!tournamentStart;
  const tournamentStarted = useMemo(() => {
    if (!tournamentStart) return false;
    try { return new Date(tournamentStart).getTime() <= Date.now(); }
    catch { return false; }
  }, [tournamentStart]);

  const [highlightedOutcomeId, setHighlightedOutcomeId] = useState<number | null>(null);
  const [selectedOutcomeIds, setSelectedOutcomeIds] = useState<Set<number> | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showCombinedProbability, setShowCombinedProbability] = useState(false);
  const [timeRange, setTimeRange] = useState<TimeRange>(
    tournamentStarted ? "tournament" : "7d"
  );

  // If tournamentStart arrives after initial render (async data), switch to tournament view
  useEffect(() => {
    if (tournamentStarted && timeRange === "7d") {
      setTimeRange("tournament");
    }
  }, [tournamentStarted]); // eslint-disable-line react-hooks/exhaustive-deps
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

  // All source market IDs for the active position (cross-source aggregation).
  // Falls back to the single active market ID when a position has no explicit
  // marketIds array. Always non-empty so downstream .length / .join are safe.
  const activeMarketIds = useMemo(() => {
    if (positionOptions) {
      const pos = positionOptions.find((p) => p.key === selectedPosition);
      if (pos?.marketIds && pos.marketIds.length > 0) return pos.marketIds;
    }
    return [activeMarketId];
  }, [positionOptions, selectedPosition, activeMarketId]);

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
  // "full" = full season (~6 months), "tournament" covers the event window plus a
  // small lead-in, all shorter ranges share a 1-week fetch that's filtered
  // client-side via EvolutionChart's timeRange prop.
  const tournamentFetchHours = useMemo(() => {
    if (!tournamentStart) return 168;
    try {
      const startMs = new Date(tournamentStart).getTime();
      const leadInMs = 24 * 60 * 60 * 1000; // 1 day lead-in before start
      const elapsedHrs = Math.max(0, (Date.now() - startMs + leadInMs) / 3_600_000);
      // Cap at ~2 weeks so we don't pull excessive data for long stale events
      return Math.min(336, Math.max(168, Math.ceil(elapsedHrs)));
    } catch {
      return 168;
    }
  }, [tournamentStart]);

  const fetchHours = timeRange === "full"
    ? 4320
    : timeRange === "tournament"
      ? tournamentFetchHours
      : Math.max(hours, 168);

  // Fetch history data. "tournament" gets its own cache key when it fetches a
  // different window than the shorter ranges.
  const fetchKey = timeRange === "full"
    ? "full"
    : timeRange === "tournament"
      ? `tournament-${tournamentFetchHours}`
      : "week";

  // Use multi-market aggregation when multiple source market IDs are available.
  // Cache key includes all IDs so switching positions invalidates correctly.
  const cacheKey = activeMarketIds.length > 1
    ? `futures-evolution-multi-${activeMarketIds.join(",")}-${fetchKey}`
    : `futures-evolution-${activeMarketId}-${fetchKey}`;

  const { data, error, isLoading } = useSWR(
    cacheKey,
    () => activeMarketIds.length > 1
      ? fetchMultiMarketHistory(activeMarketIds, fetchHours, 50)
      : fetchFuturesHistory(activeMarketId, fetchHours, undefined, 50),
    { refreshInterval: 60_000, keepPreviousData: true }
  );

  // Derive day-boundary markers for the tournament range: start of each day
  // from tournament start through min(end, now). Uses UTC dates since the API
  // returns UTC timestamps (e.g., 2026-04-09T00:00:00+00:00).
  const tournamentDayBoundaries = useMemo(() => {
    if (!tournamentStart) return null;
    try {
      const start = new Date(tournamentStart);
      // Use UTC midnight to align with API dates
      start.setUTCHours(0, 0, 0, 0);
      const endMs = tournamentEnd
        ? Math.min(new Date(tournamentEnd).getTime() + 86_400_000, Date.now())
        : Date.now();
      const boundaries: { timestamp: string; label: string }[] = [];
      const dayMs = 86_400_000;
      let t = start.getTime();
      let dayIdx = 1;
      while (t <= endMs && dayIdx <= 5) {
        boundaries.push({
          timestamp: new Date(t).toISOString(),
          label: `R${dayIdx}`,
        });
        t += dayMs;
        dayIdx += 1;
      }
      return boundaries;
    } catch {
      return null;
    }
  }, [tournamentStart, tournamentEnd]);

  // Show tournament round markers on all time ranges when available
  const effectiveBoundaries = tournamentDayBoundaries
    ? tournamentDayBoundaries
    : data?.round_boundaries ?? null;

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
    ? "fixed inset-0 z-[9999] bg-surface-card flex flex-col"
    : "bg-surface-card border border-surface-border rounded-[10px] overflow-hidden";

  // Show the card shell immediately with a loading chart area inside,
  // so controls are visible and the layout doesn't jump.
  const chartContent = isLoading ? (
    <div className="flex-1 min-w-0 px-3 sm:px-4 pt-2 pb-1 flex items-center justify-center" style={{ minHeight: isFullscreen ? 600 : 300 }}>
      <div className="flex flex-col items-center gap-2 text-text-muted">
        <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span className="text-xs">Loading odds history...</span>
      </div>
    </div>
  ) : (!data || error || data.outcomes.length === 0) ? (
    <div className="flex-1 min-w-0 px-3 sm:px-4 pt-2 pb-1 flex items-center justify-center" style={{ minHeight: 200 }}>
      <span className="text-sm text-text-muted">No history data available</span>
    </div>
  ) : (
    <>
      <div className={`flex-1 min-w-0 px-3 sm:px-4 pt-2 pb-1 ${isFullscreen ? "min-h-0" : ""}`}>
        <EvolutionChart
          historyData={data.outcomes}
          selectedOutcomeIds={effectiveSelectedIds}
          highlightedOutcomeId={highlightedOutcomeId}
          onHoverOutcome={setHighlightedOutcomeId}
          roundBoundaries={effectiveBoundaries}
          height={isFullscreen ? 600 : 300}
          className=""
          timeRange={timeRange}
          tournamentStart={tournamentStart ?? null}
          showCombinedProbability={showCombinedProbability}
        />
      </div>
      <div className="w-full sm:w-[180px] sm:flex-shrink-0 sm:border-l border-t sm:border-t-0 border-surface-border px-3 py-2 sm:overflow-y-auto">
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
        <div className="px-3 sm:px-4 py-2.5 border-b border-surface-border flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3 flex-wrap">
            {/* Time Range control group */}
            <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
              Time Range
            </span>
            <div className="flex border border-surface-border rounded-md overflow-hidden">
              {(() => {
                // Tournament mode (#1138): once the event has started, lead with
                // "LIVE" (event-start -> now, the default) followed by 1D / 1W / ALL
                // zoom-in selectors. For completed tournaments, drop 1D (it'd show
                // nothing useful). Non-tournament charts keep Season / 7 Days / etc.
                const tournamentEnded = tournamentEnd
                  ? new Date(tournamentEnd).getTime() + 86_400_000 < Date.now()
                  : false;
                const inTournamentMode = hasTournament && tournamentStarted;
                const ranges: TimeRange[] = inTournamentMode
                  ? tournamentEnded
                    ? ["tournament", "7d", "full"]
                    : ["tournament", "24h", "7d", "full"]
                  : ["full", "7d", "24h", "today"];
                const labelFor = (range: TimeRange): string => {
                  if (inTournamentMode) {
                    return range === "tournament"
                      ? "LIVE"
                      : range === "24h"
                        ? "1D"
                        : range === "7d"
                          ? "1W"
                          : range === "full"
                            ? "ALL"
                            : "Today";
                  }
                  return range === "full"
                    ? "Season"
                    : range === "7d"
                      ? "7 Days"
                      : range === "24h"
                        ? "24 Hours"
                        : "Today";
                };
                return ranges.map((range) => (
                  <button
                    key={range}
                    onClick={() => setTimeRange(range)}
                    className={`px-3 py-1 text-[11.5px] font-medium border-r border-surface-border last:border-r-0 transition-colors ${
                      timeRange === range
                        ? "bg-text-primary text-white font-semibold"
                        : "text-text-secondary hover:bg-surface-secondary"
                    }`}
                  >
                    {labelFor(range)}
                  </button>
                ));
              })()}
            </div>

            {/* Position control group — only when multiple markets available */}
            {positionOptions && positionOptions.length > 1 && (
              <>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                  Stage
                </span>
                <div className="flex border border-surface-border rounded-md overflow-hidden">
                  {positionOptions.map((pos) => (
                    <button
                      key={pos.key}
                      onClick={() => setSelectedPosition(pos.key)}
                      className={`px-3 py-1 text-[11.5px] font-medium border-r border-surface-border last:border-r-0 transition-colors ${
                        selectedPosition === pos.key
                          ? "bg-text-primary text-white font-semibold"
                          : "text-text-secondary hover:bg-surface-secondary"
                      }`}
                    >
                      {pos.label}
                    </button>
                  ))}
                </div>
              </>
            )}

            <label className="flex h-7 items-center gap-1.5 rounded-md border border-surface-border px-2 text-[11.5px] font-medium text-text-secondary hover:bg-surface-secondary">
              <input
                type="checkbox"
                checked={showCombinedProbability}
                onChange={(e) => setShowCombinedProbability(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-surface-border accent-text-primary"
              />
              <span className="whitespace-nowrap">Combined</span>
            </label>
          </div>

          {/* Expand/collapse button */}
          <button
            onClick={() => setIsFullscreen((f) => !f)}
            className="w-8 h-8 rounded-md border border-surface-border bg-surface-card hover:bg-surface-secondary hover:border-text-muted flex items-center justify-center transition-colors flex-shrink-0"
            title={isFullscreen ? "Exit fullscreen" : "Expand"}
          >
            {isFullscreen ? (
              <svg className="w-4 h-4 text-text-secondary" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path d="M4 14h6v6m10-10h-6V4m0 16l6-6M14 4l-6 6" />
              </svg>
            ) : (
              <svg className="w-4 h-4 text-text-secondary" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
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
        <div className="px-3 sm:px-4 py-1.5 border-t border-surface-border bg-surface-secondary/80 flex justify-between text-[11px] text-text-muted">
          <span>{marketName || "Win Probability"} — {activePositionLabel}</span>
          <span>
            {effectiveSelectedIds.size} of {data?.outcomes.length ?? 0}
            {selectedOutcomeIds !== null && (
              <button
                onClick={() => setSelectedOutcomeIds(null)}
                className="ml-2 text-text-muted hover:text-blue-600 transition-colors"
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
