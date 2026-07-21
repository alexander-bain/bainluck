"use client";

// #999 L2-64 Event Concept Page — settled probability-path chart. For a resolved
// event: the full path each top contender's probability took to the outcome, on a
// fixed 0–100 axis. Step interpolation suits the sparse late-stage snapshots.
// Probability-only, no source names.
//
// #L2-137 chart-excellence Phase 0: the completed journey is the default (the
// "settled means settled — charts show the completed journey" ruling), but a
// months-long flatline compresses the resolution spike into an unreadable
// vertical edge. Time-range chips (All / 1M / 1W / 1D / Since start) let the
// reader zoom to the part that carries the story, and a static legend names the
// lines.

import { useMemo, useState } from "react";
import useSWR from "swr";
import { fetchFuturesHistory } from "@/lib/api";
import type { FuturesOutcomeHistory } from "@/lib/types";
import { FuturesChart } from "@/components/FuturesChart";
import ChartRangeChips from "@/components/event/ChartRangeChips";
import {
  availableRanges,
  windowOutcomeHistory,
  type ChartRangeKey,
} from "@/lib/chartWindow";
import { golfRoundMarkers } from "@/lib/golfRounds";

interface SettledPathChartProps {
  marketId: number;
  domain?: string;
  /** L2-135: tournament start/end — golf's settled path gets R1..R4 markers. */
  startDate?: string | null;
  endDate?: string | null;
  /** L2-147 Item 3: the champion's name. When it matches an outcome, that line is
   *  drawn first (leader color) and guaranteed into the visible set — the settled
   *  journey highlights how the winner got there, not an arbitrary top-5. */
  championName?: string | null;
}

/** Last non-null probability of a series (its "current"/final value). */
function lastProbOf(o: FuturesOutcomeHistory): number {
  for (let i = o.history.length - 1; i >= 0; i--) {
    const p = o.history[i]?.probability;
    if (p != null) return p;
  }
  return -1;
}

export default function SettledPathChart({
  marketId,
  domain,
  startDate,
  endDate,
  championName,
}: SettledPathChartProps) {
  // Widest window — a settled event's path spans the whole run.
  const { data, isLoading } = useSWR(
    ["event-settled-path", marketId],
    () => fetchFuturesHistory(marketId, 8760, undefined, 8),
    { revalidateOnFocus: false },
  );

  const [range, setRange] = useState<ChartRangeKey>("all");

  const outcomes: FuturesOutcomeHistory[] = useMemo(
    () => data?.outcomes ?? [],
    [data],
  );
  const hasHistory = outcomes.some(
    (o) => o.history.filter((p) => p.probability != null).length >= 2,
  );

  const startMs = startDate ? new Date(startDate).getTime() : null;
  const ranges = useMemo(
    () => availableRanges(outcomes, startMs != null),
    [outcomes, startMs],
  );
  const windowed = useMemo(
    () => windowOutcomeHistory(outcomes, range, startMs),
    [outcomes, range, startMs],
  );

  // L2-147 Item 3: reorder so the champion's line is FIRST (leader color) and
  // pick the visible set = champion + the next strongest lines. FuturesChart
  // filters by the selected ids preserving `plotted` order, so the winner leads
  // the legend and can never be pushed out by an arbitrary top-5 slice. When the
  // winner can't be named/matched, plotted === windowed and the default applies.
  const { plotted, selected } = useMemo(() => {
    const target = championName?.trim().toLowerCase();
    const champ = target
      ? windowed.find((o) => (o.name ?? "").trim().toLowerCase() === target)
      : undefined;
    if (!champ) return { plotted: windowed, selected: undefined as Set<number> | undefined };
    const rest = windowed
      .filter((o) => o.outcome_id !== champ.outcome_id)
      .sort((a, b) => lastProbOf(b) - lastProbOf(a));
    const plotted = [champ, ...rest];
    const selected = new Set(plotted.slice(0, 6).map((o) => o.outcome_id));
    return { plotted, selected };
  }, [windowed, championName]);

  if (!isLoading && !hasHistory) return null;

  // For a settled event, cap markers at the event end (now-cap doesn't apply).
  const timeMarkers =
    domain === "golf" ? golfRoundMarkers(startDate, endDate, Date.now()) : undefined;

  return (
    <section id="path" className="bg-surface-card rounded-card shadow-card p-6">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <h2 className="text-title-3 font-semibold text-text-primary">Path to resolution</h2>
        {!isLoading && hasHistory && (
          <ChartRangeChips ranges={ranges} selected={range} onSelect={setRange} />
        )}
      </div>
      {isLoading ? (
        <div className="h-48 flex items-center justify-center text-sm text-text-secondary">
          Loading resolution path…
        </div>
      ) : (
        <FuturesChart
          historyData={plotted}
          selectedOutcomes={selected}
          fixedYAxis
          stepInterpolation
          showAxes
          showLegend
          height={260}
          greenTheme={domain === "golf"}
          timeMarkers={timeMarkers}
        />
      )}
    </section>
  );
}
