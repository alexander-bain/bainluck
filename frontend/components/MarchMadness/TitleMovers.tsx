"use client";

import type { MarchMadnessMover } from "@/lib/types";

interface TitleMoversProps {
  movers: MarchMadnessMover[];
}

export default function TitleMovers({ movers }: TitleMoversProps) {
  if (!movers.length) return null;

  return (
    <div className="mm-section">
      <div className="mm-section-header">
        <h2 className="mm-section-title">Biggest Movers (24h)</h2>
      </div>
      <div className="mm-movers-list">
        {movers.map((mover) => {
          const isPositive = mover.movement_24h > 0;
          return (
            <div key={mover.team_name} className="mm-mover-card">
              <div>
                <div className="mm-mover-name">{mover.team_name}</div>
                <div style={{ fontSize: "0.8rem", color: "var(--mm-text-dim)" }}>
                  {(mover.probability * 100).toFixed(1)}% title odds
                  {mover.seed && <span> (#{mover.seed})</span>}
                </div>
              </div>
              <div className={`mm-mover-change ${isPositive ? "positive" : "negative"}`}>
                {isPositive ? "+" : ""}
                {(mover.movement_24h * 100).toFixed(1)}%
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
