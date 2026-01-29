"use client";

interface ProbabilityBarProps {
  homeProbability: number | null | undefined;
  awayProbability: number | null | undefined;
  homeTeam: string;
  awayTeam: string;
  showLabels?: boolean;
  size?: "sm" | "md" | "lg";
  isLive?: boolean;
}

/**
 * Redesigned probability bar:
 * - Slimmer, more subtle
 * - Green accent for live games
 * - Smooth transitions
 */
export default function ProbabilityBar({
  homeProbability,
  awayProbability,
  homeTeam,
  awayTeam,
  showLabels = true,
  size = "md",
  isLive = false,
}: ProbabilityBarProps) {
  const homeProb = homeProbability ?? 0.5;
  const awayProb = awayProbability ?? 0.5;

  const total = homeProb + awayProb;
  const normalizedHome = total > 0 ? homeProb / total : 0.5;
  const normalizedAway = total > 0 ? awayProb / total : 0.5;

  const homePercent = Math.round(normalizedHome * 100);
  const awayPercent = Math.round(normalizedAway * 100);

  const homeFavored = homePercent >= awayPercent;

  // Size classes
  const sizeClasses = {
    sm: "h-1.5",
    md: "h-2",
    lg: "h-3",
  };

  // No data state
  if (homeProbability === null && awayProbability === null) {
    return (
      <div className={`${sizeClasses[size]} w-full rounded-full bg-slate/10`} />
    );
  }

  // Colors based on state
  const favoriteColor = isLive ? "bg-emerald-500" : "bg-graphite";
  const underdogColor = "bg-slate/20";

  return (
    <div className="w-full">
      {showLabels && (
        <div className="flex justify-between text-xs text-slate mb-1">
          <span className="truncate max-w-[45%]">{homeTeam}</span>
          <span className="truncate max-w-[45%] text-right">{awayTeam}</span>
        </div>
      )}
      <div
        className={`${sizeClasses[size]} w-full rounded-full overflow-hidden flex bg-slate/10`}
      >
        {/* Home team side */}
        <div
          className={`transition-all duration-300 ${
            homeFavored ? favoriteColor : underdogColor
          }`}
          style={{ width: `${homePercent}%` }}
        />

        {/* Away team side */}
        <div
          className={`transition-all duration-300 ${
            !homeFavored ? favoriteColor : underdogColor
          }`}
          style={{ width: `${awayPercent}%` }}
        />
      </div>
    </div>
  );
}
