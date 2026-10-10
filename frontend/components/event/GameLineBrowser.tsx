"use client";

import type { GameMarketsResponse } from "@/lib/api";
import { formatProbabilityPercent } from "@/lib/probabilityDisplay";
import { isPregameStatus, isSettledStatus } from "@/lib/settledQuote";
import { sourceIsStale } from "@/lib/sourceAge";
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
    // #10823: team_totals used to carry one flattened over_probability across
    // first-half, full-game and the other club's lines. The server now prices
    // each line on its own (live aftercheck on f7e7cf8b), so each row prints
    // its own quote again.
    { label: "Team scoring", rows: data.team_totals ?? [] },
    { label: "Periods", rows: data.period_markets ?? [] },
  ];
  const settled = isSettledStatus(status);
  const live = !settled && !isPregameStatus(status);
  const now = Date.now();
  const isOver = (outcome: string) => /\bover\b/i.test(outcome);
  const lineKey = (row: {
    market_name: string;
    threshold: number | null;
    source: string;
  }) => `${row.source}|${row.market_name}|${row.threshold}`;
  const items = groups.flatMap((group) => {
    // An Under row carries its Over twin's price, so beside that twin it adds a
    // blank row and nothing else. Only an Under with no Over twin stays listed.
    const overLines = new Set(
      group.rows.filter((row) => isOver(row.outcome_name)).map(lineKey),
    );
    return group.rows.flatMap((row, index) => {
      if (
        !("probability" in row) &&
        /\bunder\b/i.test(row.outcome_name) &&
        overLines.has(lineKey(row))
      ) {
        return [];
      }
      // During play a price last observed before the game moved on is not
      // today's chance: print nothing rather than a pregame number.
      const stale = live && sourceIsStale(row.observed_at, now);
      // over_probability is normalized to the OVER proposition even on a
      // source row named Under. Never attach it to that opposite outcome or
      // invent its complement. A direct outcome quote, when present, wins.
      const probability = stale
        ? null
        : "probability" in row
          ? row.probability
          : isOver(row.outcome_name)
            ? row.over_probability
            : null;
      return [
        {
          key: `${group.label}-${index}`,
          group: group.label,
          search: `${row.market_name} ${row.outcome_name}`,
          content: (
            <div
              className="py-3 border-b border-surface-border"
              data-quote={stale ? "stale" : undefined}
            >
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
              <div className="text-xs text-text-secondary mt-1">
                {row.source}
              </div>
            </div>
          ),
        },
      ];
    });
  });
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
