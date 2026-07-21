"use client";

// L2-132 Event Concept Page — WINNER EVOLUTION chart. For a LIVE/upcoming
// winner-field concept (the World Cup): the probability path the title picture
// has taken so far — the tournament's story to date — for the top contenders, on
// a fixed 0–100 axis. It is the live analogue of SettledPathChart: both reuse the
// shared FuturesChart and fetch the winner market's history by
// `evolution_market_id`. Renders nothing until there are ≥2 real points — we
// never invent a series. Step interpolation suits the sparse futures snapshots.

import { useMemo, useState } from "react";
import useSWR from "swr";
import { fetchFuturesHistory } from "@/lib/api";
import type { FuturesOutcomeHistory } from "@/lib/types";
import { outcomesByLatestProb } from "@/lib/eventConceptDisplay";
import { FuturesChart } from "@/components/FuturesChart";
import ChartRangeChips from "@/components/event/ChartRangeChips";
import {
  availableRanges,
  windowOutcomeHistory,
  type ChartRangeKey,
} from "@/lib/chartWindow";

interface WinnerEvolutionChartProps {
  marketId: number;
  domain?: string;
  /** Poll at in-play cadence while the tournament is live. */
  live?: boolean;
}

export default function WinnerEvolutionChart({
  marketId,
  domain,
  live = false,
}: WinnerEvolutionChartProps) {
  // Widest window — the winner field has traded since well before kickoff, so the
  // whole run is the story. Top 8 outcomes fetched; the chart draws the top 5.
  const { data, isLoading } = useSWR(
    ["event-winner-evolution", marketId],
    () => fetchFuturesHistory(marketId, 8760, undefined, 8),
    { revalidateOnFocus: false, refreshInterval: live ? 60000 : 0 },
  );

  // The history endpoint returns outcomes in a volume-ish order, not by win
  // probability (the WC payload leads with Egypt, trails with England). FuturesChart
  // draws the first 5, so order by each outcome's LATEST real probability desc — the
  // chart then plots the actual title contenders' paths, not 5 flat-0% longshots.
  const outcomes: FuturesOutcomeHistory[] = useMemo(
    () => outcomesByLatestProb(data?.outcomes ?? []),
    [data],
  );
  const hasHistory = outcomes.some(
    (o) => o.history.filter((p) => p.probability != null).length >= 2,
  );

  // #L2-137 chart-excellence Phase 0: same time-range floor as SettledPathChart.
  // No event-start prop here, so "Since start" is not offered.
  const [range, setRange] = useState<ChartRangeKey>("all");
  const ranges = useMemo(() => availableRanges(outcomes, false), [outcomes]);
  const windowed = useMemo(
    () => windowOutcomeHistory(outcomes, range),
    [outcomes, range],
  );

  // Honest absence: no real path yet → render nothing (never a fabricated chart).
  if (!isLoading && !hasHistory) return null;

  return (
    <section id="evolution" className="bg-surface-card rounded-card shadow-card p-6">
      <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
        <div>
          <h2 className="text-title-3 font-semibold text-text-primary mb-1">
            Winner evolution
          </h2>
          <p className="text-sm text-text-secondary">
            How the title picture has moved over the tournament.
          </p>
        </div>
        {!isLoading && hasHistory && (
          <ChartRangeChips ranges={ranges} selected={range} onSelect={setRange} />
        )}
      </div>
      {isLoading ? (
        <div className="h-48 flex items-center justify-center text-sm text-text-secondary">
          Loading evolution…
        </div>
      ) : (
        <FuturesChart
          historyData={windowed}
          fixedYAxis
          stepInterpolation
          showAxes
          showLegend
          height={280}
          greenTheme={domain === "golf"}
        />
      )}
    </section>
  );
}
