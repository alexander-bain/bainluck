"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import type { RelatedFuture, RelatedFuturesResponse } from "@/lib/types";
import { fetchRelatedFutures, formatProbability } from "@/lib/api";

interface RelatedFuturesProps {
  eventId: number;
  homeTeam: string;
  awayTeam: string;
  homeTeamColor?: string;
  awayTeamColor?: string;
  homeTeamLogo?: string;
  awayTeamLogo?: string;
}

/** Tier display config */
const TIER_CONFIG: Record<number, { label: string; icon: string }> = {
  1: { label: "Championship", icon: "🏆" },
  2: { label: "Conference", icon: "🏅" },
  3: { label: "Award", icon: "⭐" },
  4: { label: "Division", icon: "📊" },
  5: { label: "Market", icon: "📈" },
};

/** Format American odds */
function formatOdds(odds: number | null | undefined): string {
  if (odds === null || odds === undefined) return "";
  return odds > 0 ? `+${odds}` : `${odds}`;
}

/** Probability bar component — visual weight for the odds */
function ProbBar({ probability, color }: { probability: number | null; color: string }) {
  if (probability === null || probability === undefined) return null;
  // Scale: 50% probability = full bar (futures rarely exceed 50%)
  const pct = Math.min(100, (probability / 0.5) * 100);
  return (
    <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden mt-1">
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{
          width: `${Math.max(2, pct)}%`,
          backgroundColor: color || "#6B7280",
          opacity: 0.7,
        }}
      />
    </div>
  );
}

/** Movement indicator with arrow */
function Movement({ change }: { change: number | null | undefined }) {
  if (change === null || change === undefined || change === 0 || !Number.isFinite(change))
    return null;

  const isUp = change > 0;
  const abs = Math.abs(change * 100);

  return (
    <span
      className={`inline-flex items-center gap-0.5 text-xs font-medium ${
        isUp ? "text-emerald-600" : "text-red-500"
      }`}
    >
      <svg width="10" height="10" viewBox="0 0 10 10" className={isUp ? "" : "rotate-180"}>
        <path d="M5 2L8 6H2L5 2Z" fill="currentColor" />
      </svg>
      {abs.toFixed(1)}%
    </span>
  );
}

/** Single related future row — clean and compact */
function FutureRow({
  future,
  teamColor,
  teamName,
}: {
  future: RelatedFuture;
  teamColor: string;
  teamName: string;
}) {
  const tier = future.market_tier ? TIER_CONFIG[future.market_tier] : null;

  // Check if outcome name is different from team name (player outcome)
  const isPlayerOutcome =
    future.outcome_name &&
    !future.outcome_name.toLowerCase().includes(teamName.split(" ").pop()?.toLowerCase() || "___");

  return (
    <Link
      href={`/futures/${future.market_id}`}
      className="block group -mx-3 px-3 py-2 rounded-lg hover:bg-slate-50/80 transition-colors"
    >
      {/* Market info line */}
      <div className="flex items-center gap-1.5 mb-0.5">
        {tier && (
          <span className="text-[10px]" title={tier.label}>
            {tier.icon}
          </span>
        )}
        <span className="text-xs text-silver truncate">
          {future.market_name}
        </span>
      </div>

      {/* Player name (for MVP/award outcomes) */}
      {isPlayerOutcome && (
        <div className="text-sm text-graphite font-medium mb-0.5">
          {future.outcome_name}
        </div>
      )}

      {/* Main stats row */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-2 min-w-0">
          <span className="font-mono text-lg font-bold tabular-nums text-graphite">
            {formatProbability(future.probability)}
          </span>
          <Movement change={future.probability_change_24h} />
        </div>

        <span className="font-mono text-xs text-silver tabular-nums shrink-0">
          {formatOdds(future.american_odds)}
        </span>
      </div>

      {/* Probability bar */}
      <ProbBar probability={future.probability} color={teamColor} />
    </Link>
  );
}

/** Team section — color-accented, with logo */
function TeamSection({
  teamName,
  futures,
  teamColor,
  teamLogo,
  defaultExpanded,
}: {
  teamName: string;
  futures: RelatedFuture[];
  teamColor: string;
  teamLogo?: string;
  defaultExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const COLLAPSED_COUNT = 3;
  const hasMore = futures.length > COLLAPSED_COUNT;
  const displayFutures = expanded ? futures : futures.slice(0, COLLAPSED_COUNT);

  if (futures.length === 0) return null;

  const shortName = teamName.split(" ").pop() || teamName;

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ borderLeft: `3px solid ${teamColor || "#CBD5E1"}` }}
    >
      <div className="pl-3">
        {/* Team header */}
        <div className="flex items-center gap-2 py-2">
          {teamLogo && (
            <img
              src={teamLogo}
              alt=""
              width={20}
              height={20}
              loading="lazy"
              className="w-5 h-5 object-contain"
            />
          )}
          <h4 className="text-xs font-bold uppercase tracking-wider text-graphite">
            {shortName}
          </h4>
          <span className="text-[10px] text-silver">
            {futures.length} market{futures.length !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Future rows */}
        <div className="space-y-0">
          {displayFutures.map((future) => (
            <FutureRow
              key={future.outcome_id}
              future={future}
              teamColor={teamColor || "#6B7280"}
              teamName={teamName}
            />
          ))}
        </div>

        {/* Show more/less */}
        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-blue-600 hover:text-blue-700 font-medium py-1.5 px-3 transition-colors"
          >
            {expanded ? "Show less" : `+${futures.length - COLLAPSED_COUNT} more`}
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Related Futures — "Bigger Picture" section on event detail page.
 *
 * Shows championship, award, and other futures markets linked to the teams
 * in this event. Uses team colors, logos, and probability bars for visual impact.
 */
export default function RelatedFutures({
  eventId,
  homeTeam,
  awayTeam,
  homeTeamColor,
  awayTeamColor,
  homeTeamLogo,
  awayTeamLogo,
}: RelatedFuturesProps) {
  const { data, error, isLoading } = useSWR<RelatedFuturesResponse>(
    ["related-futures", eventId],
    () => fetchRelatedFutures(eventId),
    {
      revalidateOnFocus: false,
      dedupingInterval: 300000, // 5 min — futures update hourly
    }
  );

  if (isLoading || error || !data || data.total_count === 0) {
    return null;
  }

  const { home_team_futures, away_team_futures } = data;

  return (
    <div className="bg-white rounded-card shadow-card p-4 sm:p-5">
      <h3 className="text-sm font-semibold text-slate mb-3">
        Bigger Picture
      </h3>

      <div className="space-y-4">
        <TeamSection
          teamName={homeTeam}
          futures={home_team_futures}
          teamColor={homeTeamColor || "#6B7280"}
          teamLogo={homeTeamLogo}
          defaultExpanded={home_team_futures.length <= 5}
        />
        <TeamSection
          teamName={awayTeam}
          futures={away_team_futures}
          teamColor={awayTeamColor || "#6B7280"}
          teamLogo={awayTeamLogo}
          defaultExpanded={away_team_futures.length <= 5}
        />
      </div>
    </div>
  );
}
