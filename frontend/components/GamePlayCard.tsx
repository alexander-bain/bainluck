"use client";

import type { ActiveChartPoint } from "@/lib/types";

interface GamePlayCardProps {
  activePoint: ActiveChartPoint | null;
  homeTeam: string;
  awayTeam: string;
  homeTeamColor?: string;
  awayTeamColor?: string;
  homeTeamLogo?: string;
  awayTeamLogo?: string;
  /** Most recent chart point (shown when not hovering) */
  lastPoint?: ActiveChartPoint | null;
}

/** Format period number into display string */
function formatPeriod(period?: string | null): string {
  if (!period) return "";
  // Already formatted (e.g., "1st Quarter", "Halftime")
  if (period.length > 2) return period;
  // Numeric period
  const num = parseInt(period, 10);
  if (isNaN(num)) return period;
  const suffix = num === 1 ? "st" : num === 2 ? "nd" : num === 3 ? "rd" : "th";
  return `Q${num}`;
}

/**
 * ESPN-style game play card displayed below the odds chart.
 * Updates as the user hovers/scrubs across the chart, showing:
 * - Score (team-colored)
 * - Period and clock
 * - Scoring play description (when hovering over one)
 * - Win probability (when between scoring plays)
 */
export default function GamePlayCard({
  activePoint,
  homeTeam,
  awayTeam,
  homeTeamColor,
  awayTeamColor,
  homeTeamLogo,
  awayTeamLogo,
  lastPoint,
}: GamePlayCardProps) {
  const point = activePoint || lastPoint;
  if (!point) return null;

  const hasScore = point.homeScore != null && point.awayScore != null;
  const hasScoringPlay = !!point.scoringPlay;
  const homeProb = Math.round(point.homeProb * 100);
  const awayProb = Math.round(point.awayProb * 100);

  // Short team names (last word of full name, e.g., "Boston Celtics" → "Celtics")
  const homeShort = homeTeam.split(" ").pop() || homeTeam;
  const awayShort = awayTeam.split(" ").pop() || awayTeam;

  const periodDisplay = formatPeriod(point.period);
  const clockDisplay = point.clock || "";
  const timeDisplay = [periodDisplay, clockDisplay].filter(Boolean).join(" · ");

  return (
    <div className="mt-3 border-t border-gray-100 pt-3">
      <div className="flex items-start gap-3">
        {/* Time/Period badge */}
        {timeDisplay && (
          <div className="shrink-0 text-xs text-text-muted font-medium bg-gray-50 px-2 py-1 rounded">
            {timeDisplay}
          </div>
        )}

        {/* Score */}
        {hasScore && (
          <div className="shrink-0 flex items-center gap-2 text-sm font-bold tabular-nums">
            <span className="flex items-center gap-1">
              {homeTeamLogo && (
                <img src={homeTeamLogo} alt="" width={14} height={14} className="w-3.5 h-3.5 object-contain" />
              )}
              <span style={{ color: homeTeamColor || "#374151" }}>
                {point.homeScore}
              </span>
            </span>
            <span className="text-text-muted text-xs">-</span>
            <span className="flex items-center gap-1">
              <span style={{ color: awayTeamColor || "#374151" }}>
                {point.awayScore}
              </span>
              {awayTeamLogo && (
                <img src={awayTeamLogo} alt="" width={14} height={14} className="w-3.5 h-3.5 object-contain" />
              )}
            </span>
          </div>
        )}

        {/* Play description or probability context */}
        <div className="flex-1 min-w-0">
          {hasScoringPlay ? (
            <div>
              <p className="text-xs font-semibold text-red-600 flex items-center gap-1">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                {point.scoringPlay!.type && (
                  <span className="text-text-muted font-normal">
                    {point.scoringPlay!.type}
                  </span>
                )}
              </p>
              <p className="text-xs text-text-primary mt-0.5 truncate">
                {point.scoringPlay!.description || point.scoringPlay!.short_text || ""}
              </p>
            </div>
          ) : (
            <p className="text-xs text-text-muted">
              {homeShort}{" "}
              <span className="font-semibold" style={{ color: homeTeamColor || "#374151" }}>
                {homeProb}%
              </span>
              {" — "}
              {awayShort}{" "}
              <span className="font-semibold" style={{ color: awayTeamColor || "#374151" }}>
                {awayProb}%
              </span>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
