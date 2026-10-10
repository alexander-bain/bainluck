"use client";

import type { GameMarketsResponse } from "@/lib/api";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { isSettledStatus } from "@/lib/settledQuote";
import MarketBrowser from "./MarketBrowser";

/** The original quoted lines remain reachable when a family has no map. */
export default function GameLineBrowser({
  data,
  status,
}: {
  data: GameMarketsResponse;
  status?: string;
}) {
  const groups = [
    // #10823: the served team_totals over_probability is flattened across
    // first-half, full-game and the other club's lines (events.py 7c groups by
    // team_side only), so one number repeats on unrelated questions. Keep each
    // question reachable, but print no percentage until the server repair is
    // verified on production.
    { label: "Team scoring", rows: data.team_totals ?? [], withheld: true },
    { label: "Periods", rows: data.period_markets ?? [], withheld: false },
  ];
  const settled = isSettledStatus(status);
  const items = groups.flatMap((group) =>
    group.rows.map((row, index) => {
      // over_probability is normalized to the OVER proposition even on a
      // source row named Under. Never attach it to that opposite outcome or
      // invent its complement. A direct outcome quote, when present, wins.
      const probability = group.withheld
        ? null
        : "probability" in row
          ? row.probability
          : /\bover\b/i.test(row.outcome_name)
            ? row.over_probability
            : null;
      return {
        key: `${group.label}-${index}`,
        group: group.label,
        search: `${row.market_name} ${row.outcome_name}`,
        content: (
          <div className="py-3 border-b border-surface-border">
            <div className="text-sm font-medium">{row.market_name}</div>
            <div className="flex justify-between gap-4 mt-1 text-sm">
              <span>{row.outcome_name}</span>
              {probability != null && (
                <strong className="font-mono tabular-nums whitespace-nowrap">
                  {settled ? "Last quote " : ""}
                  {formatProbabilityPercent(probability)}
                </strong>
              )}
              {group.withheld && (
                <span
                  className="text-text-secondary whitespace-nowrap"
                  data-quote="withheld"
                >
                  Unavailable
                </span>
              )}
            </div>
            <div className="text-xs text-text-secondary mt-1">{row.source}</div>
          </div>
        ),
      };
    }),
  );
  if (!items.length) return null;
  return (
    <details className="rounded-xl border border-surface-border bg-surface-card p-4">
      <summary className="cursor-pointer min-h-11 text-sm font-semibold">
        Team scoring &amp; period lines
      </summary>
      <MarketBrowser label="Quoted lines" items={items} />
    </details>
  );
}
