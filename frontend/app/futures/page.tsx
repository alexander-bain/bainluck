"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetchFuturesMarkets, fetchFuturesMovers } from "@/lib/api";
import type { FuturesMarket, FuturesMover } from "@/lib/types";
import FuturesCard from "@/components/FuturesCard";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import { formatProbability } from "@/lib/api";
import { getEmojiForCategory, getNameForCategory } from "@/lib/sportCategories";

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
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("open");
  const [expandedSports, setExpandedSports] = useState<Set<string>>(new Set());

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
              className="text-caption text-slate hover:text-graphite transition-colors"
            >
              Home
            </Link>
            <span className="text-slate">/</span>
            <span className="text-caption text-graphite">Futures</span>
          </div>
          <h1 className="text-title-1 text-graphite flex items-center gap-2">
            <span>🏆</span>
            Futures Markets
          </h1>
          <p className="text-body text-slate mt-1">
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
                  ? "bg-gray-900 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
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
                <h2 className="text-title-3 font-semibold text-graphite">
                  Biggest Movers
                </h2>
                <span className="text-caption text-slate bg-mist/50 px-2 py-0.5 rounded">
                  24h
                </span>
              </div>
              <div className="bg-white rounded-card shadow-card p-4 overflow-x-auto">
                <div className="flex gap-4 min-w-max">
                  {movers.slice(0, 8).map((mover) => (
                    <MoverCard key={mover.outcome_id} mover={mover} />
                  ))}
                </div>
              </div>
            </section>
          )}

          {/* Markets Grid */}
          {markets.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-body text-slate mb-2">
                No {statusFilter === "all" ? "" : statusFilter} futures markets found
              </p>
              <p className="text-caption text-silver">
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
                    <h2 className="text-title-3 font-semibold text-graphite">
                      {group.sportName}
                    </h2>
                    <span className="text-caption text-slate bg-mist/50 px-2 py-0.5 rounded">
                      {group.markets.length}
                    </span>
                    <span className="ml-auto text-slate group-hover:text-graphite transition-colors">
                      {expandedSports.has(group.sport) ? (
                        <ChevronDown className="w-5 h-5" />
                      ) : (
                        <ChevronRight className="w-5 h-5" />
                      )}
                    </span>
                  </button>

                  {/* Markets Grid */}
                  {expandedSports.has(group.sport) && (
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      {group.markets.map((market) => (
                        <FuturesCard
                          key={market.id}
                          market={market}
                          showSport={false}
                        />
                      ))}
                    </div>
                  )}
                </section>
              ))}
            </div>
          )}

          {/* Market count */}
          {markets.length > 0 && (
            <p className="text-center text-caption text-silver pt-4">
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
      <div className="w-48 p-3 rounded-lg border border-mist hover:border-slate/30 hover:shadow-sm transition-all cursor-pointer bg-white">
        <div className="text-xs text-slate truncate mb-1">
          {mover.market_name || "Unknown Market"}
        </div>
        <div className="text-sm font-semibold text-graphite truncate mb-2">
          {mover.name}
        </div>
        <div className="flex items-center justify-between">
          <span className="font-mono text-sm font-bold text-graphite">
            {formatProbability(mover.current_probability)}
          </span>
          {change !== null && (
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                isPositive
                  ? "bg-emerald-100 text-emerald-700"
                  : "bg-red-100 text-red-600"
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
