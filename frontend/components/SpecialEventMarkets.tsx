"use client";

import { useMemo } from "react";
import type { GameMarketsResponse } from "@/lib/api";

interface SpecialEventMarketsProps {
  data: GameMarketsResponse;
  eventStatus?: string;
}

interface MarketCategory {
  title: string;
  subtitle: string;
  items: Array<{
    name: string;
    outcomes: Array<{ label: string; prob: number; source: string; sourceCount?: number }>;
  }>;
}

const CATEGORY_PATTERNS: Array<{ pattern: RegExp; category: string; subtitle: string }> = [
  { pattern: /first\s*(score|td|touchdown|goal|basket)/i, category: "Game Props", subtitle: "scoring & flow" },
  { pattern: /halftime|half\s*time|leader\s*at/i, category: "Game Props", subtitle: "scoring & flow" },
  { pattern: /overtime|OT\b|extra\s*time/i, category: "Game Props", subtitle: "scoring & flow" },
  { pattern: /coin\s*toss|gatorade|anthem|color/i, category: "Novelty Props", subtitle: "fun markets" },
  { pattern: /mvp|most\s*valuable/i, category: "MVP", subtitle: "game MVP probability" },
  { pattern: /double\s*double|triple\s*double/i, category: "Player Performance", subtitle: "statistical milestones" },
  { pattern: /both\s*teams?\s*(to\s*)?score/i, category: "Game Props", subtitle: "scoring & flow" },
];

function categorizeMarketName(name: string): { category: string; subtitle: string } {
  for (const { pattern, category, subtitle } of CATEGORY_PATTERNS) {
    if (pattern.test(name)) return { category, subtitle };
  }
  return { category: "Other Markets", subtitle: "additional markets" };
}

function PropMiniCard({ item }: { item: MarketCategory["items"][0] }) {
  const sorted = [...item.outcomes].sort((a, b) => b.prob - a.prob);
  const maxSourceCount = Math.max(...sorted.map((o) => o.sourceCount ?? 1));
  const sourceCount = maxSourceCount > 1 ? maxSourceCount : new Set(sorted.map((o) => o.source)).size;

  return (
    <div className="border border-surface-border rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="font-medium text-sm">{item.name}</div>
        {sourceCount > 1 && (
          <span className="text-[10px] font-semibold text-blue-600">{sourceCount}x</span>
        )}
      </div>
      <div className="space-y-1.5">
        {sorted.map((o, i) => (
          <div key={o.label} className="flex items-center gap-2">
            <div className={`text-xs flex-1 ${i === 0 ? "font-semibold" : "text-text-secondary"}`}>{o.label}</div>
            <div className="flex-1 h-1.5 rounded-full bg-surface-border overflow-hidden max-w-[140px]">
              <div
                className={`h-full rounded-full transition-all duration-500 ${i === 0 ? "bg-violet-400" : "bg-text-muted/40"}`}
                style={{ width: `${o.prob * 100}%` }}
              />
            </div>
            <span className="font-mono tabular-nums text-xs font-semibold w-10 text-right">
              {Math.round(o.prob * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function isRedundantWithMarketMaps(m: { market_name: string; outcome_name: string }): boolean {
  const lower = (m.market_name || "").toLowerCase();
  const outLower = (m.outcome_name || "").toLowerCase();
  if (lower.includes("spread") || lower.includes("handicap")) return true;
  if (lower.includes("total") && (outLower.includes("over") || outLower.includes("under"))) return true;
  if (lower.includes("moneyline") || lower.includes("winner") || lower.includes("match result")) return true;
  return false;
}

function findWinProbMarkets(markets: GameMarketsResponse["other"]): Set<string> {
  const byName = new Map<string, number[]>();
  for (const m of markets ?? []) {
    const name = m.market_name || "";
    if (!byName.has(name)) byName.set(name, []);
    if (m.probability != null) byName.get(name)!.push(m.probability);
  }
  const winProb = new Set<string>();
  for (const [name, probs] of byName) {
    if (probs.length === 2 && Math.abs(probs[0] + probs[1] - 1.0) < 0.1) {
      winProb.add(name);
    }
  }
  return winProb;
}

export default function SpecialEventMarkets({ data, eventStatus }: SpecialEventMarketsProps) {
  const winProbNames = findWinProbMarkets(data.other);
  const otherMarkets = (data.other ?? []).filter((m) => !isRedundantWithMarketMaps(m) && !winProbNames.has(m.market_name || ""));

  const categories = useMemo(() => {
    if (otherMarkets.length < 3) return [];

    const catMap = new Map<string, MarketCategory>();

    for (const m of otherMarkets) {
      const { category, subtitle } = categorizeMarketName(m.market_name || "");
      if (!catMap.has(category)) {
        catMap.set(category, { title: category, subtitle, items: [] });
      }

      const cat = catMap.get(category)!;
      const marketName = m.market_name || "Unknown";

      let existing = cat.items.find((item) => item.name === marketName);
      if (!existing) {
        existing = { name: marketName, outcomes: [] };
        cat.items.push(existing);
      }

      const label = m.outcome_name || "Unknown";
      const existingOutcome = existing.outcomes.find((o) => o.label === label);
      if (existingOutcome) {
        existingOutcome.sourceCount = (existingOutcome.sourceCount ?? 1) + 1;
        if (Math.abs((m.probability ?? 0) - 0.5) > Math.abs(existingOutcome.prob - 0.5)) {
          existingOutcome.prob = m.probability ?? 0;
        }
      } else {
        existing.outcomes.push({
          label,
          prob: m.probability ?? 0,
          source: m.source || "unknown",
          sourceCount: 1,
        });
      }
    }

    return [...catMap.values()]
      .filter((c) => c.items.length > 0)
      .sort((a, b) => {
        const order = ["MVP", "Game Props", "Player Performance", "Novelty Props", "Other Markets"];
        return (order.indexOf(a.title) === -1 ? 99 : order.indexOf(a.title)) -
               (order.indexOf(b.title) === -1 ? 99 : order.indexOf(b.title));
      });
  }, [otherMarkets]);

  if (categories.length === 0) return null;

  const totalItems = categories.reduce((a, c) => a + c.items.length, 0);

  return (
    <div>
      <div className="flex items-end justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold tracking-tight">Additional Markets</h3>
          <p className="text-sm text-text-secondary mt-0.5">
            {totalItems} markets grouped by category
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {categories.map((cat) => (
          <div key={cat.title} className="bg-surface-card border border-surface-border rounded-xl shadow-sm p-4">
            <div className="mb-3">
              <div className="font-semibold">{cat.title}</div>
              <div className="text-xs text-text-muted">{cat.subtitle}</div>
            </div>
            <div className="space-y-3">
              {cat.items.slice(0, 5).map((item) => (
                <PropMiniCard key={item.name} item={item} />
              ))}
              {cat.items.length > 5 && (
                <div className="text-center text-[10px] text-text-muted py-1">
                  +{cat.items.length - 5} more
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
