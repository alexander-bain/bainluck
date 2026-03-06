"use client";

import React, { useMemo } from "react";
import { MarchMadnessUpset } from "@/lib/types";
import { getUpsetRarityLabel } from "@/lib/marchMadnessData";

interface UpsetTrackerProps {
  upsets: MarchMadnessUpset[];
}

export default function UpsetTracker({ upsets }: UpsetTrackerProps) {
  // Find biggest upset: highest seed differential, then lowest pre-game probability
  const biggestUpset = useMemo(() => {
    if (upsets.length === 0) return null;
    return upsets.reduce((best, current) => {
      const currentDiff = Math.abs(
        current.seed_winner - current.seed_loser
      );
      const bestDiff = Math.abs(best.seed_winner - best.seed_loser);

      if (currentDiff !== bestDiff) {
        return currentDiff > bestDiff ? current : best;
      }

      const currentProb = current.winner_pre_game_prob ?? 0.5;
      const bestProb = best.winner_pre_game_prob ?? 0.5;
      return currentProb < bestProb ? current : best;
    });
  }, [upsets]);

  // Sort remaining upsets by most recent (assuming order from API is chronological)
  const allUpsets = useMemo(
    () => [...upsets].reverse(),
    [upsets]
  );

  if (upsets.length === 0) {
    return null;
  }

  const getUpsetColor = (seedWinner: number, seedLoser: number) => {
    const diff = Math.abs(seedWinner - seedLoser);
    if (diff >= 12) return "var(--mm-upset-red)"; // Historic
    if (diff >= 8) return "var(--mm-upset-red)"; // Massive
    if (diff >= 5) return "var(--mm-orange)"; // Major
    return "var(--mm-gold)"; // Notable
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Hero Upset */}
      <div
        style={{
          backgroundColor: "var(--mm-card-bg)",
          border: "2px solid var(--mm-upset-red)",
          borderRadius: "8px",
          padding: "20px",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Background accent */}
        <div
          style={{
            position: "absolute",
            top: "-40px",
            right: "-40px",
            width: "200px",
            height: "200px",
            borderRadius: "50%",
            backgroundColor: "rgba(231, 76, 60, 0.08)",
            zIndex: 0,
          }}
        />

        <div style={{ position: "relative", zIndex: 1 }}>
          {/* Header */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              marginBottom: "16px",
            }}
          >
            <span
              style={{
                fontSize: "12px",
                fontWeight: 700,
                color: "white",
                backgroundColor: "var(--mm-upset-red)",
                padding: "6px 12px",
                borderRadius: "4px",
                textTransform: "uppercase",
                letterSpacing: "0.5px",
              }}
            >
              🔥 {getUpsetRarityLabel(
                biggestUpset.seed_winner,
                biggestUpset.seed_loser
              )}{" "}
              UPSET
            </span>
          </div>

          {/* Winner vs Loser */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "16px",
              marginBottom: "16px",
            }}
          >
            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--mm-text-dim)",
                  marginBottom: "4px",
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                }}
              >
                Winner
              </div>
              <div
                style={{
                  fontSize: "20px",
                  fontWeight: 700,
                  color: "var(--mm-upset-red)",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                }}
              >
                #{biggestUpset.seed_winner}{" "}
                <span style={{ color: "var(--mm-text)" }}>
                  {biggestUpset.winner}
                </span>
              </div>
            </div>

            <div
              style={{
                textAlign: "center",
                padding: "12px",
                backgroundColor: "rgba(231, 76, 60, 0.1)",
                borderRadius: "4px",
              }}
            >
              <div
                style={{
                  fontSize: "16px",
                  fontWeight: 700,
                  color: "var(--mm-upset-red)",
                  marginBottom: "4px",
                }}
              >
                {biggestUpset.score}
              </div>
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--mm-text-dim)",
                }}
              >
                Final
              </div>
            </div>

            <div style={{ flex: 1, textAlign: "right" }}>
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--mm-text-dim)",
                  marginBottom: "4px",
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                }}
              >
                Loser
              </div>
              <div
                style={{
                  fontSize: "20px",
                  fontWeight: 700,
                  color: "var(--mm-text-dim)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "flex-end",
                  gap: "8px",
                }}
              >
                <span style={{ color: "var(--mm-text)" }}>
                  {biggestUpset.loser}
                </span>
                #{biggestUpset.seed_loser}
              </div>
            </div>
          </div>

          {/* Stats */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "12px",
              paddingTop: "16px",
              borderTop: "1px solid var(--mm-card-border)",
            }}
          >
            <div>
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--mm-text-dim)",
                  marginBottom: "4px",
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                }}
              >
                Pre-Game Odds
              </div>
              <div
                style={{
                  fontSize: "16px",
                  fontWeight: 700,
                  color: "var(--mm-upset-red)",
                }}
              >
                {biggestUpset.winner_pre_game_prob
                  ? `Only ${(biggestUpset.winner_pre_game_prob * 100).toFixed(1)}%`
                  : "—"}
              </div>
            </div>
            {biggestUpset.historical_upset_rate !== null &&
              biggestUpset.historical_upset_rate !== undefined && (
                <div>
                  <div
                    style={{
                      fontSize: "11px",
                      color: "var(--mm-text-dim)",
                      marginBottom: "4px",
                      textTransform: "uppercase",
                      letterSpacing: "0.5px",
                    }}
                  >
                    Historical Rate
                  </div>
                  <div
                    style={{
                      fontSize: "16px",
                      fontWeight: 700,
                      color: "var(--mm-orange)",
                    }}
                  >
                    {(biggestUpset.historical_upset_rate * 100).toFixed(1)}%
                  </div>
                </div>
              )}
          </div>
        </div>
      </div>

      {/* All Upsets List */}
      {allUpsets.length > 1 && (
        <div>
          <h3
            style={{
              fontSize: "14px",
              fontWeight: 700,
              color: "var(--mm-gold)",
              marginBottom: "12px",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
            }}
          >
            All Upsets ({allUpsets.length})
          </h3>

          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {allUpsets.map((upset, idx) => {
              const seedDiff = Math.abs(upset.seed_winner - upset.seed_loser);
              const color = getUpsetColor(upset.seed_winner, upset.seed_loser);

              return (
                <div
                  key={`${upset.event_id}-${idx}`}
                  style={{
                    backgroundColor: "var(--mm-card-bg)",
                    border: `1px solid var(--mm-card-border)`,
                    borderRadius: "6px",
                    padding: "12px",
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                  }}
                >
                  {/* Seed difference badge */}
                  <div
                    style={{
                      backgroundColor: color,
                      color: "white",
                      padding: "6px 10px",
                      borderRadius: "4px",
                      fontSize: "12px",
                      fontWeight: 700,
                      minWidth: "50px",
                      textAlign: "center",
                    }}
                  >
                    +{seedDiff}
                  </div>

                  {/* Winner */}
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontSize: "13px",
                        fontWeight: 600,
                        color: "var(--mm-text)",
                      }}
                    >
                      #{upset.seed_winner} {upset.winner}
                    </div>
                  </div>

                  {/* Score */}
                  <div
                    style={{
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "var(--mm-gold)",
                      minWidth: "50px",
                      textAlign: "center",
                    }}
                  >
                    {upset.score}
                  </div>

                  {/* Loser */}
                  <div style={{ flex: 1, textAlign: "right" }}>
                    <div
                      style={{
                        fontSize: "13px",
                        fontWeight: 600,
                        color: "var(--mm-text-dim)",
                      }}
                    >
                      #{upset.seed_loser} {upset.loser}
                    </div>
                  </div>

                  {/* Pre-game probability */}
                  {upset.winner_pre_game_prob && (
                    <div
                      style={{
                        fontSize: "11px",
                        color: "var(--mm-text-dim)",
                        minWidth: "60px",
                        textAlign: "right",
                      }}
                    >
                      {(upset.winner_pre_game_prob * 100).toFixed(0)}% odds
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
