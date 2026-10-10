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
    { label: "Team scoring", rows: data.team_totals ?? [] },
    { label: "Periods", rows: data.period_markets ?? [] },
  ];
  const settled = isSettledStatus(status);
  const items = groups.flatMap((group) =>
    group.rows.map((row, index) => {
      const probability =
        row.over_probability ?? ("probability" in row ? row.probability : null);
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
