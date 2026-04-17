"use client";

import type { WMLeaderboardEntry } from "@/lib/types";

interface LeaderboardProps {
  entries: WMLeaderboardEntry[];
  currentPlayerId?: number;
}

export default function Leaderboard({ entries, currentPlayerId }: LeaderboardProps) {
  const top5 = entries.slice(0, 5);

  if (top5.length === 0) return null;

  return (
    <div className="wm-leaderboard">
      <div className="wm-leaderboard-inner">
        <div className="wm-leaderboard-title">Leaderboard</div>
        {top5.map((entry, i) => (
          <div
            key={entry.id}
            className={`wm-leaderboard-row ${
              entry.id === currentPlayerId ? "wm-leaderboard-you" : ""
            }`}
          >
            <span className="wm-leaderboard-rank">{i + 1}</span>
            <span className="wm-leaderboard-name">
              {entry.display_name}
              {entry.id === currentPlayerId ? " (you)" : ""}
            </span>
            <span className="wm-leaderboard-bankroll">
              ${entry.bankroll.toLocaleString("en-US", { maximumFractionDigits: 0 })}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
