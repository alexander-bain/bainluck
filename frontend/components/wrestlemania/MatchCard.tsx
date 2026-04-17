"use client";

import { useState } from "react";
import type { WMMatch, WMOutcome } from "@/lib/types";
import OddsSparkline from "./OddsSparkline";

interface MatchCardProps {
  match: WMMatch;
  onOutcomeClick: (match: WMMatch, outcome: WMOutcome) => void;
}

function formatOdds(decimal: number | null): string {
  if (!decimal || decimal <= 1) return "";
  if (decimal >= 2) return `+${Math.round((decimal - 1) * 100)}`;
  return `−${Math.round(100 / (decimal - 1))}`;
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

const OUTCOME_COLORS = ["#FF2E93", "#00E5FF", "#FFD700", "#9B59B6", "#2ECC71", "#E67E22"];

function PlaceholderAvatar({ name, color }: { name: string; color: string }) {
  const initials = name
    .split(/[\s&,]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
  return (
    <div
      style={{
        width: 64,
        height: 64,
        borderRadius: "50%",
        background: `linear-gradient(135deg, ${color}33, ${color}66)`,
        border: `2px solid ${color}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "1.1rem",
        fontWeight: 700,
        color,
        flexShrink: 0,
      }}
    >
      {initials}
    </div>
  );
}

export default function MatchCard({ match, onOutcomeClick }: MatchCardProps) {
  const [showStoryline, setShowStoryline] = useState(false);
  const countdown = lockCountdown(match.lock_time);
  const isSoon = countdown !== "Locked" && !countdown.includes("d");
  const isBinary = match.outcomes.length === 2;

  // For binary matches, render a head-to-head visual
  if (isBinary) {
    const [left, right] = match.outcomes;
    const leftProb = left.probability ?? 0.5;
    const rightProb = right.probability ?? 0.5;
    const leftPicked = match.my_pick?.outcome_id === left.id;
    const rightPicked = match.my_pick?.outcome_id === right.id;

    return (
      <div className={`wm-match-card ${match.status === "resolved" ? "resolved" : ""}`}>
        <div className="wm-match-header">
          <div>
            <div className="wm-match-type">{match.match_type}</div>
            <h3 className="wm-match-title">{match.title}</h3>
          </div>
          <div style={{ textAlign: "right" }}>
            <span className={`wm-match-status ${match.status}`}>{match.status}</span>
            <div className={`wm-lock-time ${isSoon ? "soon" : ""}`} style={{ marginTop: 4 }}>
              {match.status === "resolved" ? "Final" : match.status === "locked" ? "🔒 Locked" : `Locks in ${countdown}`}
            </div>
          </div>
        </div>

        {/* Head-to-head probability bar */}
        <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", margin: "0.75rem 0 0.5rem" }}>
          <div style={{ width: `${leftProb * 100}%`, background: "#FF2E93", transition: "width 0.5s" }} />
          <div style={{ width: `${rightProb * 100}%`, background: "#00E5FF", transition: "width 0.5s" }} />
        </div>

        {/* Two-column head-to-head */}
        <div style={{ display: "flex", gap: "0.75rem" }}>
          {[
            { outcome: left, color: "#FF2E93", picked: leftPicked },
            { outcome: right, color: "#00E5FF", picked: rightPicked },
          ].map(({ outcome, color, picked }) => (
            <div
              key={outcome.id}
              className={`wm-outcome ${picked ? "selected" : ""} ${outcome.is_winner === true ? "winner" : ""} ${match.status === "resolved" && outcome.is_winner === false ? "loser" : ""}`}
              onClick={() => match.status === "open" && onOutcomeClick(match, outcome)}
              style={{ flex: 1, padding: "0.75rem", alignItems: "center" }}
            >
              {outcome.wikipedia_image_url ? (
                <img className="wm-outcome-img" src={outcome.wikipedia_image_url} alt={outcome.name} style={{ width: 64, height: 64 }} />
              ) : (
                <PlaceholderAvatar name={outcome.name} color={color} />
              )}
              <div className="wm-outcome-name" style={{ marginTop: "0.5rem" }}>{outcome.name}</div>
              <div className="wm-outcome-prob" style={{ color, fontSize: "1.4rem" }}>
                {outcome.probability ? `${Math.round(outcome.probability * 100)}%` : "—"}
              </div>
              <div className="wm-outcome-odds">{outcome.decimal_odds ? formatOdds(outcome.decimal_odds) : ""}</div>

              {/* Sparkline */}
              {outcome.history && outcome.history.length >= 2 && (
                <div style={{ marginTop: "0.5rem" }}>
                  <OddsSparkline history={outcome.history} color={color} width={100} height={32} />
                </div>
              )}

              {picked && (
                <div className="wm-pick-badge">Your pick: ${match.my_pick!.stake.toLocaleString()}</div>
              )}
              {outcome.is_winner === true && (
                <div className="wm-pick-badge" style={{ background: "rgba(255,215,0,0.2)", color: "#FFD700" }}>Winner</div>
              )}
            </div>
          ))}
        </div>

        {/* Storyline */}
        {match.storyline && (
          <div className="wm-storyline">
            <button className="wm-storyline-toggle" onClick={(e) => { e.stopPropagation(); setShowStoryline(!showStoryline); }}>
              {showStoryline ? "Hide backstory ▲" : "The feud ▼"}
            </button>
            {showStoryline && <p style={{ marginTop: "0.5rem" }}>{match.storyline}</p>}
          </div>
        )}

        {/* Public picks */}
        {match.picks.length > 0 && (
          <div className="wm-picks-list">
            {match.picks.map((pick, i) => (
              <div key={i} className="wm-pick-item">
                <span className="wm-pick-player">
                  {pick.player} → {match.outcomes.find((o) => o.id === pick.outcome_id)?.name}
                </span>
                <span className="wm-pick-stake">
                  ${pick.stake.toLocaleString()}{pick.result === "won" ? " ✓" : pick.result === "lost" ? " ✗" : ""}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Multi-way matches (Fatal Four-Way, Ladder Match)
  return (
    <div className={`wm-match-card ${match.status === "resolved" ? "resolved" : ""}`}>
      <div className="wm-match-header">
        <div>
          <div className="wm-match-type">{match.match_type}</div>
          <h3 className="wm-match-title">{match.title}</h3>
        </div>
        <div style={{ textAlign: "right" }}>
          <span className={`wm-match-status ${match.status}`}>{match.status}</span>
          <div className={`wm-lock-time ${isSoon ? "soon" : ""}`} style={{ marginTop: 4 }}>
            {match.status === "resolved" ? "Final" : match.status === "locked" ? "🔒 Locked" : `Locks in ${countdown}`}
          </div>
        </div>
      </div>

      {/* Multi-way probability bar */}
      <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", margin: "0.75rem 0 0.5rem" }}>
        {match.outcomes.map((o, i) => (
          <div key={o.id} style={{ width: `${(o.probability ?? 0) * 100}%`, background: OUTCOME_COLORS[i % OUTCOME_COLORS.length], transition: "width 0.5s" }} />
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(match.outcomes.length, 3)}, 1fr)`, gap: "0.5rem" }}>
        {match.outcomes.map((outcome, i) => {
          const color = OUTCOME_COLORS[i % OUTCOME_COLORS.length];
          const isPicked = match.my_pick?.outcome_id === outcome.id;
          return (
            <div
              key={outcome.id}
              className={`wm-outcome ${isPicked ? "selected" : ""} ${outcome.is_winner === true ? "winner" : ""} ${match.status === "resolved" && outcome.is_winner === false ? "loser" : ""}`}
              onClick={() => match.status === "open" && onOutcomeClick(match, outcome)}
              style={{ padding: "0.6rem 0.4rem" }}
            >
              {outcome.wikipedia_image_url ? (
                <img className="wm-outcome-img" src={outcome.wikipedia_image_url} alt={outcome.name} style={{ width: 48, height: 48 }} />
              ) : (
                <PlaceholderAvatar name={outcome.name} color={color} />
              )}
              <div className="wm-outcome-name" style={{ fontSize: "0.7rem" }}>{outcome.name}</div>
              <div className="wm-outcome-prob" style={{ color, fontSize: "1.1rem" }}>
                {outcome.probability ? `${Math.round(outcome.probability * 100)}%` : "—"}
              </div>
              {isPicked && <div className="wm-pick-badge">${match.my_pick!.stake.toLocaleString()}</div>}
              {outcome.is_winner === true && <div className="wm-pick-badge" style={{ background: "rgba(255,215,0,0.2)", color: "#FFD700" }}>Winner</div>}
            </div>
          );
        })}
      </div>

      {match.storyline && (
        <div className="wm-storyline">
          <button className="wm-storyline-toggle" onClick={(e) => { e.stopPropagation(); setShowStoryline(!showStoryline); }}>
            {showStoryline ? "Hide backstory ▲" : "The feud ▼"}
          </button>
          {showStoryline && <p style={{ marginTop: "0.5rem" }}>{match.storyline}</p>}
        </div>
      )}

      {match.picks.length > 0 && (
        <div className="wm-picks-list">
          {match.picks.map((pick, i) => (
            <div key={i} className="wm-pick-item">
              <span className="wm-pick-player">{pick.player} → {match.outcomes.find((o) => o.id === pick.outcome_id)?.name}</span>
              <span className="wm-pick-stake">${pick.stake.toLocaleString()}{pick.result === "won" ? " ✓" : pick.result === "lost" ? " ✗" : ""}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
