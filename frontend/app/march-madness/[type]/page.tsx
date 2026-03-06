"use client";

import { useParams, notFound } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchMarchMadness } from "@/lib/api";
import { TOURNAMENT_TYPE_CONFIG, getCountdown, TOURNAMENT_DATES_2026 } from "@/lib/marchMadnessData";
import type { MarchMadnessResponse } from "@/lib/types";
import ChampionshipOdds from "@/components/MarchMadness/ChampionshipOdds";
import SeedHistory from "@/components/MarchMadness/SeedHistory";
import TitleMovers from "@/components/MarchMadness/TitleMovers";
import BracketView from "@/components/MarchMadness/BracketView";
import BracketGrid from "@/components/MarchMadness/BracketGrid";
import LiveCommandCenter from "@/components/MarchMadness/LiveCommandCenter";
import UpsetTracker from "@/components/MarchMadness/UpsetTracker";
import CinderellaWatch from "@/components/MarchMadness/CinderellaWatch";
import BracketBusterInsights from "@/components/MarchMadness/BracketBusterInsights";
import Link from "next/link";
import "../march-madness.css";

export default function MarchMadnessPage() {
  const params = useParams();
  const type = params?.type as string;

  usePageTracking({ pageType: "march_madness", pageTitle: `March Madness - ${type}` });
  useScrollDepth({ pageType: "march_madness" });
  useEngagementTime({ pageType: "march_madness" });

  const [data, setData] = useState<MarchMadnessResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bracketView, setBracketView] = useState<"bracket" | "grid">("bracket");

  const config = TOURNAMENT_TYPE_CONFIG[type as keyof typeof TOURNAMENT_TYPE_CONFIG];

  const loadData = useCallback(async () => {
    if (!config) return;
    try {
      const result = await fetchMarchMadness(config.apiType);
      setData(result);
      setError(null);
    } catch (err) {
      setError("Failed to load tournament data");
      console.error("March Madness fetch error:", err);
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    loadData();
    // Refresh every 60 seconds during tournament
    const interval = setInterval(loadData, 60000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (!config) {
    notFound();
  }

  // Countdown logic
  const selectionSundayCountdown = getCountdown(TOURNAMENT_DATES_2026.selection_sunday + "T23:00:00Z");
  const firstFourCountdown = getCountdown(TOURNAMENT_DATES_2026.first_four.start + "T23:00:00Z");

  const getCountdownDisplay = () => {
    if (!data) return { label: "Selection Sunday", value: selectionSundayCountdown };
    switch (data.tournament_state) {
      case "pre_selection":
        return { label: "Selection Sunday", value: selectionSundayCountdown };
      case "pre_tournament":
        return { label: "First Four tips off", value: firstFourCountdown };
      case "in_progress":
        return { label: "Tournament", value: "Live" };
      case "completed":
        return { label: "Tournament", value: "Complete" };
      default:
        return { label: "Selection Sunday", value: selectionSundayCountdown };
    }
  };

  const countdown = getCountdownDisplay();

  return (
    <div className="mm-page">
      <div className="mm-content">
        {/* Hero */}
        <div className="mm-hero">
          <h1>{config.label}</h1>
          <p className="mm-hero-subtitle">
            {data?.tournament_state === "in_progress"
              ? "The tournament is live. Follow every game, upset, and Cinderella."
              : "Championship futures, historical matchup data, and tournament preview."}
          </p>
          <div className="mm-countdown">
            {countdown.label} in{" "}
            <span className="mm-countdown-value">{countdown.value}</span>
          </div>
          {/* Make Your Picks CTA */}
          {data?.bracket && data.bracket.games.length > 0 && (
            <Link
              href={`/march-madness/${type}/picks`}
              style={{
                display: "inline-block",
                marginTop: 16,
                padding: "10px 28px",
                borderRadius: 8,
                background: "var(--mm-gold)",
                color: "#1a0e08",
                fontWeight: 700,
                fontSize: "0.875rem",
                textDecoration: "none",
                transition: "opacity 0.2s",
              }}
            >
              Make Your Picks
            </Link>
          )}
        </div>

        {/* Loading state */}
        {loading && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {[...Array(6)].map((_, i) => (
              <div key={i} className="mm-skeleton" style={{ height: 64 }} />
            ))}
          </div>
        )}

        {/* Error state */}
        {error && (
          <div style={{
            padding: 24,
            textAlign: "center",
            color: "var(--mm-text-dim)",
            borderRadius: 12,
            background: "var(--mm-card-bg)",
            border: "1px solid var(--mm-card-border)",
          }}>
            <p style={{ marginBottom: 12 }}>{error}</p>
            <button
              onClick={loadData}
              style={{
                padding: "8px 20px",
                borderRadius: 8,
                border: "1px solid var(--mm-wood-accent)",
                background: "transparent",
                color: "var(--mm-wood-pale)",
                cursor: "pointer",
              }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Main content */}
        {data && !loading && (
          <>
            {/* Championship Odds */}
            <ChampionshipOdds
              teams={data.championship_odds}
              almaMaterTeams={data.alma_mater_teams}
            />

            <div className="mm-court-line" />

            {/* Biggest Movers */}
            <TitleMovers movers={data.biggest_movers} />

            {data.biggest_movers.length > 0 && <div className="mm-court-line" />}

            {/* Seed History */}
            <SeedHistory
              seedHistory={data.seed_history}
              notableUpsets={data.notable_upsets}
            />

            {/* Bracket */}
            {data.bracket && data.bracket.games.length > 0 && (
              <>
                <div className="mm-court-line" />
                <div className="mm-section">
                  <div className="mm-section-header">
                    <h2 className="mm-section-title">Bracket</h2>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <span className="mm-section-badge">{data.bracket.games.length} games</span>
                      <div style={{
                        display: "flex",
                        borderRadius: 8,
                        overflow: "hidden",
                        border: "1px solid var(--mm-card-border)",
                      }}>
                        <button
                          onClick={() => setBracketView("bracket")}
                          style={{
                            padding: "4px 12px",
                            fontSize: "0.75rem",
                            background: bracketView === "bracket" ? "var(--mm-gold)" : "transparent",
                            color: bracketView === "bracket" ? "#1a0e08" : "var(--mm-text-dim)",
                            border: "none",
                            cursor: "pointer",
                            fontWeight: bracketView === "bracket" ? 700 : 400,
                          }}
                        >
                          Bracket
                        </button>
                        <button
                          onClick={() => setBracketView("grid")}
                          style={{
                            padding: "4px 12px",
                            fontSize: "0.75rem",
                            background: bracketView === "grid" ? "var(--mm-gold)" : "transparent",
                            color: bracketView === "grid" ? "#1a0e08" : "var(--mm-text-dim)",
                            border: "none",
                            cursor: "pointer",
                            fontWeight: bracketView === "grid" ? 700 : 400,
                          }}
                        >
                          Grid
                        </button>
                      </div>
                    </div>
                  </div>
                  {bracketView === "bracket" ? (
                    <BracketView bracket={data.bracket} />
                  ) : (
                    <BracketGrid bracket={data.bracket} />
                  )}
                </div>
              </>
            )}

            {/* Upsets (during/after tournament) */}
            {data.upsets.length > 0 && (
              <>
                <div className="mm-court-line" />
                <div className="mm-section">
                  <div className="mm-section-header">
                    <h2 className="mm-section-title">Upsets</h2>
                    <span className="mm-section-badge">{data.upsets.length} upsets</span>
                  </div>
                  <UpsetTracker upsets={data.upsets} />
                </div>
              </>
            )}

            {/* Cinderellas (during/after tournament) */}
            {data.cinderellas.length > 0 && (
              <>
                <div className="mm-court-line" />
                <div className="mm-section">
                  <CinderellaWatch cinderellas={data.cinderellas} />
                </div>
              </>
            )}

            {/* Live Games (Phase 3) */}
            {data.live_games.length > 0 && (
              <>
                <div className="mm-court-line" />
                <div className="mm-section">
                  <div className="mm-section-header">
                    <h2 className="mm-section-title">Live Games</h2>
                    <span className="mm-section-badge">{data.live_games.length} games</span>
                  </div>
                  <LiveCommandCenter games={data.live_games} />
                </div>
              </>
            )}

            {/* Bracket Buster Insights (Phase 4) */}
            {data.bracket_buster_insights && data.bracket_buster_insights.length > 0 && (
              <>
                <div className="mm-court-line" />
                <div className="mm-section">
                  <div className="mm-section-header">
                    <h2 className="mm-section-title">Bracket Buster Insights</h2>
                    <span className="mm-section-badge">{data.bracket_buster_insights.length} insights</span>
                  </div>
                  <BracketBusterInsights insights={data.bracket_buster_insights} />
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
