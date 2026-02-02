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
 * Pulse is OddsTracker's proprietary excitement metric (1-100) that measures
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
    ? "bg-red-100 text-red-700"
    : pulse.score >= 61
    ? "bg-orange-100 text-orange-700"
    : pulse.score >= 41
    ? "bg-amber-100 text-amber-700"
    : "bg-slate-100 text-slate-600";

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
        <div className="space-y-1 pt-1 border-t border-white/20">
          <div className="text-xs text-white/70 font-medium">Components:</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
            <span className="text-white/80">Heart Rate:</span>
            <span className="text-white font-mono">{Math.round(pulse.components.heart_rate)}</span>
            <span className="text-white/80">Amplitude:</span>
            <span className="text-white font-mono">{Math.round(pulse.components.amplitude)}</span>
            <span className="text-white/80">Vitals:</span>
            <span className="text-white font-mono">{Math.round(pulse.components.vitals)}</span>
            <span className="text-white/80">Lead Changes:</span>
            <span className="text-white font-mono">{Math.round(pulse.components.lead_changes)}</span>
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
