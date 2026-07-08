"use client";

import { useMemo } from "react";
import type { GameMarketsResponse } from "@/lib/api";

interface PlayerPropsGridProps {
  data: GameMarketsResponse;
  homeColor?: string;
  awayColor?: string;
}

interface ParsedProp {
  playerName: string;
  statType: string;
  threshold: number;
  overProbability: number;
  source: string;
  movement: number | null;
  team: "home" | "away" | "unknown";
  headshot?: string;
}

/**
 * Player Props Grid — cards with probability, target threshold, movement.
 * Design: event-detail-v5.html mockup, Level 3 "Game Markets"
 */
export default function PlayerPropsGrid({ data, homeColor, awayColor }: PlayerPropsGridProps) {
  const { player_props, home_team, away_team } = data;

  const props = useMemo(() => {
    if (!player_props || player_props.length === 0) return [];

    // Parse two market name formats:
    // 1. "Boston at Atlanta: Trae Young Points" (player + stat in market name)
    // 2. "Philadelphia at Washington: Steals" with outcome "Joel Embiid: 1+"
    //    (stat in market name, player in outcome name)
    const parsed: ParsedProp[] = [];
    const seen = new Set<string>();

    const statTypes = [
      "Points", "Assists", "Rebounds", "Steals", "Blocks",
      "Three Pointers", "3-Pointers", "Turnovers",
      "PRA", "PA", "PR", "RA",
      "Strikeouts", "Hits", "Runs", "Home Runs",
      "Goals", "Saves", "Sacks",
      "Passing Yards", "Rushing Yards", "Receiving Yards", "Touchdowns",
      "Double Double", "Triple Double", "First Basket",
    ];

    for (const p of player_props) {
      const name = p.market_name || "";
      const colonIdx = name.indexOf(":");
      const afterColon = colonIdx >= 0 ? name.slice(colonIdx + 1).trim() : name;

      let playerName = "";
      let statType = "";

      // Check if afterColon IS a stat type (team stat market format)
      const exactStatMatch = statTypes.find(
        (st) => afterColon.toLowerCase() === st.toLowerCase(),
      );
      if (exactStatMatch) {
        // Format 2: stat from market name, player from outcome name
        // Outcome format: "PlayerName: X+" — extract name before ":"
        statType = exactStatMatch;
        const outcomeColon = (p.outcome_name || "").indexOf(":");
        if (outcomeColon > 0) {
          playerName = p.outcome_name.slice(0, outcomeColon).trim();
        }
      } else {
        // Format 1: "PlayerName StatType" after the colon
        playerName = afterColon;
        for (const st of statTypes) {
          if (afterColon.toLowerCase().endsWith(st.toLowerCase())) {
            playerName = afterColon.slice(0, -st.length).trim();
            statType = st;
            break;
          }
        }
      }

      if (!playerName || !p.threshold) continue;

      // Deduplicate by player+stat — keep highest threshold per player+stat combo
      const key = `${playerName.toLowerCase()}-${statType.toLowerCase()}`;
      if (seen.has(key)) continue;
      seen.add(key);

      // Determine team — prefer API-provided team, fall back to market name parsing
      let team: "home" | "away" | "unknown" = p.player_team ?? "unknown";
      if (team === "unknown") {
        const beforeColon = colonIdx >= 0 ? name.slice(0, colonIdx) : "";
        if (home_team && beforeColon.toLowerCase().includes(home_team.split(" ").pop()!.toLowerCase())) {
          team = "home";
        }
        if (away_team && beforeColon.toLowerCase().includes(away_team.split(" ").pop()!.toLowerCase())) {
          team = team === "home" ? "unknown" : "away";
        }
      }

      parsed.push({
        playerName,
        statType,
        threshold: p.threshold,
        overProbability: p.over_probability,
        source: p.source,
        movement: p.movement,
        team,
        headshot: p.player_headshot,
      });
    }

    // Sort by probability descending (most likely to hit first)
    return parsed.sort((a, b) => b.overProbability - a.overProbability);
  }, [player_props, home_team, away_team]);

  if (props.length === 0) return null;

  // L2-52: source-name attribution removed (blend-only).
  return (
    <div className="bg-surface-card rounded-xl border border-surface-border overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-surface-border">
        <span className="text-[11px] font-bold uppercase tracking-wider text-text-secondary">
          Player Props
        </span>
        <span className="text-micro text-text-muted">
          {props.length} props
        </span>
      </div>

      <div className="grid grid-cols-2 gap-1.5 p-3">
        {props.slice(0, 8).map((prop, i) => {
          const prob = Math.round(prop.overProbability * 100);
          const probColor = prob >= 60 ? "text-green-500" : prob >= 40 ? "text-amber-500" : "text-red-500";
          const teamColor = prop.team === "home" ? homeColor : prop.team === "away" ? awayColor : undefined;
          const initials = prop.playerName
            .split(" ")
            .map((w) => w[0])
            .join("")
            .slice(0, 2)
            .toUpperCase();

          return (
            <div key={i} className="bg-surface-elevated rounded-xl p-2 border border-surface-border">
              {/* Player */}
              <div className="flex items-center gap-1.5 mb-1">
                {prop.headshot ? (
                  <img
                    src={prop.headshot}
                    alt={prop.playerName}
                    loading="eager"
                    fetchPriority="high"
                    className="w-6 h-6 rounded-full object-cover shrink-0"
                    style={{ backgroundColor: teamColor || "#6B7280" }}
                  />
                ) : (
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-[8px] font-bold text-white shrink-0"
                    style={{ background: teamColor || "#6B7280" }}
                  >
                    {initials}
                  </div>
                )}
                <span className="text-[10px] font-bold text-text-primary truncate">
                  {prop.playerName}
                </span>
              </div>

              {/* Target */}
              <div className="text-[9px] text-text-muted font-semibold mb-1">
                target: {prop.threshold} {prop.statType.toLowerCase()}
              </div>

              {/* Probability + movement */}
              <div className="flex items-center justify-between">
                <span className={`text-[10px] font-bold font-mono ${probColor}`}>
                  {prob}% chance
                </span>
                {prop.movement !== null && Math.abs(prop.movement) >= 0.01 && (
                  <span className={`text-[8px] font-bold ${prop.movement > 0 ? "text-green-500" : "text-red-500"}`}>
                    {prop.movement > 0 ? "+" : ""}{Math.round(prop.movement * 100)}%
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
