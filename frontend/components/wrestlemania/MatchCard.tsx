"use client";

import { useState } from "react";
import type { WMMatch, WMOutcome } from "@/lib/types";

interface MatchCardProps {
  match: WMMatch;
  onOutcomeClick: (match: WMMatch, outcome: WMOutcome) => void;
}

function formatOdds(decimal: number | null): string {
  if (!decimal || decimal <= 1) return "";
  if (decimal >= 2) return `+${Math.round((decimal - 1) * 100)}`;
  return `-${Math.round(100 / (decimal - 1))}`;
}

function lockCountdown(lockTime: string): string {
  const diff = new Date(lockTime).getTime() - Date.now();
  if (diff <= 0) return "Locked";
  const hours = Math.floor(diff / 3600000);
  const mins = Math.floor((diff % 3600000) / 60000);
  if (hours > 24) return `${Math.floor(hours / 24)}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

export default function MatchCard({ match, onOutcomeClick }: MatchCardProps) {
  const [showStoryline, setShowStoryline] = useState(false);
  const countdown = lockCountdown(match.lock_time);
  const isSoon = countdown !== "Locked" && !countdown.includes("d");

  return (
    <div className={`wm-match-card ${match.status === "resolved" ? "resolved" : ""}`}>
      <div className="wm-match-header">
        <div>
          <div className="wm-match-type">{match.match_type}</div>
          <h3 className="wm-match-title">{match.title}</h3>
          <div className={`wm-lock-time ${isSoon ? "soon" : ""}`}>
            {match.status === "resolved"
              ? "Final"
              : match.status === "locked"
              ? "🔒 Locked"
              : `Locks in ${countdown}`}
          </div>
        </div>
        <span className={`wm-match-status ${match.status}`}>
          {match.status}
        </span>
      </div>

      <div className="wm-outcomes">
        {match.outcomes.map((outcome) => {
          const isPicked = match.my_pick?.outcome_id === outcome.id;
          const isWinner = outcome.is_winner === true;
          const isLoser = match.status === "resolved" && outcome.is_winner === false;

          return (
            <div
              key={outcome.id}
              className={`wm-outcome ${isPicked ? "selected" : ""} ${
                isWinner ? "winner" : ""
              } ${isLoser ? "loser" : ""}`}
              onClick={() => {
                if (match.status === "open") onOutcomeClick(match, outcome);
              }}
            >
              {outcome.wikipedia_image_url && (
                <img
                  className="wm-outcome-img"
                  src={outcome.wikipedia_image_url}
                  alt={outcome.name}
                />
              )}
              <div className="wm-outcome-name">{outcome.name}</div>
              <div className="wm-outcome-prob">
                {outcome.probability
                  ? `${Math.round(outcome.probability * 100)}%`
                  : "—"}
              </div>
              <div className="wm-outcome-odds">
                {outcome.decimal_odds ? formatOdds(outcome.decimal_odds) : ""}
              </div>
              {outcome.case_text && (
                <div className="wm-case-text">{outcome.case_text}</div>
              )}
              {isPicked && (
                <div className="wm-pick-badge">
                  Your pick: ${match.my_pick!.stake.toLocaleString()}
                </div>
              )}
              {isWinner && <div className="wm-pick-badge" style={{ background: "rgba(255,215,0,0.2)", color: "#FFD700" }}>Winner</div>}
            </div>
          );
        })}
      </div>

      {match.storyline && (
        <div className="wm-storyline">
          <button
            className="wm-storyline-toggle"
            onClick={(e) => {
              e.stopPropagation();
              setShowStoryline(!showStoryline);
            }}
          >
            {showStoryline ? "Hide backstory ▲" : "Show backstory ▼"}
          </button>
          {showStoryline && <p style={{ marginTop: "0.5rem" }}>{match.storyline}</p>}
        </div>
      )}

      {match.picks.length > 0 && (
        <div className="wm-picks-list">
          {match.picks.map((pick, i) => (
            <div key={i} className="wm-pick-item">
              <span className="wm-pick-player">
                {pick.player} → {match.outcomes.find(o => o.id === pick.outcome_id)?.name}
              </span>
              <span className="wm-pick-stake">
                ${pick.stake.toLocaleString()}
                {pick.result === "won" && " ✓"}
                {pick.result === "lost" && " ✗"}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
