"use client";

import Link from "next/link";
import type { PulseData } from "@/lib/types";
import Tooltip from "./Tooltip";

interface PulseBadgeProps {
  pulse: PulseData;
  size?: "sm" | "md" | "lg";
  showTooltip?: boolean;
  linkToExplainer?: boolean;
}

/**
 * Displays a Pulse score badge with optional tooltip explaining the metric.
 *
 * Pulse is Bain Luck's proprietary excitement metric (1-100) that measures
 * how thrilling a game is based on win probability changes over time.
 */
export default function PulseBadge({
  pulse,
  size = "sm",
  showTooltip = true,
  linkToExplainer = true,
}: PulseBadgeProps) {
  const sizeClasses = {
    sm: "text-xs px-2 py-0.5",
    md: "text-sm px-2.5 py-1",
    lg: "text-base px-3 py-1.5",
  };

  const colorClasses = pulse.score >= 81
    ? "bg-red-500/15 text-red-400"
    : pulse.score >= 61
    ? "bg-orange-500/15 text-orange-400"
    : pulse.score >= 41
    ? "bg-amber-500/15 text-amber-400"
    : "bg-surface-elevated text-text-muted";

  const badge = (
    <span
      className={`flex items-center gap-1 rounded-full font-semibold cursor-help ${sizeClasses[size]} ${colorClasses}`}
    >
      {pulse.emoji} {pulse.score}
    </span>
  );

  const tooltipContent = (
    <div className="space-y-2 min-w-[200px]">
      <div className="font-semibold text-white flex items-center gap-2">
        {pulse.emoji} Pulse: {pulse.score}
        <span className="text-white/70 font-normal">({pulse.label})</span>
      </div>

      <p className="text-white/90 text-xs leading-relaxed">
        Pulse measures game excitement based on how much win probabilities swing during play.
      </p>

      {pulse.components && (
        <div className="space-y-2 pt-2 border-t border-white/20">
          <div className="text-xs text-white/70 font-medium">What makes this exciting:</div>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between items-center">
              <span className="text-white/80">Momentum Swings</span>
              <span className="text-white font-mono">{Math.round((pulse.components.heart_rate || 0) * 100)}%</span>
            </div>
            <div className="text-white/60 text-[10px] -mt-1">How often the odds shifted</div>

            <div className="flex justify-between items-center">
              <span className="text-white/80">Drama Level</span>
              <span className="text-white font-mono">{Math.round((pulse.components.amplitude || 0) * 100)}%</span>
            </div>
            <div className="text-white/60 text-[10px] -mt-1">Size of probability swings</div>

            <div className="flex justify-between items-center">
              <span className="text-white/80">Competitiveness</span>
              <span className="text-white font-mono">{Math.round((pulse.components.vitals || 0) * 100)}%</span>
            </div>
            <div className="text-white/60 text-[10px] -mt-1">How close the matchup is</div>

            {pulse.components.lead_changes > 0 && (
              <>
                <div className="flex justify-between items-center">
                  <span className="text-white/80">Lead Changes</span>
                  <span className="text-white font-mono">{pulse.components.lead_changes}x</span>
                </div>
                <div className="text-white/60 text-[10px] -mt-1">Times the favorite flipped</div>
              </>
            )}
          </div>
        </div>
      )}

      {linkToExplainer && (
        <div className="pt-1 border-t border-white/20">
          <span className="text-xs text-sky-300 hover:text-sky-200">
            Learn more about Pulse →
          </span>
        </div>
      )}
    </div>
  );

  if (!showTooltip) {
    return badge;
  }

  const tooltipBadge = (
    <Tooltip content={tooltipContent} position="bottom">
      {badge}
    </Tooltip>
  );

  if (linkToExplainer) {
    return (
      <Link href="/pulse" className="inline-block">
        {tooltipBadge}
      </Link>
    );
  }

  return tooltipBadge;
}


/**
 * Compact inline Pulse indicator for use in lists or tight spaces.
 */
export function PulseInline({ pulse }: { pulse: PulseData }) {
  return (
    <span
      className="inline-flex items-center gap-0.5 text-xs cursor-help"
      title={`Pulse: ${pulse.score} - ${pulse.label}`}
    >
      <span>{pulse.emoji}</span>
      <span className="font-mono font-medium">{pulse.score}</span>
    </span>
  );
}
