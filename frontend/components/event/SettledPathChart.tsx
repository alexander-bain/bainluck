"use client";

// #999 L2-64 Event Concept Page — settled probability-path chart. For a resolved
// event: the full path each top contender's probability took to the outcome, on a
// fixed 0–100 axis. Step interpolation suits the sparse late-stage snapshots.
// Probability-only, no source names.

import useSWR from "swr";
import { fetchFuturesHistory } from "@/lib/api";
import type { FuturesOutcomeHistory } from "@/lib/types";
import { FuturesChart } from "@/components/FuturesChart";
import { golfRoundMarkers } from "@/lib/golfRounds";

interface SettledPathChartProps {
  marketId: number;
  domain?: string;
  /** L2-135: tournament start/end — golf's settled path gets R1..R4 markers. */
  startDate?: string | null;
  endDate?: string | null;
}

export default function SettledPathChart({
  marketId,
  domain,
  startDate,
  endDate,
}: SettledPathChartProps) {
  // Widest window — a settled event's path spans the whole run.
  const { data, isLoading } = useSWR(
    ["event-settled-path", marketId],
    () => fetchFuturesHistory(marketId, 8760, undefined, 8),
    { revalidateOnFocus: false },
  );

  const outcomes: FuturesOutcomeHistory[] = data?.outcomes ?? [];
  const hasHistory = outcomes.some(
    (o) => o.history.filter((p) => p.probability != null).length >= 2,
  );

  if (!isLoading && !hasHistory) return null;

  // For a settled event, cap markers at the event end (now-cap doesn't apply).
  const timeMarkers =
    domain === "golf" ? golfRoundMarkers(startDate, endDate, Date.now()) : undefined;

  return (
    <section id="path" className="bg-surface-card rounded-card shadow-card p-6">
      <h2 className="text-title-3 font-semibold text-text-primary mb-4">Path to resolution</h2>
      {isLoading ? (
        <div className="h-48 flex items-center justify-center text-sm text-text-secondary">
          Loading resolution path…
        </div>
      ) : (
        <FuturesChart
          historyData={outcomes}
          fixedYAxis
          stepInterpolation
          showAxes
          showLegend={false}
          height={260}
          greenTheme={domain === "golf"}
          timeMarkers={timeMarkers}
        />
      )}
    </section>
  );
}
