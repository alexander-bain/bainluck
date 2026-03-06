"use client";

import { useMemo } from "react";

// ── Negative binomial series probability (ported from backend) ──

function comb(n: number, k: number): number {
  if (k < 0 || k > n) return 0;
  if (k === 0 || k === n) return 1;
  let result = 1;
  for (let i = 0; i < k; i++) {
    result = (result * (n - i)) / (i + 1);
  }
  return Math.round(result);
}

/**
 * Compute probability of winning a best-of-N series.
 *
 * Uses the negative binomial distribution: given P(win each remaining game),
 * what's P(reaching `gamesToWin` before opponent does)?
 */
function computeSeriesWinProb(
  teamWinProbThisGame: number,
  teamGamesWon: number,
  opponentGamesWon: number,
  gamesToWin: number = 4
): number {
  const teamNeeds = gamesToWin - teamGamesWon;
  const oppNeeds = gamesToWin - opponentGamesWon;

  if (teamNeeds <= 0) return 1.0;
  if (oppNeeds <= 0) return 0.0;

  const p = Math.max(0, Math.min(1, teamWinProbThisGame));
  const totalRemaining = teamNeeds + oppNeeds - 1;

  let prob = 0;
  for (let gamesBeforeClinch = teamNeeds - 1; gamesBeforeClinch < totalRemaining; gamesBeforeClinch++) {
    const losses = gamesBeforeClinch - (teamNeeds - 1);
    prob += comb(gamesBeforeClinch, teamNeeds - 1) * Math.pow(p, teamNeeds) * Math.pow(1 - p, losses);
  }

  return prob;
}

function seriesStateLabel(
  teamGamesWon: number,
  opponentGamesWon: number,
  gamesToWin: number = 4,
  teamName?: string
): string {
  const name = teamName || "Team";
  if (teamGamesWon >= gamesToWin) return `${name} win series ${teamGamesWon}-${opponentGamesWon}`;
  if (opponentGamesWon >= gamesToWin) return `${name} lose series ${teamGamesWon}-${opponentGamesWon}`;
  if (teamGamesWon === opponentGamesWon) return `Series tied ${teamGamesWon}-${opponentGamesWon}`;
  if (teamGamesWon > opponentGamesWon) return `${name} lead ${teamGamesWon}-${opponentGamesWon}`;
  return `${name} trail ${teamGamesWon}-${opponentGamesWon}`;
}

// ── Component ──

interface SeriesProbabilityProps {
  /** Home team win probability for this game (0-1) */
  homeWinProb: number;
  /** Home team series wins */
  homeSeriesWins: number;
  /** Away team series wins */
  awaySeriesWins: number;
  /** Games needed to win series (default 4 for best-of-7) */
  gamesToWin?: number;
  homeTeam: string;
  awayTeam: string;
  homeTeamColor?: string;
  awayTeamColor?: string;
  className?: string;
}

export default function SeriesProbability({
  homeWinProb,
  homeSeriesWins,
  awaySeriesWins,
  gamesToWin = 4,
  homeTeam,
  awayTeam,
  homeTeamColor,
  awayTeamColor,
  className,
}: SeriesProbabilityProps) {
  const result = useMemo(() => {
    const homeSeriesProb = computeSeriesWinProb(homeWinProb, homeSeriesWins, awaySeriesWins, gamesToWin);
    const awaySeriesProb = 1 - homeSeriesProb;
    const stateLabel = seriesStateLabel(homeSeriesWins, awaySeriesWins, gamesToWin, homeTeam.split(" ").pop());
    const totalGames = gamesToWin * 2 - 1;

    return { homeSeriesProb, awaySeriesProb, stateLabel, totalGames };
  }, [homeWinProb, homeSeriesWins, awaySeriesWins, gamesToWin, homeTeam]);

  const homeColor = homeTeamColor || "#16a34a";
  const awayColor = awayTeamColor || "#2563eb";
  const homeShort = homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeam.split(" ").pop() || awayTeam;
  const homeSeriesPct = Math.round(result.homeSeriesProb * 100);
  const awaySeriesPct = Math.round(result.awaySeriesProb * 100);
  const isSeriesOver = homeSeriesWins >= gamesToWin || awaySeriesWins >= gamesToWin;

  if (isSeriesOver) return null;

  // Series win dots — show which games have been won
  const maxGames = gamesToWin * 2 - 1;
  const homeDots = Array.from({ length: gamesToWin }, (_, i) => i < homeSeriesWins);
  const awayDots = Array.from({ length: gamesToWin }, (_, i) => i < awaySeriesWins);

  return (
    <div className={`bg-surface-elevated rounded-lg p-4 ${className ?? ""}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary">Series Probability</h3>
        <span className="text-xs text-text-muted">Best of {maxGames}</span>
      </div>

      {/* Series state label */}
      <p className="text-xs text-text-secondary mb-3">{result.stateLabel}</p>

      {/* Series win dots */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-text-secondary mr-1" style={{ color: homeColor }}>
            {homeShort}
          </span>
          {homeDots.map((won, i) => (
            <div
              key={`h-${i}`}
              className="w-3 h-3 rounded-full border-2 transition-colors"
              style={{
                borderColor: homeColor,
                backgroundColor: won ? homeColor : "transparent",
              }}
            />
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          {awayDots.map((won, i) => (
            <div
              key={`a-${i}`}
              className="w-3 h-3 rounded-full border-2 transition-colors"
              style={{
                borderColor: awayColor,
                backgroundColor: won ? awayColor : "transparent",
              }}
            />
          ))}
          <span className="text-xs text-text-secondary ml-1" style={{ color: awayColor }}>
            {awayShort}
          </span>
        </div>
      </div>

      {/* Probability bar */}
      <div className="relative h-6 rounded-full overflow-hidden bg-surface-deep">
        <div
          className="absolute inset-y-0 left-0 rounded-l-full transition-all duration-500"
          style={{ width: `${homeSeriesPct}%`, backgroundColor: homeColor }}
        />
        <div
          className="absolute inset-y-0 right-0 rounded-r-full transition-all duration-500"
          style={{ width: `${awaySeriesPct}%`, backgroundColor: awayColor }}
        />
        {/* Percentage labels inside the bar */}
        <div className="absolute inset-0 flex items-center justify-between px-2">
          <span className="text-xs font-bold font-mono text-white drop-shadow-sm">
            {homeSeriesPct}%
          </span>
          <span className="text-xs font-bold font-mono text-white drop-shadow-sm">
            {awaySeriesPct}%
          </span>
        </div>
      </div>

      {/* Context */}
      <p className="text-[10px] text-text-muted mt-2 text-center">
        Based on {Math.round(homeWinProb * 100)}% game win probability via negative binomial model
      </p>
    </div>
  );
}
