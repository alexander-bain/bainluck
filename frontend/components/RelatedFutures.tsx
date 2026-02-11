"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";
import { fetchRelatedFutures, formatProbability } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";

interface RelatedFuturesProps {
  eventId: number;
  homeTeam: string;
  awayTeam: string;
}

/** Tier labels for display */
const TIER_LABELS: Record<number, string> = {
  1: "Championship",
  2: "Conference",
  3: "Award",
  4: "Division",
  5: "Market",
};

/** Tier-based accent colors */
const TIER_COLORS: Record<number, string> = {
  1: "bg-amber-100 text-amber-700",
  2: "bg-blue-100 text-blue-700",
  3: "bg-purple-100 text-purple-700",
  4: "bg-slate-100 text-slate-600",
  5: "bg-slate-100 text-slate-500",
};

function MovementIndicator({ change }: { change: number | null | undefined }) {
  if (change === null || change === undefined || change === 0 || !Number.isFinite(change))
    return null;

  const isPositive = change > 0;
  const absChange = Math.abs(change * 100);

  return (
    <span
      className={`text-xs font-medium ${
        isPositive ? "text-emerald-600" : "text-red-500"
      }`}
    >
      {isPositive ? "+" : "-"}{absChange.toFixed(1)}%
    </span>
  );
}

function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;

  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Single related future row */
function FutureRow({ future }: { future: RelatedFuture }) {
  const tierLabel = future.market_tier ? TIER_LABELS[future.market_tier] : null;
  const tierColor = future.market_tier
    ? TIER_COLORS[future.market_tier] || TIER_COLORS[5]
    : TIER_COLORS[5];

  return (
    <Link
      href={`/futures/${future.market_id}`}
      className="block hover:bg-slate-50 -mx-2 px-2 py-1.5 rounded-lg transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        {/* Left: market info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
            {tierLabel && (
              <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${tierColor}`}>
                {tierLabel}
              </span>
            )}
            {future.relevance_reason && (
              <span className="text-[10px] text-silver">
                {future.relevance_reason}
              </span>
            )}
          </div>
          <div className="text-sm text-graphite truncate" title={future.market_name}>
            {future.market_name}
          </div>
          {future.rank !== null && (
            <div className="text-xs text-silver mt-0.5">
              Ranked #{future.rank} in market
            </div>
          )}
        </div>

        {/* Right: probability + movement */}
        <div className="text-right shrink-0">
          <div className="font-mono text-sm font-bold tabular-nums text-graphite">
            {formatProbability(future.probability)}
          </div>
          <MovementIndicator change={future.probability_change_24h} />
        </div>
      </div>
    </Link>
  );
}

/** Team section within related futures */
function TeamFuturesSection({
  teamName,
  futures,
  defaultExpanded,
}: {
  teamName: string;
  futures: RelatedFuture[];
  defaultExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const COLLAPSED_COUNT = 3;
  const hasMore = futures.length > COLLAPSED_COUNT;
  const displayFutures = expanded ? futures : futures.slice(0, COLLAPSED_COUNT);

  if (futures.length === 0) return null;

  // Short team name (last word, e.g. "Celtics")
  const shortName = teamName.split(" ").pop() || teamName;

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <h4 className="text-xs font-semibold text-slate uppercase tracking-wider">
          {shortName}
        </h4>
        <span className="text-xs text-silver">
          {futures.length} market{futures.length !== 1 ? "s" : ""}
        </span>
      </div>

      <div className="space-y-0.5">
        {displayFutures.map((future) => (
          <FutureRow key={future.outcome_id} future={future} />
        ))}
      </div>

      {hasMore && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-blue-600 hover:text-blue-700 mt-1 px-3"
        >
          {expanded ? "Show less" : `Show ${futures.length - COLLAPSED_COUNT} more`}
        </button>
      )}
    </div>
  );
}

/**
 * Related Futures section for the event detail page.
 * Shows championship, award, and other futures markets linked to the teams in this event.
 */
export default function RelatedFutures({
  eventId,
  homeTeam,
  awayTeam,
}: RelatedFuturesProps) {
  const { data, error, isLoading } = useSWR<RelatedFuturesResponse>(
    ["related-futures", eventId],
    () => fetchRelatedFutures(eventId),
    {
      revalidateOnFocus: false,
      dedupingInterval: 300000, // 5 min — futures update hourly
    }
  );

  // Don't render anything while loading or if no data
  if (isLoading) {
    return null; // Don't show loading state at the bottom of the page
  }

  if (error || !data || data.total_count === 0) {
    return null; // Silently hide if no related futures
  }

  const { home_team_futures, away_team_futures } = data;

  // Find the most recent update across all futures for the staleness line
  const allFutures = [...home_team_futures, ...away_team_futures];
  const lastUpdated = allFutures
    .filter((f) => f.last_updated)
    .sort((a, b) => new Date(b.last_updated!).getTime() - new Date(a.last_updated!).getTime())[0];

  return (
    <div className="bg-white rounded-card shadow-card p-4 sm:p-5">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-slate">
          Bigger Picture
        </h3>
        {lastUpdated?.last_updated && (
          <span className="text-[11px] text-silver">
            Updated {formatRelativeTime(lastUpdated.last_updated)}
          </span>
        )}
      </div>

      <div className="space-y-3">
        <TeamFuturesSection
          teamName={homeTeam}
          futures={home_team_futures}
          defaultExpanded={home_team_futures.length <= 4}
        />
        <TeamFuturesSection
          teamName={awayTeam}
          futures={away_team_futures}
          defaultExpanded={away_team_futures.length <= 4}
        />
      </div>
    </div>
  );
}
