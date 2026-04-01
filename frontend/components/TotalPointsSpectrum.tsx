"use client";

import { useMemo } from "react";
import type { GameMarketsResponse } from "@/lib/api";

interface TotalPointsSpectrumProps {
  data: GameMarketsResponse;
}

/**
 * Total Points Spectrum — visualizes Kalshi/Polymarket over/under thresholds
 * as a color-coded spectrum bar with current pace marker.
 *
 * Design: event-detail-v5.html mockup, Level 3 "Game Markets"
 */
export default function TotalPointsSpectrum({ data }: TotalPointsSpectrumProps) {
  const { totals, pace } = data;

  // Only show game_total thresholds (not half/quarter/team)
  const thresholds = useMemo(
    () => totals.filter((t) => t.market_type === "game_total"),
    [totals]
  );

  if (thresholds.length < 2) return null;

  const minThreshold = thresholds[0].threshold;
  const maxThreshold = thresholds[thresholds.length - 1].threshold;
  const range = maxThreshold - minThreshold;

  // Find the "center" — threshold closest to 50% over probability
  const centerThreshold = thresholds.reduce((closest, t) =>
    Math.abs(t.over_probability - 0.5) < Math.abs(closest.over_probability - 0.5) ? t : closest
  );

  // Pace marker position (0-100%)
  const pacePosition = pace?.projected_total
    ? Math.max(0, Math.min(100, ((pace.projected_total - minThreshold + range * 0.1) / (range * 1.2)) * 100))
    : null;

  // Source label
  const sources = [...new Set(thresholds.map((t) => t.source))];
  const sourceLabel = sources.map((s) => s === "kalshi" ? "Kalshi" : s === "polymarket" ? "Polymarket" : s).join(" · ");

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border overflow-hidden">
      <div className="px-4 pt-3 pb-2">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold text-text-primary">Total Points</span>
          <span className="text-micro text-text-muted">
            {sourceLabel} · {thresholds.length} thresholds
          </span>
        </div>

        {/* Current Pace pill */}
        {pace && pace.projected_total && (
          <div className="flex items-center gap-2 mb-3 px-3 py-1.5 rounded-lg bg-gradient-to-r from-surface-elevated to-blue-50 border border-surface-border">
            <span className="text-micro font-semibold text-text-muted uppercase tracking-wider">
              Current Pace
            </span>
            <span className="text-base font-extrabold text-blue-500 tracking-tight">
              {pace.projected_total}
            </span>
            <span className="text-micro text-text-secondary ml-auto">
              {pace.total_scored} scored · {pace.time_remaining_display}
            </span>
          </div>
        )}

        {/* Spectrum bar */}
        <div className="relative h-8 rounded-lg overflow-visible bg-surface-elevated mb-1">
          {/* Color gradient segments */}
          {thresholds.map((t, i) => {
            const pos = ((t.threshold - minThreshold + range * 0.1) / (range * 1.2)) * 100;
            const width = 100 / (thresholds.length + 1);
            // Color: green for likely over (>60%), yellow for toss-up, red for unlikely
            const opacity = 0.15 + t.over_probability * 0.5;
            const hue = t.over_probability > 0.6 ? "bg-green-500" :
                        t.over_probability > 0.35 ? "bg-yellow-500" : "bg-red-500";
            return (
              <div
                key={i}
                className={`absolute top-0 bottom-0 ${hue}`}
                style={{
                  left: `${Math.max(0, pos - width / 2)}%`,
                  width: `${width}%`,
                  opacity,
                }}
              />
            );
          })}

          {/* Pace marker */}
          {pacePosition !== null && (
            <div
              className="absolute top-[-4px] bottom-[-4px] w-0.5 bg-text-primary z-10 rounded-full"
              style={{ left: `${pacePosition}%` }}
            >
              <div className="absolute top-[-18px] left-1/2 -translate-x-1/2 bg-text-primary text-surface-deep text-[8px] font-bold px-1 py-0.5 rounded whitespace-nowrap">
                {pace?.projected_total} pace
              </div>
            </div>
          )}
        </div>

        {/* Threshold ticks */}
        <div className="flex justify-between px-0.5">
          {thresholds.map((t, i) => {
            const prob = Math.round(t.over_probability * 100);
            const isCenter = t === centerThreshold;
            const probColor = prob >= 65 ? "text-green-500" :
                              prob >= 35 ? "text-amber-500" : "text-red-500";
            return (
              <div
                key={i}
                className="flex flex-col items-center"
                style={{ minWidth: 0, flex: "1 1 0" }}
              >
                <span className={`text-[8px] font-medium ${isCenter ? "font-bold text-text-primary" : "text-text-muted"}`}>
                  {t.threshold}
                </span>
                <span className={`text-[7px] font-semibold ${probColor}`}>
                  {prob}%
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
