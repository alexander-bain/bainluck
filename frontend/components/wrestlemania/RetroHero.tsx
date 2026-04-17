"use client";

interface RetroHeroProps {
  bankroll?: number;
  playerName?: string;
}

export default function RetroHero({ bankroll, playerName }: RetroHeroProps) {
  return (
    <div className="wm-hero">
      <h1 className="wm-hero-title">WrestleMania 42</h1>
      <div className="wm-hero-subtitle">Prediction Game</div>
      <div className="wm-hero-date">April 19–20, 2026 • Las Vegas</div>
      {playerName && (
        <div style={{ marginTop: "1rem" }}>
          <div className="wm-bankroll-label">
            {playerName}&apos;s Bankroll
          </div>
          <div className="wm-bankroll">
            ${bankroll?.toLocaleString("en-US", { maximumFractionDigits: 0 }) ?? "1,000,000"}
          </div>
        </div>
      )}
    </div>
  );
}
