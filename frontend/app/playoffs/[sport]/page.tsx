"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetchPlayoffGrid } from "@/lib/api";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import type {
  PlayoffGridResponse,
  ProgressionResponse,
  ProgressionStage,
  ProgressionParticipant,
} from "@/lib/types";

/** League configs: slug → API params + display info */
const LEAGUE_CONFIG: Record<
  string,
  { sport: string; league: string; name: string; emoji: string; conferences?: string[] }
> = {
  nba: { sport: "basketball", league: "NBA", name: "NBA Playoff Odds", emoji: "🏀", conferences: ["Eastern Conference", "Western Conference"] },
  nfl: { sport: "football", league: "NFL", name: "NFL Playoff Odds", emoji: "🏈", conferences: ["AFC", "NFC"] },
  nhl: { sport: "hockey", league: "NHL", name: "NHL Playoff Odds", emoji: "🏒", conferences: ["Eastern Conference", "Western Conference"] },
  mlb: { sport: "baseball", league: "MLB", name: "MLB Playoff Odds", emoji: "⚾", conferences: ["American League", "National League"] },
  ncaab: { sport: "basketball", league: "NCAAB", name: "NCAA Basketball Playoff Odds", emoji: "🏀" },
  ncaaf: { sport: "football", league: "NCAAF", name: "College Football Playoff Odds", emoji: "🏈" },
  soccer: { sport: "soccer", league: "", name: "Soccer Tournament Odds", emoji: "⚽" },
  golf: { sport: "golf", league: "", name: "Golf Tournament Odds", emoji: "⛳" },
};

const SOURCE_LABELS: Record<string, string> = {
  odds_api: "Sportsbooks",
  kalshi: "Kalshi",
  polymarket: "Polymarket",
};

/** Short display labels for conference filter buttons */
const CONF_SHORT: Record<string, string> = {
  "Eastern Conference": "East",
  "Western Conference": "West",
  "American League": "AL",
  "National League": "NL",
};

/** Transform PlayoffGridResponse into ProgressionResponse for TournamentProgressionTable */
function toProgressionResponse(data: PlayoffGridResponse): ProgressionResponse {
  const stages: ProgressionStage[] = data.stages.map((s) => ({
    key: s.key,
    label: s.label,
    order: s.order,
    market_id: s.market_ids.length > 0 ? s.market_ids[0] : null,
    market_name: null,
  }));

  const participants: ProgressionParticipant[] = data.teams.map((t) => {
    const probabilities: Record<string, number | null> = {};
    const changes_24h: Record<string, number | null> = {};
    const status: Record<string, "clinched" | "eliminated" | null> = {};

    for (const [stageKey, stageData] of Object.entries(t.stages)) {
      probabilities[stageKey] = stageData.probability;
      changes_24h[stageKey] = stageData.change_24h;
      status[stageKey] = stageData.status;
    }

    return {
      name: t.name,
      team_id: t.team_id,
      logo_url: t.logo_url,
      primary_color: t.primary_color,
      conference: t.conference,
      record: t.record,
      probabilities,
      changes_24h,
      status,
    };
  });

  return {
    sport: data.sport,
    tournament_name: `${data.league || data.sport} ${data.season || ""}`.trim(),
    stages,
    participants,
  };
}

export default function PlayoffGridPage({
  params,
}: {
  params: { sport: string };
}) {
  const slug = params.sport.toLowerCase();
  const config = LEAGUE_CONFIG[slug];
  const displayName = config?.name ?? `${slug.toUpperCase()} Playoff Odds`;
  const emoji = config?.emoji ?? "🏆";

  usePageTracking({ pageType: "playoff_grid", pageTitle: `${displayName} - Bain Luck` });
  useScrollDepth({ pageType: "playoff_grid" });
  useEngagementTime({ pageType: "playoff_grid" });

  const [conferenceFilter, setConferenceFilter] = useState<string | null>(null);

  const {
    data: gridData,
    error: gridError,
    isLoading,
  } = useSWR(
    config ? ["playoff-grid", config.sport, config.league] : null,
    () => fetchPlayoffGrid(config!.sport, config!.league || undefined, undefined, 64),
    { refreshInterval: 60000 }
  );

  const progressionData = useMemo(() => {
    if (!gridData) return null;
    return toProgressionResponse(gridData);
  }, [gridData]);

  // Apply conference filter
  const filteredData = useMemo(() => {
    if (!progressionData) return null;
    if (!conferenceFilter) return progressionData;
    return {
      ...progressionData,
      participants: progressionData.participants.filter(
        (p) => p.conference === conferenceFilter
      ),
    };
  }, [progressionData, conferenceFilter]);

  // No config for this slug
  if (!config) {
    return (
      <main className="min-h-screen bg-background">
        <div className="max-w-6xl mx-auto px-4 py-8">
          <h1 className="text-2xl font-bold text-text-primary mb-4">League Not Found</h1>
          <p className="text-text-secondary mb-6">
            No playoff grid available for &quot;{slug}&quot;.
          </p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(LEAGUE_CONFIG).map(([key, cfg]) => (
              <Link
                key={key}
                href={`/playoffs/${key}`}
                className="px-4 py-2 rounded-lg bg-surface-card border border-white/10 text-text-primary hover:border-white/30 transition-colors"
              >
                {cfg.emoji} {cfg.league || cfg.sport}
              </Link>
            ))}
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-3xl">{emoji}</span>
            <h1 className="text-2xl font-bold text-text-primary">{displayName}</h1>
          </div>
          {gridData?.season && (
            <p className="text-sm text-text-secondary">
              {gridData.season} Season
            </p>
          )}
        </div>

        {/* League tabs */}
        <div className="flex gap-2 mb-4 overflow-x-auto pb-1 scrollbar-hide">
          {Object.entries(LEAGUE_CONFIG)
            .filter(([, cfg]) => ["basketball", "football", "hockey", "baseball"].includes(cfg.sport))
            .map(([key, cfg]) => (
              <Link
                key={key}
                href={`/playoffs/${key}`}
                className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
                  key === slug
                    ? "bg-blue-500/20 text-blue-400 border border-blue-500/40"
                    : "bg-surface-card text-text-secondary border border-white/10 hover:border-white/20"
                }`}
              >
                {cfg.emoji} {cfg.league}
              </Link>
            ))}
        </div>

        {/* Source badges + conference filter */}
        {gridData && (
          <div className="flex flex-wrap items-center gap-3 mb-4">
            {/* Sources */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-text-secondary">Sources:</span>
              {gridData.sources.map((source) => (
                <span
                  key={source}
                  className="text-xs px-2 py-0.5 rounded-full bg-surface-card border border-white/10 text-text-secondary"
                >
                  {SOURCE_LABELS[source] || source}
                </span>
              ))}
            </div>

            {/* Conference filter */}
            {config.conferences && config.conferences.length > 0 && (
              <div className="flex items-center gap-1.5 ml-auto">
                <button
                  onClick={() => setConferenceFilter(null)}
                  className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
                    !conferenceFilter
                      ? "bg-blue-500/20 text-blue-400 border border-blue-500/40"
                      : "bg-surface-card text-text-secondary border border-white/10 hover:border-white/20"
                  }`}
                >
                  All
                </button>
                {config.conferences.map((conf) => (
                  <button
                    key={conf}
                    onClick={() => setConferenceFilter(conferenceFilter === conf ? null : conf)}
                    className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
                      conferenceFilter === conf
                        ? "bg-blue-500/20 text-blue-400 border border-blue-500/40"
                        : "bg-surface-card text-text-secondary border border-white/10 hover:border-white/20"
                    }`}
                  >
                    {CONF_SHORT[conf] || conf}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Loading state */}
        {isLoading && <SkeletonGrid count={6} />}

        {/* Error state */}
        {gridError && (
          <ErrorMessage message="Failed to load playoff odds. Please try again." />
        )}

        {/* Empty state */}
        {!isLoading && !gridError && filteredData && filteredData.participants.length === 0 && (
          <div className="text-center py-12">
            <p className="text-text-secondary text-lg mb-2">No playoff odds available yet</p>
            <p className="text-text-secondary/60 text-sm">
              Odds will appear when sportsbooks and prediction markets publish {config.league || config.sport} playoff markets.
            </p>
          </div>
        )}

        {/* The grid */}
        {filteredData && filteredData.participants.length > 0 && (
          <TournamentProgressionTable
            data={filteredData}
            showLogos
            pageType="playoff_grid"
            className="bg-surface-card rounded-xl border border-white/10 p-4"
          />
        )}

        {/* Team count footer */}
        {gridData && gridData.teams.length > 0 && (
          <p className="text-xs text-text-secondary/50 mt-3 text-center">
            {gridData.teams.length} teams · {gridData.stages.length} stages ·{" "}
            {gridData.sources.length} source{gridData.sources.length !== 1 ? "s" : ""}
            {conferenceFilter && ` · Showing ${CONF_SHORT[conferenceFilter] || conferenceFilter}`}
          </p>
        )}
      </div>
    </main>
  );
}
