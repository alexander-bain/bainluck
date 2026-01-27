"use client";

interface ProbabilityBarProps {
  homeProbability: number | null | undefined;
  awayProbability: number | null | undefined;
  homeTeam: string;
  awayTeam: string;
  showLabels?: boolean;
  size?: "sm" | "md" | "lg";
}

/**
 * Visual bar showing probability split between home and away teams.
 * Home team on left (green gradient), away team on right (blue gradient).
 */
export default function ProbabilityBar({
  homeProbability,
  awayProbability,
  homeTeam,
  awayTeam,
  showLabels = true,
  size = "md",
}: ProbabilityBarProps) {
  // Handle null probabilities
  const homeProb = homeProbability ?? 0.5;
  const awayProb = awayProbability ?? 0.5;

  // Normalize to ensure they sum to 1
  const total = homeProb + awayProb;
  const normalizedHome = total > 0 ? homeProb / total : 0.5;
  const normalizedAway = total > 0 ? awayProb / total : 0.5;

  const homePercent = Math.round(normalizedHome * 100);
  const awayPercent = Math.round(normalizedAway * 100);

  // Determine which team is favored
  const homeFavored = homePercent >= awayPercent;

  // Size classes
  const sizeClasses = {
    sm: "h-6 text-xs",
    md: "h-8 text-sm",
    lg: "h-10 text-base",
  };

  // No data state
  if (homeProbability === null && awayProbability === null) {
    return (
      <div
        className={`${sizeClasses[size]} w-full rounded-lg bg-gray-200 flex items-center justify-center text-gray-500`}
      >
        No odds available
      </div>
    );
  }

  return (
    <div className="w-full">
      {showLabels && (
        <div className="flex justify-between text-xs text-gray-600 mb-1">
          <span className="truncate max-w-[45%]">{homeTeam}</span>
          <span className="truncate max-w-[45%] text-right">{awayTeam}</span>
        </div>
      )}
      <div
        className={`${sizeClasses[size]} w-full rounded-lg overflow-hidden flex shadow-sm`}
      >
        {/* Home team side */}
        <div
          className={`flex items-center justify-center font-bold text-white transition-all duration-300 ${
            homeFavored
              ? "bg-gradient-to-r from-green-600 to-green-500"
              : "bg-gradient-to-r from-gray-500 to-gray-400"
          }`}
          style={{ width: `${homePercent}%`, minWidth: homePercent > 0 ? "40px" : "0" }}
        >
          {homePercent > 15 && `${homePercent}%`}
        </div>

        {/* Away team side */}
        <div
          className={`flex items-center justify-center font-bold text-white transition-all duration-300 ${
            !homeFavored
              ? "bg-gradient-to-l from-blue-600 to-blue-500"
              : "bg-gradient-to-l from-gray-500 to-gray-400"
          }`}
          style={{ width: `${awayPercent}%`, minWidth: awayPercent > 0 ? "40px" : "0" }}
        >
          {awayPercent > 15 && `${awayPercent}%`}
        </div>
      </div>
    </div>
  );
}
