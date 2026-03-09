"use client";

import { useMemo } from "react";
import { useParams, notFound } from "next/navigation";
import useSWR from "swr";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchPlayoffGrid, fetchMarchMadness } from "@/lib/api";
import { TOURNAMENT_TYPE_CONFIG } from "@/lib/marchMadnessData";
import TournamentChart from "@/components/TournamentChart";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import SeedHistory from "@/components/MarchMadness/SeedHistory";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import type {
  PlayoffGridResponse,
  ProgressionResponse,
  ProgressionStage,
  ProgressionParticipant,
} from "@/lib/types";
import "../march-madness.css";

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
    tournament_name: `NCAA ${data.season || ""} Tournament`.trim(),
    stages,
    participants,
  };
}

export default function MarchMadnessPage() {
  const params = useParams();
  const type = params?.type as string;

  usePageTracking({ pageType: "march_madness", pageTitle: `March Madness - ${type}` });
  useScrollDepth({ pageType: "march_madness" });
  useEngagementTime({ pageType: "march_madness" });

  const config = TOURNAMENT_TYPE_CONFIG[type as keyof typeof TOURNAMENT_TYPE_CONFIG];

  if (!config) {
    notFound();
  }

  // Fetch playoff grid for odds data
  const league = type === "womens" ? "WNCAAB" : "NCAAB";
  const {
    data: gridData,
    error: gridError,
    isLoading: gridLoading,
  } = useSWR(
    ["playoff-grid", "basketball", league],
    () => fetchPlayoffGrid("basketball", league, undefined, 64),
    { refreshInterval: 60000 }
  );

  // Fetch March Madness API for seed history (static data)
  const {
    data: mmData,
  } = useSWR(
    ["march-madness", config.apiType],
    () => fetchMarchMadness(config.apiType),
    { refreshInterval: 0 }  // Static data, no need to refresh
  );

  const progressionData = useMemo(() => {
    if (!gridData) return null;
    return toProgressionResponse(gridData);
  }, [gridData]);

  // Find the championship stage market ID for the chart
  const championshipMarketId = useMemo(() => {
    if (!gridData) return null;
    const champStage = gridData.stages.find((s) => s.key === "championship");
    return champStage?.market_ids?.[0] ?? null;
  }, [gridData]);

  return (
    <div className="mm-page">
      <div className="mm-content">
        {/* Hero */}
        <div className="mm-hero">
          <h1>{config.label}</h1>
          <p className="mm-hero-subtitle">
            Round-by-round championship odds from sportsbooks and prediction markets.
          </p>
          {/* Tournament type toggle */}
          <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 12 }}>
            <Link
              href="/march-madness/mens"
              className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
                type === "mens"
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                  : "bg-white/5 text-white/50 border border-white/10 hover:border-white/20"
              }`}
            >
              🏀 Men&apos;s
            </Link>
            <Link
              href="/march-madness/womens"
              className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
                type === "womens"
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                  : "bg-white/5 text-white/50 border border-white/10 hover:border-white/20"
              }`}
            >
              🏀 Women&apos;s
            </Link>
          </div>
        </div>

        {/* Loading state */}
        {gridLoading && <SkeletonGrid count={6} />}

        {/* Error state */}
        {gridError && (
          <ErrorMessage message="Failed to load tournament odds. Please try again." />
        )}

        {/* Championship odds trend chart */}
        {championshipMarketId && (
          <div className="mm-section">
            <div className="mm-section-header">
              <h2 className="mm-section-title">Championship Odds Trend</h2>
            </div>
            <TournamentChart
              marketId={championshipMarketId}
              hours={336}
              height={280}
              hideLeaderboard
              className="bg-white/[0.03] rounded-xl border border-white/10 p-3"
            />
          </div>
        )}

        {/* Round-by-round odds grid */}
        {progressionData && progressionData.participants.length > 0 && (
          <>
            <div className="mm-court-line" />
            <div className="mm-section">
              <div className="mm-section-header">
                <h2 className="mm-section-title">Tournament Odds Grid</h2>
                <span className="mm-section-badge">{progressionData.participants.length} teams</span>
              </div>
              <TournamentProgressionTable
                data={progressionData}
                showLogos
                pageType="march_madness"
                className="bg-white/[0.03] rounded-xl border border-white/10 p-4"
              />
            </div>
          </>
        )}

        {/* Empty state */}
        {!gridLoading && !gridError && (!progressionData || progressionData.participants.length === 0) && (
          <div className="mm-section" style={{ textAlign: "center", padding: "48px 24px" }}>
            <p style={{ color: "var(--mm-text-dim)", fontSize: "1.1rem", marginBottom: 8 }}>
              No tournament odds available yet
            </p>
            <p style={{ color: "var(--mm-text-dim)", opacity: 0.6, fontSize: "0.875rem" }}>
              Odds will appear when sportsbooks and prediction markets publish NCAA tournament markets.
            </p>
          </div>
        )}

        {/* Seed History (static data from March Madness API) */}
        {mmData && mmData.seed_history.length > 0 && (
          <>
            <div className="mm-court-line" />
            <SeedHistory
              seedHistory={mmData.seed_history}
              notableUpsets={mmData.notable_upsets}
            />
          </>
        )}

        {/* Sources footer */}
        {gridData && gridData.sources.length > 0 && (
          <p style={{
            textAlign: "center",
            fontSize: "0.75rem",
            color: "var(--mm-text-dim)",
            opacity: 0.5,
            marginTop: 16,
          }}>
            {gridData.teams.length} teams · {gridData.stages.length} stage{gridData.stages.length !== 1 ? "s" : ""} ·{" "}
            Sources: {gridData.sources.map(s =>
              s === "odds_api" ? "Sportsbooks" : s === "kalshi" ? "Kalshi" : s === "polymarket" ? "Polymarket" : s
            ).join(", ")}
          </p>
        )}
      </div>
    </div>
  );
}
