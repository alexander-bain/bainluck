"use client";

import { useState, useCallback } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetchFuturesBrowse, fetchFuturesCategories, formatProbability } from "@/lib/api";
import type { FuturesBrowseItem } from "@/lib/types";

const CATEGORY_EMOJI: Record<string, string> = {
  basketball: "🏀",
  football: "🏈",
  baseball: "⚾",
  hockey: "🏒",
  soccer: "⚽",
  golf: "⛳",
  tennis: "🎾",
  mma: "🥊",
  boxing: "🥊",
  motorsports: "🏎️",
  cricket: "🏏",
  rugby: "🏉",
  aussierules: "🏉",
  horse_racing: "🐎",
  olympics: "🏅",
  esports: "🎮",
  entertainment: "🎬",
  politics: "🏛️",
  crypto: "₿",
  economics: "📈",
  tech: "💻",
  weather: "🌤️",
  geopolitics: "🌍",
  culture: "🎭",
  lacrosse: "🥍",
  chess: "♟️",
  poker: "🃏",
  darts: "🎯",
  other: "🏆",
};

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function CategoryBrowser() {
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

  const { data: categoriesData, isLoading } = useSWR(
    "futures-categories",
    fetchFuturesCategories,
  );

  const toggleCategory = useCallback((key: string) => {
    setExpandedCategory(prev => prev === key ? null : key);
  }, []);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-16 bg-surface-card rounded-card border border-surface-border animate-pulse" />
        ))}
      </div>
    );
  }

  if (!categoriesData || categoriesData.categories.length === 0) return null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text-primary">
          Browse by category
        </h2>
        <span className="text-micro text-text-muted">
          {categoriesData.total.toLocaleString()} markets
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
        {categoriesData.categories.map((cat) => (
          <button
            key={cat.key}
            onClick={() => toggleCategory(cat.key)}
            className={`flex items-center gap-2 p-3 rounded-card border transition-all text-left ${
              expandedCategory === cat.key
                ? "bg-accent-brand/10 border-accent-brand/30 ring-1 ring-accent-brand/20"
                : "bg-surface-card border-surface-border hover:bg-surface-elevated hover:border-text-muted"
            }`}
          >
            <span className="text-lg">{CATEGORY_EMOJI[cat.key] ?? "🏆"}</span>
            <div className="min-w-0">
              <div className="text-sm font-medium text-text-primary truncate">
                {capitalize(cat.key)}
              </div>
              <div className="text-micro text-text-muted">{cat.count}</div>
            </div>
          </button>
        ))}
      </div>

      {expandedCategory && (
        <CategoryMarkets
          category={expandedCategory}
          onClose={() => setExpandedCategory(null)}
        />
      )}
    </div>
  );
}

function CategoryMarkets({ category, onClose }: { category: string; onClose: () => void }) {
  const [offset, setOffset] = useState(0);
  const [allItems, setAllItems] = useState<FuturesBrowseItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");

  const { data, isLoading } = useSWR(
    ["futures-browse", category, offset, searchQuery],
    () => fetchFuturesBrowse({
      category,
      q: searchQuery || undefined,
      limit: 20,
      offset,
    }),
    {
      onSuccess: (newData) => {
        if (offset === 0) {
          setAllItems(newData.items);
        } else {
          setAllItems(prev => [...prev, ...newData.items]);
        }
      },
    }
  );

  const handleLoadMore = () => {
    if (data?.has_more) {
      setOffset(prev => prev + 20);
    }
  };

  const handleSearch = (q: string) => {
    setSearchQuery(q);
    setOffset(0);
    setAllItems([]);
  };

  return (
    <div className="bg-surface-card rounded-card border border-surface-border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <span>{CATEGORY_EMOJI[category] ?? "🏆"}</span>
          {capitalize(category)}
          {data && (
            <span className="text-micro text-text-muted font-normal">
              ({data.total})
            </span>
          )}
        </h3>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-text-primary transition-colors p-1"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Search within category */}
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => handleSearch(e.target.value)}
        placeholder={`Search ${category}...`}
        className="w-full px-3 py-1.5 text-xs border border-surface-border rounded-lg bg-surface-deep focus:outline-none focus:border-accent-brand/40 transition-colors mb-3"
      />

      {/* Market list */}
      <div className="space-y-1.5">
        {allItems.map((market) => (
          <CompactMarketCard key={market.id} market={market} />
        ))}
      </div>

      {isLoading && (
        <div className="space-y-1.5 mt-1.5">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-12 bg-surface-border/30 rounded animate-pulse" />
          ))}
        </div>
      )}

      {!isLoading && allItems.length === 0 && (
        <p className="text-xs text-text-muted py-4 text-center">No markets found</p>
      )}

      {data?.has_more && !isLoading && (
        <button
          onClick={handleLoadMore}
          className="w-full mt-3 py-2 text-xs font-medium text-text-secondary hover:text-text-primary border border-surface-border rounded-lg hover:bg-surface-elevated transition-colors"
        >
          Load more ({data.total - allItems.length} remaining)
        </button>
      )}
    </div>
  );
}

function CompactMarketCard({ market }: { market: FuturesBrowseItem }) {
  const leader = market.top_outcomes[0];

  return (
    <Link href={`/futures/${market.id}`}>
      <div className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg hover:bg-surface-elevated transition-colors">
        <div className="flex-1 min-w-0">
          <div className="text-xs font-medium text-text-primary truncate">
            {market.name}
          </div>
          {leader && (
            <div className="text-[11px] text-text-muted truncate">
              {leader.name}
              {leader.probability !== null && (
                <span className="ml-1 font-mono font-bold text-text-secondary">
                  {formatProbability(leader.probability)}
                </span>
              )}
            </div>
          )}
        </div>
        <div className="flex-shrink-0 flex items-center gap-2">
          {leader?.movement !== null && leader?.movement !== undefined && leader.movement !== 0 && (
            <span className={`text-[10px] font-medium ${
              leader.movement > 0 ? "text-accent-live" : "text-accent-danger"
            }`}>
              {leader.movement > 0 ? "▲" : "▼"}
            </span>
          )}
          <span className="text-micro text-text-muted">
            {market.outcome_count}
          </span>
        </div>
      </div>
    </Link>
  );
}
