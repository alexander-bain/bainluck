"use client";

import { format, parseISO } from "date-fns";
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
  // Game clock is shown only when genuinely observed; a value carried forward from
  // an earlier snapshot is marked approximate ("~") rather than shown as exact, and
  // when there's no clock at all we fall back to the period, then to "—" (#925).
  const clockText = point.clock ? `${point.clockApprox ? "~" : ""}${point.clock}` : "";
  const gameState =
    [periodDisplay, clockText].filter(Boolean).join(" ") || (hasScore ? "—" : "");
  let timeOfDay = "";
  try {
    timeOfDay = format(parseISO(point.timestamp), "h:mm a");
  } catch {
    timeOfDay = "";
  }

  return (
    <div className="mt-3 border-t border-surface-border pt-3">
      <div className="flex items-start gap-3">
        {/* Game-state badge: period + clock (top), time of day (bottom) */}
        {(gameState || timeOfDay) && (
          <div className="shrink-0 flex flex-col items-start gap-0.5">
            {gameState && (
              <span className="text-xs text-text-primary font-semibold tabular-nums bg-surface-secondary px-2 py-1 rounded">
                {gameState}
              </span>
            )}
            {timeOfDay && (
              <span className="text-[10px] text-text-muted px-2 tabular-nums">
                {timeOfDay}
              </span>
            )}
          </div>
        )}

        {/* Score */}
        {hasScore && (
          <div className="shrink-0 flex items-center gap-2 text-sm font-bold tabular-nums">
            <span className="flex items-center gap-1">
              {homeTeamLogo && (
                <img src={homeTeamLogo} alt="" width={14} height={14} className="w-3.5 h-3.5 object-contain" />
              )}
              <span style={{ color: homeTeamColor || "var(--text-secondary)" }}>
                {point.homeScore}
              </span>
            </span>
            <span className="text-text-muted text-xs">-</span>
            <span className="flex items-center gap-1">
              <span style={{ color: awayTeamColor || "var(--text-secondary)" }}>
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
              <span className="font-semibold" style={{ color: homeTeamColor || "var(--text-secondary)" }}>
                {homeProb}%
              </span>
              {" — "}
              {awayShort}{" "}
              <span className="font-semibold" style={{ color: awayTeamColor || "var(--text-secondary)" }}>
                {awayProb}%
              </span>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
