"use client";

import Link from "next/link";
import type { FuturesMarket, FuturesOutcome } from "@/lib/types";
import { formatProbability, formatAmericanOdds } from "@/lib/api";

interface FuturesCardProps {
  market: FuturesMarket;
  showSport?: boolean;
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

/**
 * Format sport name for display
 */
function formatSportName(sportKey: string | null, sportName: string | null): string {
  if (sportName) return sportName;
  if (!sportKey) return "Sports";
  // Convert key like "basketball_nba_championship_winner" to "NBA Championship"
  return sportKey
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Movement indicator component
 */
function MovementIndicator({ change }: { change: number | null }) {
  if (change === null || change === 0) return null;

  const isPositive = change > 0;
  const absChange = Math.abs(change * 100);

  return (
    <span
      className={`text-xs font-medium ${
        isPositive ? "text-emerald-600" : "text-red-500"
      }`}
    >
      {isPositive ? "↑" : "↓"} {absChange.toFixed(1)}%
    </span>
  );
}

/**
 * Futures Market Card
 * Displays a futures market with top outcomes and probabilities
 */
export default function FuturesCard({
  market,
  showSport = true,
}: FuturesCardProps) {
  const outcomes = market.top_outcomes || market.outcomes || [];
  const topOutcomes = outcomes.slice(0, 5);
  const sportEmoji = getSportEmoji(market.sport);
  const isResolved = market.status === "resolved";

  // Find the leader
  const leader = topOutcomes[0];

  return (
    <Link href={`/futures/${market.id}`} className="h-full">
      <div
        className={`h-full flex flex-col rounded-card shadow-card p-4 hover:shadow-card-hover transition-all cursor-pointer ${
          isResolved
            ? "bg-slate-50 border border-slate-200"
            : "bg-white border border-mist"
        }`}
      >
        {/* Header */}
        <div className="flex justify-between items-start mb-3">
          <div className="flex items-center gap-2 flex-wrap flex-1 min-w-0">
            {showSport && market.sport && (
              <span className="text-sm bg-slate/10 px-2 py-0.5 rounded-full flex items-center gap-1 shrink-0">
                <span>{sportEmoji}</span>
                <span className="text-slate font-medium truncate max-w-[100px]">
                  {formatSportName(market.sport, market.sport_name)}
                </span>
              </span>
            )}
            {market.category && (
              <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full shrink-0">
                {market.category}
              </span>
            )}
          </div>

          {/* Status Badge */}
          <div className="flex items-center gap-1.5 shrink-0">
            {isResolved && (
              <span className="flex items-center gap-1 bg-slate/10 text-slate px-2 py-0.5 rounded-full text-xs font-medium">
                Resolved
              </span>
            )}
            {market.outcome_count > 0 && (
              <span className="text-xs text-silver">
                {market.outcome_count} outcomes
              </span>
            )}
          </div>
        </div>

        {/* Market Name */}
        <h3 className="text-base font-semibold text-graphite mb-3 line-clamp-2">
          {market.name}
        </h3>

        {/* Top Outcomes */}
        <div className="space-y-2 flex-grow">
          {topOutcomes.map((outcome, index) => (
            <OutcomeRow
              key={outcome.id}
              outcome={outcome}
              rank={index + 1}
              isLeader={index === 0}
              isResolved={isResolved}
            />
          ))}

          {outcomes.length === 0 && (
            <div className="text-sm text-slate text-center py-4">
              No outcomes available
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-3 pt-3 border-t border-mist/50 flex justify-between items-center">
          <div className="text-xs text-slate">
            {market.source && (
              <span>Source: {market.source}</span>
            )}
          </div>
          {market.updated_at && (
            <span className="text-xs text-silver">
              Updated {formatRelativeTime(market.updated_at)}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}

/**
 * Single outcome row within the card
 */
function OutcomeRow({
  outcome,
  rank,
  isLeader,
  isResolved,
}: {
  outcome: FuturesOutcome;
  rank: number;
  isLeader: boolean;
  isResolved: boolean;
}) {
  const movement = outcome.movement ?? outcome.probability_change_24h;

  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2 flex-1 min-w-0">
        {/* Rank indicator */}
        <span
          className={`w-5 h-5 flex items-center justify-center text-xs rounded-full shrink-0 ${
            isLeader
              ? "bg-amber-100 text-amber-700 font-semibold"
              : "bg-slate/10 text-slate"
          }`}
        >
          {rank}
        </span>

        {/* Name */}
        <span
          className={`text-sm truncate ${
            isLeader ? "font-semibold text-graphite" : "text-slate"
          }`}
        >
          {outcome.name}
        </span>

        {/* Winner badge */}
        {outcome.is_winner && (
          <span className="text-xs bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded shrink-0">
            Winner
          </span>
        )}
      </div>

      {/* Probability and movement */}
      <div className="flex items-center gap-2 shrink-0">
        <MovementIndicator change={movement} />
        <span
          className={`font-mono text-sm tabular-nums ${
            isLeader ? "font-bold text-graphite" : "text-slate"
          }`}
        >
          {formatProbability(outcome.probability)}
        </span>
      </div>
    </div>
  );
}

/**
 * Format relative time (e.g., "2h ago", "3d ago")
 */
function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}
