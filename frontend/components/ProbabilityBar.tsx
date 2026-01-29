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
 * Horizontal probability bar per design brief.
 * Charcoal for favorite side, Fog for underdog.
 * No gradients, no team colors.
 */
export default function ProbabilityBar({
  homeProbability,
  awayProbability,
  homeTeam,
  awayTeam,
  showLabels = true,
  size = "md",
}: ProbabilityBarProps) {
  const homeProb = homeProbability ?? 0.5;
  const awayProb = awayProbability ?? 0.5;

  const total = homeProb + awayProb;
  const normalizedHome = total > 0 ? homeProb / total : 0.5;
  const normalizedAway = total > 0 ? awayProb / total : 0.5;

  const homePercent = Math.round(normalizedHome * 100);
  const awayPercent = Math.round(normalizedAway * 100);

  const homeFavored = homePercent >= awayPercent;

  // Size classes per design brief
  const sizeClasses = {
    sm: "h-2",
    md: "h-2",
    lg: "h-3",
  };

  // No data state
  if (homeProbability === null && awayProbability === null) {
    return (
      <div className={`${sizeClasses[size]} w-full rounded bg-mist`} />
    );
  }

  return (
    <div className="w-full">
      {showLabels && (
        <div className="flex justify-between text-caption text-slate mb-1">
          <span className="truncate max-w-[45%]">{homeTeam}</span>
          <span className="truncate max-w-[45%] text-right">{awayTeam}</span>
        </div>
      )}
      <div
        className={`${sizeClasses[size]} w-full rounded overflow-hidden flex`}
      >
        {/* Home team side */}
        <div
          className={`probability-transition ${
            homeFavored ? "bg-charcoal" : "bg-fog"
          }`}
          style={{ width: `${homePercent}%` }}
        />

        {/* Away team side */}
        <div
          className={`probability-transition ${
            !homeFavored ? "bg-charcoal" : "bg-fog"
          }`}
          style={{ width: `${awayPercent}%` }}
        />
      </div>
    </div>
  );
}
