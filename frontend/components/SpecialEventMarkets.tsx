"use client";

import { useMemo } from "react";
import type { GameMarketsResponse } from "@/lib/api";
import {
  buildMarketSection,
  MAX_CARDS_PER_CATEGORY,
  MAX_OUTCOMES_PER_CARD,
  type MarketCard,
} from "@/lib/otherMarketGroups";
import {
  isSettledStatus,
  SETTLED_QUOTE_PREFIX,
  SETTLED_QUOTE_SECTION_NOTE,
} from "@/lib/settledQuote";

interface SpecialEventMarketsProps {
  data: GameMarketsResponse;
  eventStatus?: string;
  /**
   * Sets already played out, for a match still in progress. The event page
   * passes it for tennis only; everything else leaves it undefined and no row
   * changes. See `buildMarketSection`'s `completedSets`.
   */
  completedSets?: number;
}

function OutcomeBar({
  outcome,
  rank,
  settled,
}: {
  outcome: MarketCard["outcomes"][0];
  rank: number;
  /** #2086: the game is over, so this number is a frozen quote, not a chance. */
  settled: boolean;
}) {
  const percent = Math.round(outcome.prob * 100);
  // A finished GAME settles every row; a finished SET settles only the rows
  // that asked about it. Both end in the same render, because both are the same
  // statement to a reader: this number stopped being a chance.
  const frozen = settled || outcome.decided === true;

  // A settled row loses the bar, exactly as `PropTravelBar`'s `ResolvedMark`
  // does. A filled bar is a picture of a live distribution; leaving it up and
  // only re-wording the caption keeps the lie in the part of the row a reader
  // actually looks at.
  if (frozen) {
    return (
      <div className="flex items-baseline gap-2 text-xs">
        <div className={`flex-1 ${rank === 0 ? "font-semibold" : "text-text-secondary"}`}>
          {outcome.label}
        </div>
        <span className="font-mono tabular-nums text-text-muted">
          {SETTLED_QUOTE_PREFIX} {percent}%
        </span>
      </div>
    );
  }

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
        {percent}%
      </span>
    </div>
  );
}

function PropMiniCard({ item, settled }: { item: MarketCard; settled: boolean }) {
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
          <OutcomeBar key={o.label} outcome={o} rank={i} settled={settled} />
        ))}
      </div>
      {rest.length > 0 && (
        <details className="mt-1.5">
          <summary className="cursor-pointer select-none py-1 text-[11px] text-text-muted">
            {rest.length} more
          </summary>
          <div className="space-y-1.5 pt-1.5">
            {rest.map((o) => (
              <OutcomeBar key={o.label} outcome={o} rank={1} settled={settled} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

export default function SpecialEventMarkets({
  data,
  eventStatus,
  completedSets,
}: SpecialEventMarketsProps) {
  const section = useMemo(
    () => buildMarketSection(data.other, { completedSets }),
    [data.other, completedSets],
  );

  // #2086. `eventStatus` has been DECLARED on this component's props and PASSED
  // by the event page since the section shipped — and destructured by nobody, so
  // every `other` row printed a live-looking chance on a game that had finished.
  // A grep for `eventStatus` here finds the declaration and the call site and
  // reads as handled; an optional prop that is never destructured is invisible
  // to tsc. Measured 2026-08-21: of 158 priced rows on 40 settled events, the
  // MODAL row sits in 0.40–0.60 — a coin-flip on a match that ended a week ago,
  // which reads far more plausibly than the 99% the issue was filed on.
  //
  // The predicate is `isSettledStatus`, not a local `=== "completed"` pair: the
  // page, `MarketMapSection` and `propDivergence` were already carrying three
  // spellings of "settled" between them, and this is the widest owned one.
  const settled = isSettledStatus(eventStatus);

  if (section.categories.length === 0) return null;

  const { renderedOutcomes, withheld } = section;

  return (
    <div>
      <div className="flex items-end justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">Additional Markets</h3>
          <p className="text-sm text-text-secondary mt-0.5">
            {renderedOutcomes} market{renderedOutcomes === 1 ? "" : "s"} grouped by category
            {/* Said ONCE, at section level, following `PropDivergenceDetail`'s
                "Not graded" group rather than `PropTravelBar`'s per-row label.
                The rail labels each row because its rows differ — some HIT,
                some MISS, some ungraded — so the label discriminates. Here
                every row is in the same state, so repeating it ten times
                discriminates nothing and just crowds the card. */}
            {settled && (
              <>
                {" · "}
                <span className="text-text-muted" data-testid="special-markets-settled-note">
                  {SETTLED_QUOTE_SECTION_NOTE}
                </span>
              </>
            )}
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
                  <PropMiniCard key={item.name} item={item} settled={settled} />
                ))}
                {restCards.length > 0 && (
                  <details>
                    <summary className="cursor-pointer select-none text-center text-[10px] text-text-muted py-1">
                      +{restCards.length} more
                    </summary>
                    <div className="space-y-3 pt-3">
                      {restCards.map((item) => (
                        <PropMiniCard key={item.name} item={item} settled={settled} />
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
