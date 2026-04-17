"use client";

import { useState } from "react";
import type { WMMatch, WMOutcome } from "@/lib/types";
import WMOddsChart from "./WMOddsChart";

interface PickDrawerProps {
  match: WMMatch;
  outcome: WMOutcome;
  bankroll: number;
  onSubmit: (matchId: number, outcomeId: number, stake: number) => void;
  onDelete?: (pickId: number) => void;
  onClose: () => void;
  submitting?: boolean;
}

const PRESETS = [1000, 10000, 50000, 100000, 250000, 500000];

export default function PickDrawer({
  match,
  outcome,
  bankroll,
  onSubmit,
  onDelete,
  onClose,
  submitting,
}: PickDrawerProps) {
  const maxStake = Math.floor(bankroll);
  const [stake, setStake] = useState(Math.min(10000, maxStake));

  const decimalOdds = outcome.decimal_odds ?? 2.0;
  const potentialPayout = stake * decimalOdds;
  const potentialProfit = potentialPayout - stake;

  const existingPick = match.my_pick;

  return (
    <div className="wm-drawer-overlay" onClick={onClose}>
      <div className="wm-drawer" onClick={(e) => e.stopPropagation()}>
        <h3 className="wm-drawer-title">
          {match.title}
        </h3>

        <div style={{ textAlign: "center", marginBottom: "1rem" }}>
          {outcome.wikipedia_image_url && (
            <img
              className="wm-outcome-img"
              src={outcome.wikipedia_image_url}
              alt={outcome.name}
              style={{ width: 80, height: 80 }}
            />
          )}
          <div style={{ fontSize: "1.2rem", fontWeight: 700, marginTop: "0.5rem" }}>
            {outcome.name}
          </div>
          <div className="wm-outcome-prob" style={{ fontSize: "1.5rem" }}>
            {outcome.probability
              ? `${Math.round(outcome.probability * 100)}%`
              : "—"}
          </div>
          <div style={{ fontSize: "0.8rem", color: "var(--wm-text-muted)" }}>
            {decimalOdds.toFixed(2)}x payout
          </div>
        </div>

        {outcome.case_text && (
          <div
            style={{
              fontSize: "0.8rem",
              color: "var(--wm-text-secondary)",
              fontStyle: "italic",
              lineHeight: 1.5,
              marginBottom: "1rem",
              padding: "0.75rem",
              borderLeft: "2px solid var(--wm-neon-pink)",
            }}
          >
            {outcome.case_text}
          </div>
        )}

        {/* Full odds chart */}
        {match.outcomes.some((o) => o.history && o.history.length >= 2) && (
          <div style={{ marginBottom: "1rem" }}>
            <WMOddsChart outcomes={match.outcomes} height={180} />
          </div>
        )}

        <div className="wm-stake-section">
          <div className="wm-stake-label">
            Stake (available: ${maxStake.toLocaleString()})
          </div>
          <input
            className="wm-stake-slider"
            type="range"
            min={1}
            max={maxStake}
            value={stake}
            onChange={(e) => setStake(Number(e.target.value))}
          />
          <input
            className="wm-stake-input"
            type="number"
            min={1}
            max={maxStake}
            value={stake}
            onChange={(e) => {
              const v = Number(e.target.value);
              if (v >= 0 && v <= maxStake) setStake(v);
            }}
          />
          <div className="wm-stake-presets">
            {PRESETS.filter((p) => p <= maxStake).map((p) => (
              <button
                key={p}
                className="wm-stake-preset"
                onClick={() => setStake(p)}
              >
                ${p >= 1000 ? `${p / 1000}k` : p}
              </button>
            ))}
            <button
              className="wm-stake-preset"
              onClick={() => setStake(maxStake)}
            >
              All-in
            </button>
          </div>
        </div>

        <div className="wm-potential-payout">
          Potential payout: <span>${potentialPayout.toLocaleString("en-US", { maximumFractionDigits: 0 })}</span>
          {" "}(+${potentialProfit.toLocaleString("en-US", { maximumFractionDigits: 0 })} profit)
        </div>

        <button
          className="wm-submit-pick"
          disabled={stake < 1 || stake > maxStake || submitting}
          onClick={() => onSubmit(match.id, outcome.id, stake)}
        >
          {submitting
            ? "Placing..."
            : existingPick
            ? "Update Pick"
            : "Place Pick"}
        </button>

        {existingPick && onDelete && (
          <button
            style={{
              width: "100%",
              padding: "0.5rem",
              marginTop: "0.5rem",
              background: "transparent",
              border: "1px solid var(--wm-card-border)",
              color: "var(--wm-text-muted)",
              fontFamily: "'Bebas Neue', Impact, sans-serif",
              fontSize: "0.9rem",
              letterSpacing: "0.1em",
              cursor: "pointer",
              borderRadius: "6px",
            }}
            onClick={() => onDelete(existingPick.id)}
          >
            Remove Pick
          </button>
        )}

        <button
          style={{
            width: "100%",
            padding: "0.5rem",
            marginTop: "0.5rem",
            background: "transparent",
            border: "none",
            color: "var(--wm-text-muted)",
            fontSize: "0.8rem",
            cursor: "pointer",
          }}
          onClick={onClose}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
