"use client";

import React, { useMemo } from "react";
import { MarchMadnessCinderella } from "@/lib/types";
import { getSeedColor } from "@/lib/marchMadnessData";

interface CinderellaWatchProps {
  cinderellas: MarchMadnessCinderella[];
}

const ROUND_ORDER: Record<number, string> = {
  1: "Round of 64",
  2: "Round of 32",
  3: "Sweet 16",
  4: "Elite Eight",
  5: "Final Four",
  6: "Championship",
};

const getRoundFromWins = (gamesWon: number): string => {
  if (gamesWon >= 5) return "Final Four";
  if (gamesWon >= 4) return "Elite Eight";
  if (gamesWon >= 3) return "Sweet 16";
  if (gamesWon >= 2) return "Round of 32";
  if (gamesWon >= 1) return "Round of 32";
  return "First Round";
};

export default function CinderellaWatch({ cinderellas }: CinderellaWatchProps) {
  // Sort by deepest run (most games won), then by title odds
  const sortedCinderellas = useMemo(
    () =>
      [...cinderellas].sort((a, b) => {
        if (b.games_won !== a.games_won) {
          return b.games_won - a.games_won;
        }
        return b.title_odds - a.title_odds;
      }),
    [cinderellas]
  );

  if (cinderellas.length === 0) {
    return null;
  }

  const isDeepRun = (gamesWon: number): boolean => gamesWon >= 3;

  return (
    <div>
      <h2
        style={{
          fontSize: "16px",
          fontWeight: 700,
          color: "var(--mm-gold)",
          marginBottom: "16px",
          textTransform: "uppercase",
          letterSpacing: "0.5px",
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <span>🎉</span> Cinderella Watch
      </h2>

      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {sortedCinderellas.map((cinderella, idx) => {
          const deepRun = isDeepRun(cinderella.games_won);
          const seedColor = getSeedColor(cinderella.seed);
          const currentRound = getRoundFromWins(cinderella.games_won);

          return (
            <div
              key={`${cinderella.team_name}-${idx}`}
              style={{
                backgroundColor: "var(--mm-card-bg)",
                border: deepRun
                  ? "2px solid var(--mm-gold)"
                  : "1px solid var(--mm-card-border)",
                borderRadius: "6px",
                padding: "12px",
                display: "grid",
                gridTemplateColumns:
                  "60px 1fr 1fr 1fr 1fr",
                gap: "12px",
                alignItems: "center",
                transition: "all 0.2s ease",
              }}
              onMouseEnter={(e) => {
                if (deepRun) {
                  (e.currentTarget as HTMLDivElement).style.boxShadow =
                    "0 0 12px rgba(201, 168, 76, 0.2)";
                }
              }}
              onMouseLeave={(e) => {
                if (deepRun) {
                  (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
                }
              }}
            >
              {/* Seed Badge */}
              <div
                style={{
                  backgroundColor: seedColor,
                  color: "white",
                  padding: "8px",
                  borderRadius: "4px",
                  textAlign: "center",
                  fontWeight: 700,
                  fontSize: "14px",
                  minHeight: "40px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  boxShadow: `0 0 8px ${seedColor}40`,
                }}
              >
                #{cinderella.seed}
              </div>

              {/* Team name + region */}
              <div>
                <div
                  style={{
                    fontSize: "13px",
                    fontWeight: 600,
                    color: "var(--mm-text)",
                  }}
                >
                  {cinderella.team_name}
                </div>
                {cinderella.region && (
                  <div
                    style={{
                      fontSize: "11px",
                      color: "var(--mm-text-dim)",
                      marginTop: "2px",
                    }}
                  >
                    {cinderella.region} Region
                  </div>
                )}
              </div>

              {/* Record */}
              <div>
                <div
                  style={{
                    fontSize: "10px",
                    color: "var(--mm-text-dim)",
                    marginBottom: "2px",
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                  }}
                >
                  Record
                </div>
                <div
                  style={{
                    fontSize: "14px",
                    fontWeight: 700,
                    color: "var(--mm-green)",
                  }}
                >
                  {cinderella.games_won}-{cinderella.games_played - cinderella.games_won}
                </div>
              </div>

              {/* Current Round */}
              <div>
                <div
                  style={{
                    fontSize: "10px",
                    color: "var(--mm-text-dim)",
                    marginBottom: "2px",
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                  }}
                >
                  Current Round
                </div>
                <div
                  style={{
                    fontSize: "12px",
                    fontWeight: 600,
                    color: deepRun ? "var(--mm-gold)" : "var(--mm-text-dim)",
                  }}
                >
                  {currentRound}
                </div>
              </div>

              {/* Title Odds */}
              <div>
                <div
                  style={{
                    fontSize: "10px",
                    color: "var(--mm-text-dim)",
                    marginBottom: "2px",
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                  }}
                >
                  Title Odds
                </div>
                <div
                  style={{
                    fontSize: "14px",
                    fontWeight: 700,
                    color: "var(--mm-cinderella)",
                  }}
                >
                  {(cinderella.title_odds * 100).toFixed(2)}%
                </div>
              </div>

            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div
        style={{
          marginTop: "16px",
          padding: "12px",
          backgroundColor: "rgba(201, 168, 76, 0.05)",
          borderRadius: "4px",
          fontSize: "11px",
          color: "var(--mm-text-dim)",
          display: "flex",
          gap: "16px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div
            style={{
              width: "8px",
              height: "8px",
              backgroundColor: "var(--mm-gold)",
              borderRadius: "50%",
            }}
          />
          <span>Deep run (Sweet 16+)</span>
        </div>
      </div>
    </div>
  );
}
