"use client";

// L2-132 Event Concept Page — WINNER EVOLUTION chart. For a LIVE/upcoming
// winner-field concept (the World Cup): the probability path the title picture
// has taken so far — the tournament's story to date — for the top contenders, on
// a fixed 0–100 axis. It is the live analogue of SettledPathChart: both reuse the
// shared FuturesChart and fetch the winner market's history by
// `evolution_market_id`. Renders nothing until there are ≥2 real points — we
// never invent a series. Step interpolation suits the sparse futures snapshots.

import useSWR from "swr";
import { fetchFuturesHistory } from "@/lib/api";
import type { FuturesOutcomeHistory } from "@/lib/types";
import { FuturesChart } from "@/components/FuturesChart";

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

  const outcomes: FuturesOutcomeHistory[] = data?.outcomes ?? [];
  const hasHistory = outcomes.some(
    (o) => o.history.filter((p) => p.probability != null).length >= 2,
  );

  // Honest absence: no real path yet → render nothing (never a fabricated chart).
  if (!isLoading && !hasHistory) return null;

  return (
    <section id="evolution" className="bg-surface-card rounded-card shadow-card p-6">
      <h2 className="text-title-3 font-semibold text-text-primary mb-1">
        Winner evolution
      </h2>
      <p className="text-sm text-text-secondary mb-4">
        How the title picture has moved over the tournament.
      </p>
      {isLoading ? (
        <div className="h-48 flex items-center justify-center text-sm text-text-secondary">
          Loading evolution…
        </div>
      ) : (
        <FuturesChart
          historyData={outcomes}
          fixedYAxis
          stepInterpolation
          showAxes
          showLegend={false}
          height={280}
          greenTheme={domain === "golf"}
        />
      )}
    </section>
  );
}
