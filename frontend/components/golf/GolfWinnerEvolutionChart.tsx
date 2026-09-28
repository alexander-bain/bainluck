"use client";

import { useEffect, useMemo, useState } from "react";
import { EvolutionView } from "@/components/EvolutionView";
import { fetchFuturesHistory } from "@/lib/api";
import { isDrawableHistory, winnerChartCandidates } from "@/lib/golfWinnerChart";

// ============================================================================
// Evolution Chart with market fallback — tries market IDs in order until
// one can draw a line. Backend sorts Winner markets first.
// ============================================================================

export function EvolutionViewWithFallback({
  marketIds,
  marketNames,
  marketName,
  defaultTopN,
  hours,
}: {
  marketIds: number[];
  marketNames?: string[];
  marketName: string;
  defaultTopN: number;
  hours: number;
}) {
  // #6243: walk only the Winner questions (the heading says "Win Probability"),
  // and advance on the chart's own drawability test — see `lib/golfWinnerChart.ts`.
  const candidates = useMemo(
    () => winnerChartCandidates(marketIds, marketNames),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [marketIds.join(","), (marketNames ?? []).join("\u0000")],
  );
  const [currentIndex, setCurrentIndex] = useState(0);

  // Reset when the candidates change
  useEffect(() => {
    setCurrentIndex(0);
  }, [candidates]);

  if (candidates.length === 0) return null;

  // Nothing can draw: the first candidate's own empty state, as before #6243.
  if (currentIndex >= candidates.length) {
    return (
      <EvolutionView
        requireCurrentPrices
        marketId={candidates[0]}
        marketName={marketName}
        defaultTopN={defaultTopN}
        hours={hours}
      />
    );
  }

  const marketId = candidates[currentIndex];
  return (
    <EvolutionViewWithCallback
      key={marketId}
      marketId={marketId}
      marketName={marketName}
      defaultTopN={defaultTopN}
      hours={hours}
      onEmpty={() => setCurrentIndex((i) => i + 1)}
    />
  );
}

function EvolutionViewWithCallback({
  marketId,
  marketName,
  defaultTopN,
  hours,
  onEmpty,
}: {
  marketId: number;
  marketName: string;
  defaultTopN: number;
  hours: number;
  onEmpty: () => void;
}) {
  const [hasData, setHasData] = useState<boolean | null>(null);

  // Check if this market has history data before rendering EvolutionView
  useEffect(() => {
    let cancelled = false;
    fetchFuturesHistory(marketId, hours, undefined, 30)
      .then((data) => {
        if (cancelled) return;
        if (!isDrawableHistory(data)) {
          setHasData(false);
          onEmpty();
        } else {
          setHasData(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHasData(false);
          onEmpty();
        }
      });
    return () => {
      cancelled = true;
    };
  }, [marketId, hours]);

  if (hasData === null) {
    return (
      <div className="animate-pulse">
        <div className="h-8 bg-gray-800 rounded w-48 mb-4" />
        <div className="h-[400px] bg-gray-800/50 rounded-lg" />
      </div>
    );
  }

  if (!hasData) return null;

  return (
    <EvolutionView
      requireCurrentPrices
      marketId={marketId}
      marketName={marketName}
      defaultTopN={defaultTopN}
      hours={hours}
    />
  );
}
