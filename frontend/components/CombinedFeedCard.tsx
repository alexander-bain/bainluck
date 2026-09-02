"use client";

/**
 * CombinedFeedCard — renders a cross-source market group in the feed.
 *
 * When multiple markets share the same canonical_market_key (e.g., "NBA
 * Championship Winner" from Polymarket, Kalshi, and Odds API), this card
 * merges their outcomes and shows a compact cross-source comparison.
 */

import Link from "next/link";
import type { FeedItem, FeedFuturesData, FeedFuturesOutcome } from "@/lib/types";
import { formatProbability } from "@/lib/api";
import { getEmojiForCategory, getNameForCategory } from "@/lib/sportCategories";
import type { GroupedMarket } from "@/lib/feedSections";
import { sourceHex } from "@/lib/sourceColors";

// ---------------------------------------------------------------------------
// Source display helpers
// ---------------------------------------------------------------------------

const SOURCE_LABELS: Record<string, string> = {
  odds_api: "Sportsbooks",
  kalshi: "Kalshi",
  polymarket: "Polymarket",
};

function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] || source;
}

// ---------------------------------------------------------------------------
// Outcome merging (same logic as CombinedMarketCard but using FeedFuturesData)
// ---------------------------------------------------------------------------

interface MergedOutcome {
  name: string;
  bySource: Record<string, number | null>;
  avgProbability: number;
  bestMovement: number | null;
}

function mergeOutcomesFromFeed(
  items: FeedItem[]
): { merged: MergedOutcome[]; sources: string[] } {
  const sourceSet = new Set<string>();
  const byName = new Map<string, MergedOutcome>();

  for (const item of items) {
    const data = item.data as FeedFuturesData;
    const src = data.source || "unknown";
    sourceSet.add(src);

    for (const outcome of data.top_outcomes) {
      const key = outcome.name.toLowerCase().trim();
      if (!byName.has(key)) {
        byName.set(key, {
          name: outcome.name,
          bySource: {},
          avgProbability: 0,
          bestMovement: null,
        });
      }
      const entry = byName.get(key)!;
      entry.bySource[src] = outcome.probability;
      // Track best movement across sources
      if (outcome.movement !== null && outcome.movement !== undefined) {
        if (entry.bestMovement === null || Math.abs(outcome.movement) > Math.abs(entry.bestMovement)) {
          entry.bestMovement = outcome.movement;
        }
      }
    }
  }

  // Compute average and sort
  for (const entry of byName.values()) {
    const probs = Object.values(entry.bySource).filter(
      (v): v is number => v !== null && v > 0
    );
    entry.avgProbability =
      probs.length > 0 ? probs.reduce((s, v) => s + v, 0) / probs.length : 0;
  }

  const merged = Array.from(byName.values()).sort(
    (a, b) => b.avgProbability - a.avgProbability
  );

  const sources = Array.from(sourceSet).sort((a, b) => {
    // Consistent ordering: Sportsbooks → Kalshi → Polymarket
    const order: Record<string, number> = { odds_api: 0, kalshi: 1, polymarket: 2 };
    return (order[a] ?? 3) - (order[b] ?? 3);
  });

  return { merged, sources };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface CombinedFeedCardProps {
  group: GroupedMarket;
}

export default function CombinedFeedCard({ group }: CombinedFeedCardProps) {
  const { items } = group;
  if (items.length === 0) return null;

  // Use the first item for shared metadata (name, category, etc.)
  const primaryData = items[0].data as FeedFuturesData;
  const catKey = primaryData.llm_sport_category ?? "";
  const catEmoji = catKey ? getEmojiForCategory(catKey) : "📊";
  const catName = catKey ? getNameForCategory(catKey) : "Futures";

  // Link to the first market's detail page
  const linkId = primaryData.id;

  // Merge outcomes across sources
  const { merged, sources } = mergeOutcomesFromFeed(items);
  const displayed = merged.slice(0, 5);
  const hasMore = merged.length > 5;

  // Best reason from any of the items
  const reason = items.find((i) => i.reason)?.reason || null;

  return (
    <Link href={`/futures/${linkId}`} aria-label={`${primaryData.name} - ${sources.length} sources`}>
      <article className="rounded-card border border-surface-border bg-surface-card hover:bg-surface-elevated transition-all cursor-pointer overflow-hidden">
        {/* Header */}
        <div className="px-3 pt-3 pb-2">
          <div className="flex items-center justify-between gap-2 mb-1">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-[11px] text-text-muted tracking-wide truncate">
                <span className="mr-0.5">{catEmoji}</span>
                {catName}
              </span>
            </div>
            <span className="text-[10px] bg-accent-futures/10 text-accent-futures px-1.5 py-0.5 rounded font-medium flex-shrink-0">
              {sources.length} sources
            </span>
          </div>
          <div className="text-sm font-medium text-text-primary line-clamp-2">
            {primaryData.name}
          </div>
          {reason && (
            <p className="text-xs text-text-secondary mt-0.5 line-clamp-2">
              {reason}
            </p>
          )}
        </div>

        {/* Source legend */}
        <div className="px-3 pb-1.5 flex items-center gap-3">
          {sources.map((src) => (
            <div key={src} className="flex items-center gap-1">
              <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: sourceHex(src) }} />
              <span className="text-[10px]" style={{ color: sourceHex(src) }}>
                {sourceLabel(src)}
              </span>
            </div>
          ))}
        </div>

        {/* Cross-source outcome comparison rows */}
        <div className="border-t border-surface-border/50">
          {displayed.map((outcome, i) => (
            <div
              key={outcome.name}
              className={`px-3 py-1.5 flex items-center gap-2 ${
                i < displayed.length - 1
                  ? "border-b border-surface-border/30"
                  : ""
              }`}
            >
              {/* Rank + name */}
              <span className="text-[10px] text-text-muted/50 w-4 flex-shrink-0">
                #{i + 1}
              </span>
              <span className="text-xs font-medium text-text-primary truncate flex-1 min-w-0">
                {outcome.name}
              </span>

              {/* Per-source probabilities */}
              <div className="flex items-center gap-2 flex-shrink-0">
                {sources.map((src) => {
                  const prob = outcome.bySource[src];
                  if (prob === null || prob === undefined) {
                    return (
                      <span
                        key={src}
                        className="w-10 text-right text-[10px] text-text-muted"
                      >
                        —
                      </span>
                    );
                  }
                  return (
                    <span
                      key={src}
                      className="w-10 text-right text-[11px] font-mono font-semibold"
                      style={{ color: sourceHex(src) }}
                    >
                      {formatProbability(prob)}
                    </span>
                  );
                })}
              </div>

              {/* Movement indicator */}
              {outcome.bestMovement !== null &&
                outcome.bestMovement !== 0 && (
                  <span
                    className={`text-[10px] font-medium flex-shrink-0 ${
                      outcome.bestMovement > 0
                        ? "text-accent-live"
                        : "text-accent-danger"
                    }`}
                  >
                    {outcome.bestMovement > 0 ? "+" : ""}
                    {(outcome.bestMovement * 100).toFixed(1)}%
                  </span>
                )}
            </div>
          ))}
        </div>

        {/* Footer */}
        {hasMore && (
          <div className="px-3 py-1.5 text-center text-[10px] text-text-muted border-t border-surface-border/50">
            +{merged.length - 5} more outcomes
          </div>
        )}
      </article>
    </Link>
  );
}
