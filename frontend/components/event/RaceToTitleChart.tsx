"use client";

// #999 L2-64/L2-71 Event Concept Page — "Race to the title" full-width chart.
// Plots the top contenders' BLENDED probability lines over time on a FIXED,
// labeled 0–100 axis with STRAIGHT segments (no smoothing) — the D1/#883 binds. A
// range switcher (24h / 7d / All) and a top-N switcher control the view. L2-71:
// the series come FROM the envelope (competitor.history) — no separate fetch; the
// range switcher filters those points client-side. Honest-empty when no
// per-competitor history exists yet — never invent a line.

import { useMemo, useState } from "react";
import type { EventConceptCompetitor, FuturesOutcomeHistory } from "@/lib/types";
import { competitorsToOutcomeHistory } from "@/lib/eventConceptDisplay";
import { FuturesChart } from "@/components/FuturesChart";

interface RaceToTitleChartProps {
  /** Envelope competitors carrying per-competitor `history` (L2-71). */
  competitors: EventConceptCompetitor[];
  /** Golf tints the leader gold; other domains use the default palette. */
  domain?: string;
}

const RANGES: { label: string; hours: number }[] = [
  { label: "24h", hours: 24 },
  { label: "7d", hours: 168 },
  { label: "All", hours: 0 }, // 0 = no time filter
];
const TOPS = [5, 10];

/** Current probability = the last non-null point of an outcome's series. */
function lastProb(o: FuturesOutcomeHistory): number {
  for (let i = o.history.length - 1; i >= 0; i--) {
    const p = o.history[i]?.probability;
    if (p != null) return p;
  }
  return -1;
}

export default function RaceToTitleChart({ competitors, domain }: RaceToTitleChartProps) {
  const [hours, setHours] = useState(168);
  const [topN, setTopN] = useState(5);

  // Built from the envelope's per-competitor history; the range switch filters
  // points client-side (no refetch).
  const outcomes: FuturesOutcomeHistory[] = useMemo(
    () => competitorsToOutcomeHistory(competitors, hours),
    [competitors, hours],
  );

  // Pick the current top-N contenders (by latest probability) and hand their ids
  // to FuturesChart as the selected set so it plots exactly those lines.
  const selected = useMemo(() => {
    const ranked = [...outcomes].sort((a, b) => lastProb(b) - lastProb(a));
    return new Set(ranked.slice(0, topN).map((o) => o.outcome_id));
  }, [outcomes, topN]);

  const hasHistory = outcomes.some(
    (o) => o.history.filter((p) => p.probability != null).length >= 2,
  );
  const isLoading = false;

  return (
    <section id="race" className="bg-surface-card rounded-card shadow-card p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h2 className="text-title-3 font-semibold text-text-primary">Race to the title</h2>
        <div className="flex items-center gap-3">
          <div className="flex rounded-full bg-surface-elevated p-0.5">
            {TOPS.map((t) => (
              <button
                key={t}
                onClick={() => setTopN(t)}
                className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
                  topN === t
                    ? "bg-surface-card text-text-primary shadow-card font-semibold"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                Top {t}
              </button>
            ))}
          </div>
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
      </div>

      {isLoading ? (
        <div className="h-56 flex items-center justify-center text-sm text-text-secondary">
          Loading probability history…
        </div>
      ) : hasHistory ? (
        <FuturesChart
          historyData={outcomes}
          selectedOutcomes={selected}
          fixedYAxis
          showAxes
          showLegend={false}
          height={280}
          greenTheme={domain === "golf"}
        />
      ) : (
        <div className="h-40 flex flex-col items-center justify-center gap-1 text-sm text-text-secondary">
          <span>Probability history isn&apos;t available for this event yet.</span>
          <span className="text-xs text-text-muted">
            The race chart appears once enough snapshots are recorded.
          </span>
        </div>
      )}
    </section>
  );
}
