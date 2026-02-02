"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import useSWR from "swr";
import {
  fetchFuturesMarket,
  fetchFuturesHistory,
  formatProbability,
  formatAmericanOdds,
} from "@/lib/api";
import type { FuturesOutcome, FuturesOutcomeHistory } from "@/lib/types";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";

interface FuturesDetailPageProps {
  params: { id: string };
}

/**
 * Get emoji for sport category
 */
function getSportEmoji(sportKey: string | null): string {
  if (!sportKey) return "🏆";
  const key = sportKey.toLowerCase();
  if (key.includes("basketball") || key.includes("nba") || key.includes("ncaab")) return "🏀";
  if (key.includes("football") || key.includes("nfl") || key.includes("ncaaf")) return "🏈";
  if (key.includes("baseball") || key.includes("mlb")) return "⚾";
  if (key.includes("hockey") || key.includes("nhl")) return "🏒";
  if (key.includes("soccer") || key.includes("mls") || key.includes("epl") || key.includes("uefa")) return "⚽";
  if (key.includes("golf") || key.includes("pga")) return "⛳";
  if (key.includes("tennis") || key.includes("atp") || key.includes("wta")) return "🎾";
  if (key.includes("mma") || key.includes("ufc")) return "🥊";
  if (key.includes("nascar") || key.includes("f1") || key.includes("racing")) return "🏎️";
  return "🏆";
}

type SortField = "rank" | "probability" | "change" | "name";
type SortDirection = "asc" | "desc";

export default function FuturesDetailPage({ params }: FuturesDetailPageProps) {
  const marketId = parseInt(params.id, 10);
  const [sortField, setSortField] = useState<SortField>("rank");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [selectedOutcomes, setSelectedOutcomes] = useState<Set<number>>(new Set());
  const [showAllOutcomes, setShowAllOutcomes] = useState(false);

  const {
    data: market,
    error: marketError,
    isLoading: marketLoading,
    mutate: refreshMarket,
  } = useSWR(
    ["futures-market", marketId],
    () => fetchFuturesMarket(marketId),
    { refreshInterval: 60000 }
  );

  const {
    data: historyData,
    error: historyError,
    isLoading: historyLoading,
  } = useSWR(
    market ? ["futures-history", marketId] : null,
    () => fetchFuturesHistory(marketId, 168)
  );

  // Sort outcomes
  const sortedOutcomes = useMemo(() => {
    if (!market?.outcomes) return [];

    const sorted = [...market.outcomes].sort((a, b) => {
      let comparison = 0;

      switch (sortField) {
        case "rank":
          comparison = (a.rank ?? 999) - (b.rank ?? 999);
          break;
        case "probability":
          comparison = (b.probability ?? 0) - (a.probability ?? 0);
          break;
        case "change":
          const aChange = a.probability_change_24h ?? 0;
          const bChange = b.probability_change_24h ?? 0;
          comparison = Math.abs(bChange) - Math.abs(aChange);
          break;
        case "name":
          comparison = a.name.localeCompare(b.name);
          break;
      }

      return sortDirection === "asc" ? comparison : -comparison;
    });

    return sorted;
  }, [market?.outcomes, sortField, sortDirection]);

  // Limit displayed outcomes unless "show all" is enabled
  const displayedOutcomes = showAllOutcomes
    ? sortedOutcomes
    : sortedOutcomes.slice(0, 25);

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection(field === "name" ? "asc" : "desc");
    }
  };

  const toggleOutcomeSelection = (outcomeId: number) => {
    setSelectedOutcomes((prev) => {
      const next = new Set(prev);
      if (next.has(outcomeId)) {
        next.delete(outcomeId);
      } else {
        next.add(outcomeId);
      }
      return next;
    });
  };

  if (marketLoading) {
    return (
      <div className="py-12">
        <LoadingSpinner text="Loading market..." />
      </div>
    );
  }

  if (marketError || !market) {
    return (
      <ErrorMessage
        title="Market not found"
        message={marketError?.message || "Unable to load market details"}
        onRetry={() => refreshMarket()}
      />
    );
  }

  const sportEmoji = getSportEmoji(market.sport);
  const isResolved = market.status === "resolved";

  // Find the leader for highlighting
  const leader = sortedOutcomes[0];

  return (
    <div className="space-y-6">
      {/* Navigation */}
      <div className="flex items-center gap-2">
        <Link
          href="/futures"
          className="inline-flex items-center text-caption text-slate hover:text-graphite transition-colors"
        >
          <svg
            className="w-4 h-4 mr-1"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 19l-7-7 7-7"
            />
          </svg>
          Back to Futures
        </Link>
      </div>

      {/* Hero Section */}
      <div
        className={`rounded-card shadow-card p-6 ${
          isResolved
            ? "bg-slate-50 border border-slate-200"
            : "bg-white"
        }`}
      >
        {/* Sport badge */}
        <div className="flex items-center justify-between mb-4">
          {market.sport && (
            <span className="text-sm bg-slate/10 px-3 py-1 rounded-full flex items-center gap-2">
              <span className="text-lg">{sportEmoji}</span>
              <span className="text-slate font-medium">
                {market.sport_name || market.sport}
              </span>
            </span>
          )}

          {/* Status badge */}
          {isResolved && (
            <span className="flex items-center gap-1 bg-slate/20 text-slate px-3 py-1 rounded-full text-sm font-medium">
              Resolved
            </span>
          )}
        </div>

        {/* Market name */}
        <h1 className="text-title-1 text-graphite mb-2">{market.name}</h1>

        {market.description && (
          <p className="text-body text-slate mb-4">{market.description}</p>
        )}

        {/* Market info strip */}
        <div className="flex flex-wrap gap-4 text-sm text-slate">
          <span>
            {market.outcome_count} outcome{market.outcome_count !== 1 ? "s" : ""}
          </span>
          {market.source && <span>Source: {market.source}</span>}
          {market.resolution_date && (
            <span>
              Resolves:{" "}
              {new Date(market.resolution_date).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          )}
          {market.updated_at && (
            <span>
              Updated:{" "}
              {new Date(market.updated_at).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })}{" "}
              at{" "}
              {new Date(market.updated_at).toLocaleTimeString("en-US", {
                hour: "numeric",
                minute: "2-digit",
              })}
            </span>
          )}
        </div>

        {/* Current Leader */}
        {leader && (
          <div className="mt-6 pt-4 border-t border-mist">
            <div className="text-sm text-slate mb-2">Current Favorite</div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="w-8 h-8 flex items-center justify-center text-lg bg-amber-100 text-amber-700 rounded-full font-bold">
                  1
                </span>
                <span className="text-xl font-semibold text-graphite">
                  {leader.name}
                </span>
                {leader.is_winner && (
                  <span className="text-sm bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded font-medium">
                    Winner
                  </span>
                )}
              </div>
              <div className="text-right">
                <div className="font-mono text-2xl font-bold text-graphite">
                  {formatProbability(leader.probability)}
                </div>
                <div className="text-sm text-slate">
                  {formatAmericanOdds(leader.american_odds)}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Probability Chart (if history available) */}
      {historyData && historyData.outcomes.length > 0 && (
        <div className="bg-white rounded-card shadow-card p-6">
          <h2 className="text-title-3 font-semibold text-graphite mb-4 flex items-center gap-2">
            <span>📈</span>
            Probability Trends
          </h2>
          <FuturesChart
            historyData={historyData.outcomes}
            selectedOutcomes={selectedOutcomes}
            onToggleOutcome={toggleOutcomeSelection}
          />
        </div>
      )}

      {/* All Outcomes Table */}
      <div className="bg-white rounded-card shadow-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-title-3 font-semibold text-graphite flex items-center gap-2">
            <span>📊</span>
            All Outcomes
          </h2>
          {sortedOutcomes.length > 25 && (
            <button
              onClick={() => setShowAllOutcomes(!showAllOutcomes)}
              className="text-sm text-slate hover:text-graphite transition-colors"
            >
              {showAllOutcomes
                ? "Show less"
                : `Show all ${sortedOutcomes.length}`}
            </button>
          )}
        </div>

        {/* Sort controls */}
        <div className="flex gap-2 mb-4 flex-wrap">
          <SortButton
            label="Rank"
            field="rank"
            currentField={sortField}
            direction={sortDirection}
            onClick={() => toggleSort("rank")}
          />
          <SortButton
            label="Probability"
            field="probability"
            currentField={sortField}
            direction={sortDirection}
            onClick={() => toggleSort("probability")}
          />
          <SortButton
            label="24h Change"
            field="change"
            currentField={sortField}
            direction={sortDirection}
            onClick={() => toggleSort("change")}
          />
          <SortButton
            label="Name"
            field="name"
            currentField={sortField}
            direction={sortDirection}
            onClick={() => toggleSort("name")}
          />
        </div>

        {/* Outcomes list */}
        <div className="space-y-2">
          {displayedOutcomes.map((outcome, index) => (
            <OutcomeRow
              key={outcome.id}
              outcome={outcome}
              rank={outcome.rank ?? index + 1}
              isLeader={outcome.id === leader?.id}
              isSelected={selectedOutcomes.has(outcome.id)}
              onToggleSelect={() => toggleOutcomeSelection(outcome.id)}
              hasHistory={historyData?.outcomes.some(
                (h) => h.outcome_id === outcome.id
              ) ?? false}
            />
          ))}
        </div>

        {/* Show more button */}
        {!showAllOutcomes && sortedOutcomes.length > 25 && (
          <button
            onClick={() => setShowAllOutcomes(true)}
            className="w-full mt-4 py-2 text-sm text-slate hover:text-graphite border border-mist rounded-lg hover:bg-slate/5 transition-colors"
          >
            Show {sortedOutcomes.length - 25} more outcomes
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Sort button component
 */
function SortButton({
  label,
  field,
  currentField,
  direction,
  onClick,
}: {
  label: string;
  field: SortField;
  currentField: SortField;
  direction: SortDirection;
  onClick: () => void;
}) {
  const isActive = field === currentField;

  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors flex items-center gap-1 ${
        isActive
          ? "bg-gray-900 text-white"
          : "bg-gray-100 text-gray-600 hover:bg-gray-200"
      }`}
    >
      {label}
      {isActive && (
        <span>{direction === "asc" ? "↑" : "↓"}</span>
      )}
    </button>
  );
}

/**
 * Single outcome row
 */
function OutcomeRow({
  outcome,
  rank,
  isLeader,
  isSelected,
  onToggleSelect,
  hasHistory,
}: {
  outcome: FuturesOutcome;
  rank: number;
  isLeader: boolean;
  isSelected: boolean;
  onToggleSelect: () => void;
  hasHistory: boolean;
}) {
  const change = outcome.probability_change_24h;
  const rankChange = outcome.rank_change_24h;

  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-lg transition-colors ${
        isSelected
          ? "bg-blue-50 border border-blue-200"
          : isLeader
          ? "bg-amber-50 border border-amber-200"
          : "bg-slate/5 hover:bg-slate/10"
      }`}
    >
      {/* Selection checkbox (for chart) */}
      {hasHistory && (
        <button
          onClick={(e) => {
            e.preventDefault();
            onToggleSelect();
          }}
          className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
            isSelected
              ? "bg-blue-500 border-blue-500 text-white"
              : "border-slate/30 hover:border-slate"
          }`}
        >
          {isSelected && (
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clipRule="evenodd"
              />
            </svg>
          )}
        </button>
      )}

      {/* Rank */}
      <span
        className={`w-8 h-8 flex items-center justify-center text-sm rounded-full shrink-0 ${
          isLeader
            ? "bg-amber-100 text-amber-700 font-bold"
            : "bg-white text-slate border border-mist"
        }`}
      >
        {rank}
      </span>

      {/* Rank change indicator */}
      {rankChange !== null && rankChange !== 0 && (
        <span
          className={`text-xs shrink-0 ${
            rankChange < 0 ? "text-emerald-600" : "text-red-500"
          }`}
        >
          {rankChange < 0 ? `↑${Math.abs(rankChange)}` : `↓${rankChange}`}
        </span>
      )}

      {/* Name */}
      <div className="flex-1 min-w-0">
        <span
          className={`text-sm truncate block ${
            isLeader ? "font-semibold text-graphite" : "text-graphite"
          }`}
        >
          {outcome.name}
        </span>
        {outcome.is_winner && (
          <span className="text-xs text-emerald-600 font-medium">Winner</span>
        )}
      </div>

      {/* Opening vs Current comparison */}
      {outcome.opening_probability !== null && (
        <div className="text-xs text-slate text-right shrink-0">
          <div>
            Open: {formatProbability(outcome.opening_probability)}
          </div>
        </div>
      )}

      {/* 24h Change */}
      <div className="w-20 text-right shrink-0">
        {change !== null && change !== 0 ? (
          <span
            className={`text-xs font-medium px-2 py-0.5 rounded-full ${
              change > 0
                ? "bg-emerald-100 text-emerald-700"
                : "bg-red-100 text-red-600"
            }`}
          >
            {change > 0 ? "+" : ""}
            {(change * 100).toFixed(1)}%
          </span>
        ) : (
          <span className="text-xs text-silver">-</span>
        )}
      </div>

      {/* Current probability and odds */}
      <div className="text-right shrink-0">
        <div
          className={`font-mono text-base tabular-nums ${
            isLeader ? "font-bold text-graphite" : "font-semibold text-graphite"
          }`}
        >
          {formatProbability(outcome.probability)}
        </div>
        <div className="text-xs text-slate font-mono">
          {formatAmericanOdds(outcome.american_odds)}
        </div>
      </div>
    </div>
  );
}

/**
 * Simple line chart for futures probability trends
 */
function FuturesChart({
  historyData,
  selectedOutcomes,
  onToggleOutcome,
}: {
  historyData: FuturesOutcomeHistory[];
  selectedOutcomes: Set<number>;
  onToggleOutcome: (id: number) => void;
}) {
  // Color palette for chart lines
  const colors = [
    "#2563eb", // blue
    "#dc2626", // red
    "#16a34a", // green
    "#9333ea", // purple
    "#ea580c", // orange
    "#0891b2", // cyan
    "#be185d", // pink
    "#4f46e5", // indigo
  ];

  // Filter to selected outcomes, or show top 5 if none selected
  const displayedOutcomes = useMemo(() => {
    if (selectedOutcomes.size > 0) {
      return historyData.filter((o) => selectedOutcomes.has(o.outcome_id));
    }
    // Default to first 5 outcomes with history
    return historyData.slice(0, 5);
  }, [historyData, selectedOutcomes]);

  if (displayedOutcomes.length === 0) {
    return (
      <div className="h-48 flex items-center justify-center text-sm text-slate">
        Select outcomes below to see their probability trends
      </div>
    );
  }

  // Find time range and probability range
  let minTime = Infinity;
  let maxTime = -Infinity;
  let maxProb = 0;

  for (const outcome of displayedOutcomes) {
    for (const point of outcome.history) {
      const time = new Date(point.timestamp).getTime();
      if (time < minTime) minTime = time;
      if (time > maxTime) maxTime = time;
      if (point.probability !== null && point.probability > maxProb) {
        maxProb = point.probability;
      }
    }
  }

  // Add padding to max probability
  maxProb = Math.min(1, maxProb * 1.1);

  const chartWidth = 800;
  const chartHeight = 200;
  const padding = { top: 20, right: 20, bottom: 30, left: 50 };
  const innerWidth = chartWidth - padding.left - padding.right;
  const innerHeight = chartHeight - padding.top - padding.bottom;

  const xScale = (time: number) =>
    padding.left + ((time - minTime) / (maxTime - minTime)) * innerWidth;

  const yScale = (prob: number) =>
    padding.top + (1 - prob / maxProb) * innerHeight;

  return (
    <div className="space-y-4">
      {/* Chart */}
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          className="w-full min-w-[600px]"
          style={{ maxHeight: "250px" }}
        >
          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct) => (
            <g key={pct}>
              <line
                x1={padding.left}
                y1={yScale(maxProb * pct)}
                x2={chartWidth - padding.right}
                y2={yScale(maxProb * pct)}
                stroke="#e5e7eb"
                strokeDasharray="4"
              />
              <text
                x={padding.left - 8}
                y={yScale(maxProb * pct)}
                textAnchor="end"
                dominantBaseline="middle"
                className="text-xs fill-slate"
              >
                {Math.round(maxProb * pct * 100)}%
              </text>
            </g>
          ))}

          {/* Lines */}
          {displayedOutcomes.map((outcome, idx) => {
            const points = outcome.history
              .filter((p) => p.probability !== null)
              .map((p) => ({
                x: xScale(new Date(p.timestamp).getTime()),
                y: yScale(p.probability!),
              }));

            if (points.length < 2) return null;

            const pathD = points
              .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
              .join(" ");

            return (
              <path
                key={outcome.outcome_id}
                d={pathD}
                fill="none"
                stroke={colors[idx % colors.length]}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            );
          })}
        </svg>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3">
        {displayedOutcomes.map((outcome, idx) => (
          <button
            key={outcome.outcome_id}
            onClick={() => onToggleOutcome(outcome.outcome_id)}
            className="flex items-center gap-2 text-sm hover:opacity-80 transition-opacity"
          >
            <span
              className="w-3 h-3 rounded-full"
              style={{ backgroundColor: colors[idx % colors.length] }}
            />
            <span className="text-graphite">{outcome.name}</span>
          </button>
        ))}
      </div>

      {selectedOutcomes.size === 0 && (
        <p className="text-xs text-slate text-center">
          Showing top 5 outcomes. Check boxes below to compare specific outcomes.
        </p>
      )}
    </div>
  );
}
