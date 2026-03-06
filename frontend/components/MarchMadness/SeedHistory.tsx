"use client";

import type { SeedHistoryEntry, NotableUpset } from "@/lib/types";

interface SeedHistoryProps {
  seedHistory: SeedHistoryEntry[];
  notableUpsets: NotableUpset[];
}

export default function SeedHistory({ seedHistory, notableUpsets }: SeedHistoryProps) {
  return (
    <div className="mm-section">
      <div className="mm-section-header">
        <h2 className="mm-section-title">Historical Seed Matchups</h2>
        <span className="mm-section-badge">First Round</span>
      </div>

      <div className="mm-seed-grid">
        {seedHistory.map((entry) => {
          const upsetPct = entry.upset_pct * 100;
          const barColor = upsetPct > 40
            ? "#ef4444"
            : upsetPct > 25
            ? "#f59e0b"
            : upsetPct > 10
            ? "#22c55e"
            : "var(--mm-wood-accent)";

          return (
            <div key={entry.label} className="mm-seed-card">
              <div className="mm-seed-matchup">{entry.label}</div>
              <div className="mm-seed-bar">
                <div
                  className="mm-seed-bar-fill"
                  style={{
                    width: `${upsetPct}%`,
                    background: barColor,
                  }}
                />
              </div>
              <div className="mm-seed-stats">
                #{entry.lower_seed} wins {upsetPct.toFixed(1)}% of the time
                <span style={{ opacity: 0.6 }}> ({entry.matchups} games)</span>
              </div>
            </div>
          );
        })}
      </div>

      {notableUpsets.length > 0 && (
        <>
          <div className="mm-court-line" />
          <div className="mm-section-header">
            <h2 className="mm-section-title">Notable Upsets</h2>
          </div>
          <div className="mm-notable-grid">
            {notableUpsets.map((upset, i) => (
              <div key={i} className="mm-notable-card">
                <div className="mm-notable-header">
                  <span className="mm-notable-year">{upset.year}</span>
                  <span className="mm-notable-seeds">
                    #{upset.seed_winner} over #{upset.seed_loser}
                  </span>
                </div>
                <div className="mm-notable-result">
                  {upset.winner} {upset.score} {upset.loser}
                </div>
                <div className="mm-notable-note">{upset.note}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
