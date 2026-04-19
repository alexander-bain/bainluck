"use client";

import { useState } from "react";
import type { WMLeaderboardEntry, WMCommentaryEntry } from "@/lib/types";
import CommentaryFeed from "./CommentaryFeed";

interface LeaderboardProps {
  entries: WMLeaderboardEntry[];
  currentPlayerId?: number;
  commentaryFeed?: WMCommentaryEntry[];
}

function formatMoney(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1000)}k`;
  return `$${Math.round(n)}`;
}

function resultIcon(result: "won" | "lost" | null): string {
  if (result === "won") return "✓";
  if (result === "lost") return "✗";
  return "⏳";
}

export default function Leaderboard({ entries, currentPlayerId, commentaryFeed }: LeaderboardProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  if (entries.length === 0) return null;

  return (
    <div className="wm-leaderboard-section">
      <div className="wm-leaderboard-header">Leaderboard</div>

      {entries.map((entry, i) => {
        const isYou = entry.id === currentPlayerId;
        const isExpanded = expandedId === entry.id;
        const rankColors = ["var(--wm-neon-gold)", "var(--wm-text-primary)", "var(--wm-text-secondary)"];
        const rankColor = i < 3 ? rankColors[i] : "var(--wm-text-muted)";

        return (
          <div
            key={entry.id}
            className={`wm-lb-row ${isYou ? "wm-lb-you" : ""}`}
            onClick={() => setExpandedId(isExpanded ? null : entry.id)}
          >
            <div className="wm-lb-main">
              <span className="wm-lb-rank" style={{ color: rankColor }}>
                {i === 0 ? "👑" : i + 1}
              </span>
              <div className="wm-lb-info">
                <span className="wm-lb-name">
                  {entry.display_name}
                  {isYou && <span className="wm-lb-you-badge">you</span>}
                </span>
                <span className="wm-lb-meta">
                  {entry.wins}W {entry.losses}L {entry.pending}P
                  {entry.pending > 0 && (
                    <span className="wm-lb-max"> · max {formatMoney(entry.max_possible)}</span>
                  )}
                </span>
              </div>
              {entry.win_probability != null && (
                <span
                  className="wm-lb-winprob"
                  style={{
                    color: entry.win_probability > 30
                      ? "var(--wm-neon-gold)"
                      : entry.win_probability > 10
                      ? "var(--wm-text-primary)"
                      : "var(--wm-text-muted)",
                  }}
                >
                  {entry.win_probability > 0
                    ? `${entry.win_probability}%`
                    : "<1%"}
                </span>
              )}
              <span className="wm-lb-bankroll">{formatMoney(entry.bankroll)}</span>
            </div>

            {isExpanded && entry.pick_details.length > 0 && (
              <div className="wm-lb-picks">
                {entry.pick_details.map((pk, j) => (
                  <div key={j} className="wm-lb-pick">
                    <span className="wm-lb-pick-result">{resultIcon(pk.result)}</span>
                    <span className="wm-lb-pick-name">{pk.outcome_name}</span>
                    <span className="wm-lb-pick-info">
                      {formatMoney(pk.stake)} @ {pk.odds.toFixed(1)}x
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}

      {commentaryFeed && commentaryFeed.length > 0 && (
        <CommentaryFeed entries={commentaryFeed} />
      )}
    </div>
  );
}
