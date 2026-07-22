"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import { BracketGame } from "@/lib/types";
import { getUpsetRarityLabel } from "@/lib/marchMadnessData";

interface LiveCommandCenterProps {
  games: BracketGame[];
}

export default function LiveCommandCenter({ games }: LiveCommandCenterProps) {
  const liveGames = useMemo(
    () => games.filter((g) => g.status === "live" || g.status === "in_progress"),
    [games]
  );

  const selectedGameId = useMemo(() => {
    if (liveGames.length === 0) return null;
    return liveGames.reduce((best, game) => {
      const bestEI = liveGames.find((g) => g.event_id === best)?.ei ?? -1;
      return (game.ei ?? -1) > bestEI ? game.event_id : best;
    }, liveGames[0].event_id);
  }, [liveGames]);

  const [selectedId, setSelectedId] = useState<number | null>(selectedGameId);

  // Update selected if selected game goes offline
  React.useEffect(() => {
    if (selectedId && !liveGames.find((g) => g.event_id === selectedId)) {
      setSelectedId(selectedGameId);
    }
  }, [liveGames, selectedId, selectedGameId]);

  const selectedGame = liveGames.find((g) => g.event_id === selectedId);

  if (liveGames.length === 0) {
    return (
      <div
        style={{
          backgroundColor: "var(--mm-card-bg)",
          border: "1px solid var(--mm-card-border)",
          borderRadius: "8px",
          padding: "24px",
          textAlign: "center",
          color: "var(--mm-text-dim)",
          fontStyle: "italic",
        }}
      >
        No live games right now
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {/* Live games carousel */}
      <div
        style={{
          display: "flex",
          gap: "12px",
          overflowX: "auto",
          overflowY: "hidden",
          paddingBottom: "8px",
          scrollBehavior: "smooth",
        }}
      >
        {liveGames.map((game) => {
          const isSelected = selectedId === game.event_id;
          const seedDiff = Math.abs((game.seed_home ?? 0) - (game.seed_away ?? 0));
          const isUpset =
            (game.prob_home ?? 0.5) < 0.45 || (game.prob_away ?? 0.5) < 0.45;

          return (
            <button
              key={game.event_id}
              onClick={() => setSelectedId(game.event_id)}
              style={{
                flex: "0 0 200px",
                padding: "12px",
                backgroundColor: isSelected
                  ? "rgba(201, 168, 76, 0.2)"
                  : "var(--mm-card-bg)",
                border: isSelected
                  ? "2px solid var(--mm-gold)"
                  : "1px solid var(--mm-card-border)",
                borderRadius: "6px",
                cursor: "pointer",
                transition: "all 0.2s ease",
                color: "var(--mm-text)",
                textAlign: "left",
                fontSize: "13px",
                fontWeight: isSelected ? 600 : 400,
              }}
              onMouseEnter={(e) => {
                if (!isSelected) {
                  (e.currentTarget as HTMLButtonElement).style.borderColor =
                    "var(--mm-gold)";
                }
              }}
              onMouseLeave={(e) => {
                if (!isSelected) {
                  (e.currentTarget as HTMLButtonElement).style.borderColor =
                    "var(--mm-card-border)";
                }
              }}
            >
              <div style={{ display: "flex", gap: "4px", marginBottom: "8px" }}>
                {game.seed_home && (
                  <span
                    style={{
                      backgroundColor: "rgba(139, 69, 19, 0.5)",
                      padding: "2px 6px",
                      borderRadius: "3px",
                      fontSize: "11px",
                    }}
                  >
                    #{game.seed_home}
                  </span>
                )}
                {isUpset && (
                  <span
                    style={{
                      backgroundColor: "var(--mm-upset-red)",
                      color: "white",
                      padding: "2px 6px",
                      borderRadius: "3px",
                      fontSize: "11px",
                      fontWeight: 600,
                    }}
                  >
                    UPSET
                  </span>
                )}
              </div>
              <div
                style={{
                  fontWeight: 600,
                  fontSize: "12px",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  marginBottom: "6px",
                }}
              >
                {game.home_team}
              </div>
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--mm-text-dim)",
                  marginBottom: "6px",
                }}
              >
                vs {game.away_team.substring(0, 20)}
                {game.away_team.length > 20 ? "..." : ""}
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  fontSize: "12px",
                  color: "var(--mm-gold)",
                  fontWeight: 600,
                }}
              >
                <span>{game.score_home ?? "-"}</span>
                <span>{game.score_away ?? "-"}</span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Selected game detail */}
      {selectedGame && (
        <Link href={`/events/${selectedGame.event_id}`}>
          <div
            style={{
              backgroundColor: "var(--mm-card-bg)",
              border: "2px solid var(--mm-gold)",
              borderRadius: "8px",
              padding: "20px",
              cursor: "pointer",
              transition: "all 0.2s ease",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLDivElement).style.backgroundColor =
                "rgba(201, 168, 76, 0.15)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLDivElement).style.backgroundColor =
                "var(--mm-card-bg)";
            }}
          >
            {/* Header with seeds and round */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "16px",
              }}
            >
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                {selectedGame.seed_home && (
                  <span
                    style={{
                      backgroundColor: "rgba(139, 69, 19, 0.5)",
                      padding: "4px 10px",
                      borderRadius: "4px",
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "var(--mm-gold)",
                    }}
                  >
                    #{selectedGame.seed_home}
                  </span>
                )}
                <span style={{ color: "var(--mm-text)" }}>
                  {selectedGame.home_team}
                </span>
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "8px",
                }}
              >
                <div
                  style={{
                    fontSize: "24px",
                    fontWeight: 700,
                    color: "var(--mm-gold)",
                  }}
                >
                  {selectedGame.score_home ?? "-"}{" "}
                  <span style={{ fontSize: "16px" }}>-</span>{" "}
                  {selectedGame.score_away ?? "-"}
                </div>
                {selectedGame.round && (
                  <div
                    style={{
                      fontSize: "12px",
                      color: "var(--mm-text-dim)",
                      textTransform: "uppercase",
                      letterSpacing: "0.5px",
                    }}
                  >
                    {selectedGame.round}
                  </div>
                )}
              </div>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <span style={{ color: "var(--mm-text)" }}>
                  {selectedGame.away_team}
                </span>
                {selectedGame.seed_away && (
                  <span
                    style={{
                      backgroundColor: "rgba(139, 69, 19, 0.5)",
                      padding: "4px 10px",
                      borderRadius: "4px",
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "var(--mm-gold)",
                    }}
                  >
                    #{selectedGame.seed_away}
                  </span>
                )}
              </div>
            </div>

            {/* Stats row */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr 1fr 1fr",
                gap: "12px",
                borderTop: "1px solid var(--mm-card-border)",
                paddingTop: "16px",
              }}
            >
              {/* Home probability */}
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
                  {selectedGame.home_team.substring(0, 12)} Win%
                </div>
                <div
                  style={{
                    fontSize: "18px",
                    fontWeight: 700,
                    color: "var(--mm-gold)",
                  }}
                >
                  {selectedGame.prob_home
                    ? `${(selectedGame.prob_home * 100).toFixed(0)}%`
                    : "—"}
                </div>
              </div>

              {/* Away probability */}
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
                  {selectedGame.away_team.substring(0, 12)} Win%
                </div>
                <div
                  style={{
                    fontSize: "18px",
                    fontWeight: 700,
                    color: "var(--mm-gold)",
                  }}
                >
                  {selectedGame.prob_away
                    ? `${(selectedGame.prob_away * 100).toFixed(0)}%`
                    : "—"}
                </div>
              </div>

              {/* EI Badge */}
              {selectedGame.ei && (
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
                    Excitement
                  </div>
                  <div
                    style={{
                      fontSize: "18px",
                      fontWeight: 700,
                      color: "var(--mm-orange)",
                    }}
                  >
                    {selectedGame.ei}
                  </div>
                </div>
              )}

              {/* Upset info */}
              {selectedGame.historical_upset_rate !== null &&
                selectedGame.historical_upset_rate !== undefined && (
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
                      Upset Rate
                    </div>
                    <div
                      style={{
                        fontSize: "18px",
                        fontWeight: 700,
                        color: "var(--mm-upset-red)",
                      }}
                    >
                      {(selectedGame.historical_upset_rate * 100).toFixed(0)}%
                    </div>
                  </div>
                )}
            </div>

            {/* Click to view full */}
            <div
              style={{
                marginTop: "16px",
                padding: "12px",
                backgroundColor: "rgba(201, 168, 76, 0.1)",
                borderRadius: "4px",
                textAlign: "center",
                fontSize: "12px",
                color: "var(--mm-gold)",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Click to view full event details
            </div>
          </div>
        </Link>
      )}
    </div>
  );
}
