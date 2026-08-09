"use client";

import { useMemo } from "react";
import type { GameMarketsResponse } from "@/lib/api";
import {
  buildMarketSection,
  MAX_CARDS_PER_CATEGORY,
  MAX_OUTCOMES_PER_CARD,
  type MarketCard,
} from "@/lib/otherMarketGroups";

interface SpecialEventMarketsProps {
  data: GameMarketsResponse;
  eventStatus?: string;
}

function OutcomeBar({
  outcome,
  rank,
}: {
  outcome: MarketCard["outcomes"][0];
  rank: number;
}) {
  return (
    <div className="flex items-center gap-2">
      <div className={`text-xs flex-1 ${rank === 0 ? "font-semibold" : "text-text-secondary"}`}>
        {outcome.label}
      </div>
      <div className="flex-1 h-1.5 rounded-full bg-surface-border overflow-hidden max-w-[140px]">
        <div
          className={`h-full rounded-full transition-all duration-500 ${rank === 0 ? "bg-violet-400" : "bg-text-muted/40"}`}
          style={{ width: `${outcome.prob * 100}%` }}
        />
      </div>
      <span className="font-mono tabular-nums text-xs font-semibold w-10 text-right">
        {Math.round(outcome.prob * 100)}%
      </span>
    </div>
  );
}

function PropMiniCard({ item }: { item: MarketCard }) {
  const maxSourceCount = Math.max(...item.outcomes.map((o) => o.sourceCount ?? 1));
  const sourceCount =
    maxSourceCount > 1 ? maxSourceCount : new Set(item.outcomes.map((o) => o.source)).size;

  // K10: cap the bars a single card can stack. Live MLB games put 34–61 props
  // under one heading; the overflow is DISCLOSED, never dropped (gotcha #43).
  const shown = item.outcomes.slice(0, MAX_OUTCOMES_PER_CARD);
  const rest = item.outcomes.slice(MAX_OUTCOMES_PER_CARD);

  return (
    <div className="border border-surface-border rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="font-medium text-sm">{item.name}</div>
        {sourceCount > 1 && (
          <span className="text-[10px] font-semibold text-blue-600">{sourceCount}x</span>
        )}
      </div>
      <div className="space-y-1.5">
        {shown.map((o, i) => (
          <OutcomeBar key={o.label} outcome={o} rank={i} />
        ))}
      </div>
      {rest.length > 0 && (
        <details className="mt-1.5">
          <summary className="cursor-pointer select-none py-1 text-[11px] text-text-muted">
            {rest.length} more
          </summary>
          <div className="space-y-1.5 pt-1.5">
            {rest.map((o) => (
              <OutcomeBar key={o.label} outcome={o} rank={1} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

export default function SpecialEventMarkets({ data }: SpecialEventMarketsProps) {
  const section = useMemo(() => buildMarketSection(data.other), [data.other]);

  if (section.categories.length === 0) return null;

  const { renderedOutcomes, withheld } = section;

  return (
    <div>
      <div className="flex items-end justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">Additional Markets</h3>
          <p className="text-sm text-text-secondary mt-0.5">
            {renderedOutcomes} market{renderedOutcomes === 1 ? "" : "s"} grouped by category
            {withheld > 0 && (
              <>
                {" · "}
                <span className="text-text-muted">
                  {withheld} hidden (conflicting duplicate price{withheld === 1 ? "" : "s"})
                </span>
              </>
            )}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {section.categories.map((cat) => {
          const shownCards = cat.cards.slice(0, MAX_CARDS_PER_CATEGORY);
          const restCards = cat.cards.slice(MAX_CARDS_PER_CATEGORY);
          return (
            <div
              key={cat.title}
              className="bg-surface-card border border-surface-border rounded-xl shadow-sm p-4"
            >
              <div className="mb-3">
                <div className="font-semibold">{cat.title}</div>
                <div className="text-xs text-text-muted">{cat.subtitle}</div>
              </div>
              <div className="space-y-3">
                {shownCards.map((item) => (
                  <PropMiniCard key={item.name} item={item} />
                ))}
                {restCards.length > 0 && (
                  <details>
                    <summary className="cursor-pointer select-none text-center text-[10px] text-text-muted py-1">
                      +{restCards.length} more
                    </summary>
                    <div className="space-y-3 pt-3">
                      {restCards.map((item) => (
                        <PropMiniCard key={item.name} item={item} />
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
