"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetchSharedTeamFutures } from "@/lib/api";
import type { TeamFutureItem } from "@/lib/types";
import { SkeletonGrid } from "@/components/SkeletonCard";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

export default function SharedMyOddsPage() {
  return (
    <Suspense fallback={<SkeletonGrid count={6} />}>
      <SharedMyOddsContent />
    </Suspense>
  );
}

function SharedMyOddsContent() {
  usePageTracking({ pageType: 'share', pageTitle: 'Shared Team Odds' });
  useScrollDepth({ pageType: 'share' });
  useEngagementTime({ pageType: 'share' });

  const searchParams = useSearchParams();
  const teamsParam = searchParams.get("teams");

  const teamIds = (teamsParam || "")
    .split(",")
    .map((s) => parseInt(s.trim(), 10))
    .filter((n) => !isNaN(n));

  const { data, error, isLoading } = useSWR(
    teamIds.length > 0 ? ["shared-team-futures", ...teamIds] : null,
    () => fetchSharedTeamFutures(teamIds, 50),
  );

  if (!teamsParam || teamIds.length === 0) {
    return (
      <div className="max-w-lg mx-auto text-center py-16 px-4">
        <h1 className="text-lg font-semibold text-text-primary mb-2">
          Invalid share link
        </h1>
        <p className="text-sm text-text-secondary mb-6">
          This link is missing team information.
        </p>
        <Link
          href="/"
          className="text-sm text-accent-brand font-medium hover:opacity-80"
        >
          Go to homepage
        </Link>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-10 bg-surface-elevated rounded animate-pulse" />
        <SkeletonGrid count={6} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-lg mx-auto text-center py-16 px-4">
        <h1 className="text-lg font-semibold text-text-primary mb-2">
          Couldn&apos;t load odds
        </h1>
        <p className="text-sm text-text-secondary mb-6">
          {error.message}
        </p>
        <Link
          href="/"
          className="text-sm text-accent-brand font-medium hover:opacity-80"
        >
          Go to homepage
        </Link>
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <div className="max-w-lg mx-auto text-center py-16 px-4">
        <h1 className="text-lg font-semibold text-text-primary mb-2">
          No futures found
        </h1>
        <p className="text-sm text-text-secondary mb-6">
          No open futures markets match these teams right now.
        </p>
        <Link
          href="/"
          className="text-sm text-accent-brand font-medium hover:opacity-80"
        >
          Go to homepage
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      {/* Header with team logos */}
      <div>
        <div className="flex items-center gap-2 flex-wrap mb-1">
          {data.teams.map((team) => (
            <div key={team.id} className="flex items-center gap-1.5">
              {team.logo_small ? (
                <img
                  src={team.logo_small}
                  alt={team.name}
                  className="w-5 h-5 object-contain"
                />
              ) : (
                <div
                  className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold text-white"
                  style={{ backgroundColor: team.primary_color || "#666" }}
                >
                  {(team.name || "?")[0]}
                </div>
              )}
              <span className="text-sm text-text-secondary">{team.name}</span>
            </div>
          ))}
        </div>
        <h1 className="text-xl font-bold text-text-primary">
          {data.teams.length === 1
            ? `${data.teams[0].name} Odds`
            : "Teams\u2019 Odds"}
        </h1>
        <p className="text-xs text-text-muted mt-0.5">
          Live odds from sportsbooks &amp; prediction markets
        </p>
      </div>

      {/* Futures list */}
      <div className="space-y-1">
        {data.items.map((item) => (
          <SharedFutureRow key={`${item.market_id}-${item.outcome_id}`} item={item} />
        ))}
      </div>

      {/* CTA */}
      <div className="text-center py-8 border-t border-border-subtle">
        <p className="text-sm text-text-secondary mb-3">
          Track your own teams&apos; odds
        </p>
        <Link
          href="/"
          className="inline-block px-6 py-2.5 bg-text-primary text-surface-deep rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
        >
          bainluck.com
        </Link>
      </div>
    </div>
  );
}

function SharedFutureRow({ item }: { item: TeamFutureItem }) {
  const prob = item.probability;
  const change = item.probability_change_24h;
  const probStr = prob !== null ? `${Math.round(prob * 100)}%` : "-";

  let changeStr = "";
  let changeColor = "text-text-muted";
  if (change !== null && change !== 0) {
    const sign = change > 0 ? "+" : "";
    changeStr = `${sign}${(change * 100).toFixed(1)}%`;
    changeColor = change > 0 ? "text-green-500" : "text-red-500";
  }

  const marketName = (item.market_name || "")
    .replace(/\s*Winner\s*$/i, "")
    .replace(/\s*20\d{2}(-\d{2})?$/i, "");

  return (
    <Link
      href={`/futures/${item.market_id}`}
      className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-surface-elevated transition-colors"
    >
      {/* Team logo */}
      <div className="w-7 h-7 flex-shrink-0">
        {item.matched_team.logo_small ? (
          <img
            src={item.matched_team.logo_small}
            alt={item.matched_team.name}
            className="w-7 h-7 object-contain"
          />
        ) : (
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold text-white"
            style={{ backgroundColor: item.matched_team.primary_color || "#666" }}
          >
            {(item.matched_team.name || "?")[0]}
          </div>
        )}
      </div>

      {/* Market name */}
      <div className="flex-1 min-w-0">
        <p className="text-sm text-text-primary truncate">
          {marketName}
        </p>
        <p className="text-[11px] text-text-muted truncate">
          {item.outcome_name}
        </p>
      </div>

      {/* Probability */}
      <div className="text-right flex-shrink-0">
        <p className="text-sm font-semibold text-text-primary font-mono tabular-nums">
          {probStr}
        </p>
        {changeStr && (
          <p className={`text-[11px] font-medium ${changeColor} font-mono tabular-nums`}>
            {changeStr}
          </p>
        )}
      </div>
    </Link>
  );
}
