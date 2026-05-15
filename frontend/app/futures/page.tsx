"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetchFuturesMarkets, fetchFuturesMovers, fetchFuturesGroups } from "@/lib/api";
import type { FuturesMarket, FuturesMover, FuturesGroupSummary } from "@/lib/types";
import FuturesCard from "@/components/FuturesCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import { formatProbability } from "@/lib/api";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import {
  getEmojiForCategory,
  getNameForCategory,
  groupBySubcategory,
  SUBCATEGORY_THRESHOLD,
} from "@/lib/sportCategories";

type StatusFilter = "open" | "resolved" | "all";

const STATUS_FILTER_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "resolved", label: "Resolved" },
  { value: "all", label: "All" },
];

interface SportGroup {
  sport: string;
  sportName: string;
  emoji: string;
  markets: FuturesMarket[];
}

export default function FuturesPage() {
  usePageTracking({ pageType: 'futures', pageTitle: 'Championship & Futures Odds' });
  useScrollDepth({ pageType: 'futures' });
  useEngagementTime({ pageType: 'futures' });

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("open");
  const [expandedSports, setExpandedSports] = useState<Set<string>>(new Set());
  const [expandedSubcategories, setExpandedSubcategories] = useState<Set<string>>(new Set());

  const {
    data: marketsData,
    error: marketsError,
    isLoading: marketsLoading,
    mutate: refreshMarkets,
  } = useSWR(
    ["futures", statusFilter],
    () => fetchFuturesMarkets({ status: statusFilter, limit: 100 }),
    { refreshInterval: 60000, keepPreviousData: true, revalidateOnFocus: false }
  );

  const {
    data: moversData,
    error: moversError,
    isLoading: moversLoading,
  } = useSWR("futures-movers", () => fetchFuturesMovers(24, 10));

  // Multi-source / grouped markets
  const { data: groupsData } = useSWR(
    statusFilter === "open" ? "futures-groups" : null,
    () => fetchFuturesGroups({ limit: 20 }),
    { revalidateOnFocus: false }
  );
  const multiSourceGroups = (groupsData?.groups ?? []).filter(
    (g) => g.sources.length >= 2
  );

  // Group markets by sport
  const sportGroups = useMemo((): SportGroup[] => {
    const markets = marketsData?.markets ?? [];
    const groups = new Map<string, SportGroup>();

    for (const market of markets) {
      const sport = market.sport || market.llm_sport_category || "other";
      const sportName = market.sport_name || getNameForCategory(sport);

      if (!groups.has(sport)) {
        groups.set(sport, {
          sport,
          sportName,
          emoji: getEmojiForCategory(sport),
          markets: [],
        });
      }

      groups.get(sport)!.markets.push(market);
    }

    // Sort groups by number of markets
    return Array.from(groups.values()).sort(
      (a, b) => b.markets.length - a.markets.length
    );
  }, [marketsData?.markets]);

  const toggleSportExpand = (sport: string) => {
    setExpandedSports((prev) => {
      const next = new Set(prev);
      if (next.has(sport)) {
        next.delete(sport);
      } else {
        next.add(sport);
      }
      return next;
    });
  };

  const toggleSubcategory = (key: string) => {
    setExpandedSubcategories((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const markets = marketsData?.markets ?? [];
  const movers = moversData?.movers ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link
              href="/"
              className="text-caption text-text-secondary hover:text-text-primary transition-colors"
            >
              Home
            </Link>
            <span className="text-text-secondary">/</span>
            <span className="text-caption text-text-primary">Futures</span>
          </div>
          <h1 className="text-title-1 text-text-primary flex items-center gap-2">
            <span>🏆</span>
            Futures Markets
          </h1>
          <p className="text-body text-text-secondary mt-1">
            Championship winners, MVPs, and season-long betting markets
          </p>
        </div>

        {/* Status filter pills */}
        <div className="flex items-center gap-1">
          {STATUS_FILTER_OPTIONS.map((option) => (
            <button
              key={option.value}
              onClick={() => setStatusFilter(option.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                statusFilter === option.value
                  ? "bg-text-primary text-surface-deep"
                  : "bg-surface-elevated text-text-secondary hover:bg-surface-border"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error State */}
      {marketsError && (
        <ErrorMessage
          message={marketsError.message}
          onRetry={() => refreshMarkets()}
        />
      )}

      {/* Loading State */}
      {marketsLoading && (
        <div className="py-12">
          <LoadingSpinner text="Loading futures markets..." />
        </div>
      )}

      {/* Content */}
      {!marketsLoading && !marketsError && (
        <>
          {/* Movers Section */}
          {movers.length > 0 && statusFilter === "open" && (
            <section className="mb-8">
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">📈</span>
                <h2 className="text-title-3 font-semibold text-text-primary">
                  Biggest Movers
                </h2>
                <span className="text-caption text-text-secondary bg-surface-border/50 px-2 py-0.5 rounded">
                  24h
                </span>
              </div>
              <div className="bg-surface-card rounded-card shadow-card p-4 overflow-x-auto">
                <div className="flex gap-4 min-w-max">
                  {movers.slice(0, 8).map((mover) => (
                    <MoverCard key={mover.outcome_id} mover={mover} />
                  ))}
                </div>
              </div>
            </section>
          )}

          {/* Multi-Source Groups */}
          {multiSourceGroups.length > 0 && statusFilter === "open" && (
            <section className="mb-8">
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg">🔗</span>
                <h2 className="text-title-3 font-semibold text-text-primary">
                  Tracked Across Sources
                </h2>
                <span className="text-caption text-text-secondary bg-surface-border/50 px-2 py-0.5 rounded">
                  {multiSourceGroups.length}
                </span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {multiSourceGroups.map((group) => (
                  <GroupCard key={group.group_id} group={group} />
                ))}
              </div>
            </section>
          )}

          {/* Markets Grid */}
          {markets.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-body text-text-secondary mb-2">
                No {statusFilter === "all" ? "" : statusFilter} futures markets found
              </p>
              <p className="text-caption text-text-muted">
                {statusFilter !== "all"
                  ? "Try selecting a different status filter"
                  : "Check back later for new markets"}
              </p>
            </div>
          ) : (
            <div className="space-y-8">
              {sportGroups.map((group) => (
                <section key={group.sport}>
                  {/* Sport Header */}
                  <button
                    onClick={() => toggleSportExpand(group.sport)}
                    className="flex items-center gap-2 mb-4 w-full text-left group"
                  >
                    <span className="text-lg">{group.emoji}</span>
                    <h2 className="text-title-3 font-semibold text-text-primary">
                      {group.sportName}
                    </h2>
                    <span className="text-caption text-text-secondary bg-surface-border/50 px-2 py-0.5 rounded">
                      {group.markets.length}
                    </span>
                    <span className="ml-auto text-text-secondary group-hover:text-text-primary transition-colors">
                      {expandedSports.has(group.sport) ? (
                        <ChevronDown className="w-5 h-5" />
                      ) : (
                        <ChevronRight className="w-5 h-5" />
                      )}
                    </span>
                  </button>

                  {/* Markets Grid */}
                  {expandedSports.has(group.sport) && (() => {
                    const subcategories = groupBySubcategory(group.markets, group.sport);
                    const useSubcategories = group.markets.length >= SUBCATEGORY_THRESHOLD && subcategories.length > 1;

                    if (!useSubcategories) {
                      return (
                        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                          {group.markets.map((market) => (
                            <FuturesCard
                              key={market.id}
                              market={market}
                              showSport={false}
                            />
                          ))}
                        </div>
                      );
                    }

                    return (
                      <div className="space-y-3">
                        {subcategories.map((sub) => {
                          const subKey = `${group.sport}:${sub.key}`;
                          const isSubExpanded = expandedSubcategories.has(subKey);

                          return (
                            <div key={subKey}>
                              <button
                                onClick={() => toggleSubcategory(subKey)}
                                className="flex items-center gap-2 mb-2 w-full text-left group"
                              >
                                <span className="text-text-secondary group-hover:text-text-primary transition-colors">
                                  {isSubExpanded ? (
                                    <ChevronDown className="w-4 h-4" />
                                  ) : (
                                    <ChevronRight className="w-4 h-4" />
                                  )}
                                </span>
                                <h3 className="text-body font-medium text-text-primary">
                                  {sub.displayName}
                                </h3>
                                <span className="text-caption text-text-muted">
                                  {sub.markets.length} market{sub.markets.length !== 1 ? "s" : ""}
                                </span>
                              </button>
                              {isSubExpanded && (
                                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 ml-6">
                                  {sub.markets.map((market) => (
                                    <FuturesCard
                                      key={market.id}
                                      market={market}
                                      showSport={false}
                                    />
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    );
                  })()}
                </section>
              ))}
            </div>
          )}

          {/* Market count */}
          {markets.length > 0 && (
            <p className="text-center text-caption text-text-muted pt-4">
              {markets.length} market{markets.length !== 1 ? "s" : ""}
            </p>
          )}
        </>
      )}
    </div>
  );
}

/**
 * Mover card component for the horizontal scroller
 */
function MoverCard({ mover }: { mover: FuturesMover }) {
  const change = mover.probability_change_24h;
  const isPositive = change !== null && change > 0;

  return (
    <Link href={`/futures/${mover.market_id}`}>
      <div className="w-48 p-3 rounded-lg border border-surface-border hover:border-surface-border hover:shadow-card transition-all cursor-pointer bg-surface-card">
        <div className="text-xs text-text-secondary truncate mb-1">
          {mover.market_name || "Unknown Market"}
        </div>
        <div className="text-sm font-semibold text-text-primary truncate mb-2">
          {mover.name}
        </div>
        <div className="flex items-center justify-between">
          <span className="font-mono text-sm font-bold text-text-primary">
            {formatProbability(mover.current_probability)}
          </span>
          {change !== null && (
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                isPositive
                  ? "bg-emerald-500/15 text-emerald-400"
                  : "bg-red-500/15 text-red-400"
              }`}
            >
              {isPositive ? "+" : ""}
              {(change * 100).toFixed(1)}%
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}

/**
 * Group card linking to a multi-source grouped market
 */
function GroupCard({ group }: { group: FuturesGroupSummary }) {
  return (
    <Link href={`/futures/${group.representative_id}`}>
      <div className="p-3 rounded-lg border border-surface-border hover:border-accent-futures/30 hover:shadow-card transition-all cursor-pointer bg-surface-card">
        <div className="text-sm font-medium text-text-primary line-clamp-2 mb-2">
          {group.representative_name}
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            {group.sources.map((src) => (
              <span
                key={src}
                className={`text-[10px] px-1.5 py-0.5 rounded ${sourceStyle(src)}`}
              >
                {formatSourceLabel(src)}
              </span>
            ))}
          </div>
          <span className="text-caption text-text-muted">
            {group.market_count} market{group.market_count !== 1 ? "s" : ""}
          </span>
        </div>
      </div>
    </Link>
  );
}

function sourceStyle(source: string): string {
  switch (source) {
    case "polymarket":
      return "bg-blue-500/15 text-blue-400";
    case "kalshi":
      return "bg-green-500/15 text-green-400";
    case "odds_api":
      return "bg-slate-500/15 text-slate-300";
    default:
      return "bg-text-secondary/15 text-text-muted";
  }
}

function formatSourceLabel(source: string): string {
  const names: Record<string, string> = {
    odds_api: "Sportsbooks",
    kalshi: "Kalshi",
    polymarket: "Polymarket",
  };
  return names[source] || source;
}

/**
 * Chevron icons
 */
function ChevronDown({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}

function ChevronRight({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
    </svg>
  );
}
