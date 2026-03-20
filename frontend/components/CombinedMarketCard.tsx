"use client";

/**
 * CombinedMarketCard — displays a market group combining data from
 * multiple sources (Polymarket, Kalshi, Odds API) into a unified view.
 *
 * Used when markets from different sources share the same canonical
 * market key (e.g., "NBA Championship Winner" from all three sources).
 * Shows cross-source probability comparison and merged outcome list.
 */

import { motion } from "framer-motion";
import { fadeIn } from "@/lib/animations";

interface SourceOutcome {
  id: number;
  name: string;
  probability: number | null;
  american_odds?: number | null;
  source: string;
}

interface SourceMarket {
  id: number;
  name: string;
  source: string;
  external_id: string | null;
  status: string;
  outcome_count: number;
  outcomes: SourceOutcome[];
}

interface CombinedMarketCardProps {
  /** Group title (e.g., "NBA Championship Winner 2025-26") */
  title: string;
  /** Markets from different sources */
  markets: SourceMarket[];
  /** Maximum outcomes to show (default: 8) */
  maxOutcomes?: number;
}

function formatSource(source: string): string {
  const names: Record<string, string> = {
    odds_api: "Sportsbooks",
    kalshi: "Kalshi",
    polymarket: "Polymarket",
  };
  return names[source] || source;
}

function sourceColor(source: string): string {
  switch (source) {
    case "polymarket":
      return "text-blue-400";
    case "kalshi":
      return "text-green-400";
    case "odds_api":
      return "text-slate-300";
    default:
      return "text-gray-400";
  }
}

function sourceDot(source: string): string {
  switch (source) {
    case "polymarket":
      return "bg-blue-500";
    case "kalshi":
      return "bg-green-500";
    case "odds_api":
      return "bg-slate-400";
    default:
      return "bg-gray-500";
  }
}

/**
 * Merge outcomes across sources by name.
 * Returns an array of { name, sources: { [source]: probability } }
 */
function mergeOutcomes(markets: SourceMarket[]) {
  const merged = new Map<
    string,
    { name: string; bySource: Record<string, number | null> }
  >();

  for (const market of markets) {
    for (const o of market.outcomes) {
      const key = o.name.toLowerCase().trim();
      if (!merged.has(key)) {
        merged.set(key, { name: o.name, bySource: {} });
      }
      merged.get(key)!.bySource[market.source] = o.probability;
    }
  }

  // Sort by average probability descending
  return Array.from(merged.values()).sort((a, b) => {
    const avgA = avg(Object.values(a.bySource));
    const avgB = avg(Object.values(b.bySource));
    return avgB - avgA;
  });
}

function avg(values: (number | null)[]): number {
  const valid = values.filter((v): v is number => v !== null && v > 0);
  return valid.length > 0 ? valid.reduce((s, v) => s + v, 0) / valid.length : 0;
}

export default function CombinedMarketCard({
  title,
  markets,
  maxOutcomes = 8,
}: CombinedMarketCardProps) {
  if (!markets || markets.length === 0) return null;

  const sources = [...new Set(markets.map((m) => m.source))];
  const merged = mergeOutcomes(markets);
  const displayed = merged.slice(0, maxOutcomes);
  const hasMore = merged.length > maxOutcomes;

  return (
    <motion.div
      variants={fadeIn}
      initial="hidden"
      animate="visible"
      className="rounded-lg border border-[var(--surface-border)] bg-[var(--surface-card)] overflow-hidden"
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--surface-border)]">
        <h3 className="text-sm font-medium text-[var(--text-primary)]">
          {title}
        </h3>
        <div className="flex items-center gap-3 mt-1.5">
          {sources.map((src) => (
            <div key={src} className="flex items-center gap-1.5">
              <div className={`w-1.5 h-1.5 rounded-full ${sourceDot(src)}`} />
              <span className={`text-[10px] ${sourceColor(src)}`}>
                {formatSource(src)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Outcome rows */}
      <div className="divide-y divide-[var(--surface-border)]/50">
        {displayed.map((item) => (
          <div
            key={item.name}
            className="px-4 py-2.5 flex items-center gap-3 hover:bg-[var(--surface-elevated)]/50 transition-colors duration-150"
          >
            {/* Outcome name */}
            <div className="flex-1 text-sm text-[var(--text-primary)] truncate">
              {item.name}
            </div>

            {/* Probability per source */}
            <div className="flex items-center gap-3">
              {sources.map((src) => {
                const prob = item.bySource[src];
                if (prob === null || prob === undefined) {
                  return (
                    <div
                      key={src}
                      className="w-14 text-right text-xs text-[var(--text-muted)]"
                    >
                      —
                    </div>
                  );
                }
                return (
                  <div
                    key={src}
                    className={`w-14 text-right text-xs font-mono font-medium ${sourceColor(src)}`}
                  >
                    {(prob * 100).toFixed(0)}%
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      {hasMore && (
        <div className="px-4 py-2 text-center text-xs text-[var(--text-muted)] border-t border-[var(--surface-border)]/50">
          +{merged.length - maxOutcomes} more outcomes
        </div>
      )}
    </motion.div>
  );
}
