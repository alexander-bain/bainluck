"use client";

// #999 L2-64 Event Concept Page — co-equal / two-sided variant (UFC-style). For
// primary.kind === "co_equal_list": two head-to-head competitors as a split
// probability bar plus a shared probability timeline on a fixed 0–100 axis. Built
// now; tennis/golf are winner_field, so this renders for co-equal domains (fights)
// once they route here. Probability-only, no source names, straight segments.

import { useState } from "react";
import useSWR from "swr";
import { fetchFuturesHistory } from "@/lib/api";
import { formatProbability } from "@/lib/api";
import { fieldOrder } from "@/lib/eventConceptDisplay";
import type { EventConceptCompetitor, FuturesOutcomeHistory } from "@/lib/types";
import { FuturesChart } from "@/components/FuturesChart";
import FighterAvatar from "./FighterAvatar";

interface TwoSidedTimelineProps {
  competitors: EventConceptCompetitor[];
  label: string;
  evolutionMarketId?: number | null;
}

const RANGES: { label: string; hours: number }[] = [
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "All", hours: 8760 },
];

export default function TwoSidedTimeline({
  competitors,
  label,
  evolutionMarketId,
}: TwoSidedTimelineProps) {
  const [hours, setHours] = useState(168);
  const pair = fieldOrder(competitors).slice(0, 2);
  const { data } = useSWR(
    evolutionMarketId ? ["event-twosided", evolutionMarketId, hours] : null,
    () => fetchFuturesHistory(evolutionMarketId as number, hours, undefined, 4),
    { revalidateOnFocus: false },
  );

  if (pair.length < 2) return null;

  const [a, b] = pair;
  const aPct = a.probability != null ? Math.round(a.probability * 100) : 50;
  const outcomes: FuturesOutcomeHistory[] = data?.outcomes ?? [];
  const hasHistory = outcomes.some(
    (o) => o.history.filter((p) => p.probability != null).length >= 2,
  );

  return (
    <section id="head-to-head" className="bg-surface-card rounded-card shadow-card p-6">
      <h2 className="text-title-3 font-semibold text-text-primary mb-4">{label || "Head to head"}</h2>

      {/* Two-sided split bar. L2-113: fighter avatars flank the head-to-head so the
          marquee bout reads as two people, not two text labels. */}
      <div className="flex items-center justify-between text-sm mb-2">
        <div className="flex items-center gap-2 min-w-0 mr-2">
          <FighterAvatar name={a.name} size={40} />
          <span className="text-text-primary font-medium truncate">{a.name}</span>
        </div>
        <div className="flex items-center gap-2 min-w-0 ml-2 justify-end">
          <span className="text-text-primary font-medium truncate text-right">{b.name}</span>
          <FighterAvatar name={b.name} size={40} />
        </div>
      </div>
      <div className="flex items-center justify-between font-mono text-lg font-semibold tabular-nums mb-1.5">
        <span className="text-accent-brand">{formatProbability(a.probability)}</span>
        <span className="text-text-secondary">{formatProbability(b.probability)}</span>
      </div>
      <div className="flex h-2.5 rounded-full overflow-hidden bg-surface-elevated">
        <div className="h-full bg-accent-brand" style={{ width: `${aPct}%` }} />
        <div className="h-full bg-text-muted/50" style={{ width: `${100 - aPct}%` }} />
      </div>

      {/* Shared timeline */}
      {hasHistory && (
        <div className="mt-5">
          <div className="flex justify-end mb-2">
            <div className="flex rounded-full bg-surface-elevated p-0.5">
              {RANGES.map((r) => (
                <button
                  key={r.hours}
                  onClick={() => setHours(r.hours)}
                  className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
                    hours === r.hours
                      ? "bg-surface-card text-text-primary shadow-card font-semibold"
                      : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
          <FuturesChart
            historyData={outcomes}
            fixedYAxis
            showAxes
            showLegend={false}
            height={240}
          />
        </div>
      )}
    </section>
  );
}
