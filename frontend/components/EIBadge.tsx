"use client";

import { motion } from "framer-motion";
import type { EIData } from "@/lib/types";
import { getEIClasses, getEIRingClass } from "@/lib/eiColors";
import { eiBreathingTransition } from "@/lib/animations";
import Tooltip from "./Tooltip";

interface EIBadgeProps {
  ei: EIData;
  size?: "sm" | "md" | "lg";
  showTooltip?: boolean;
  /** When true, badge pulses with EI-mapped breathing speed */
  isLive?: boolean;
}

/**
 * Displays an Excitement Index (EI) score badge with optional tooltip.
 *
 * EI is Bain Luck's excitement metric (1-100) that measures how thrilling a game
 * is based on cumulative win probability changes over time.
 */
export default function EIBadge({
  ei,
  size = "sm",
  showTooltip = true,
  isLive = false,
}: EIBadgeProps) {
  const sizeClasses = {
    sm: "text-xs px-2 py-0.5",
    md: "text-sm px-2.5 py-1",
    lg: "text-base px-3 py-1.5",
  };

  const colorClasses = getEIClasses(ei.score);
  const ringClass = getEIRingClass(ei.score);
  const showRingGlow = isLive && ei.score >= 70;

  const badge = (
    <motion.span
      className={`flex items-center gap-1 rounded-full font-semibold cursor-help ${sizeClasses[size]} ${colorClasses} ${
        showRingGlow ? `ring-2 ${ringClass}` : ""
      }`}
      {...(isLive ? {
        animate: { scale: [1, 1.03, 1] },
        transition: eiBreathingTransition(ei.score),
      } : {})}
    >
      {ei.emoji} {ei.score}
    </motion.span>
  );

  const tooltipContent = (
    <div className="space-y-2 min-w-[200px]">
      <div className="font-semibold text-white flex items-center gap-2">
        {ei.emoji} Excitement Index: {ei.score}
        <span className="text-white/70 font-normal">({ei.label})</span>
      </div>

      <p className="text-white/90 text-xs leading-relaxed">
        Measures game excitement based on how much win probabilities swing during play.
        Higher = more dramatic swings and lead changes.
      </p>

      {ei.metadata && (
        <div className="space-y-2 pt-2 border-t border-white/20">
          <div className="text-xs text-white/70 font-medium">Game details:</div>
          <div className="space-y-1.5 text-xs">
            {ei.metadata.raw_ei != null && (
              <>
                <div className="flex justify-between items-center">
                  <span className="text-white/80">Probability Travel</span>
                  <span className="text-white font-mono">{ei.metadata.raw_ei.toFixed(2)}</span>
                </div>
                <div className="text-white/60 text-[10px] -mt-1">Cumulative probability distance</div>
              </>
            )}

            {ei.metadata.lead_changes > 0 && (
              <>
                <div className="flex justify-between items-center">
                  <span className="text-white/80">Lead Changes</span>
                  <span className="text-white font-mono">{ei.metadata.lead_changes}x</span>
                </div>
                <div className="text-white/60 text-[10px] -mt-1">Times the favorite flipped</div>
              </>
            )}

            {ei.metadata.comeback_factor != null && ei.metadata.comeback_factor > 0 && (
              <>
                <div className="flex justify-between items-center">
                  <span className="text-white/80">Comeback Factor</span>
                  <span className="text-white font-mono">{Math.round(ei.metadata.comeback_factor * 100)}%</span>
                </div>
                <div className="text-white/60 text-[10px] -mt-1">Winner&apos;s lowest probability</div>
              </>
            )}
          </div>
        </div>
      )}

    </div>
  );

  if (!showTooltip) {
    return badge;
  }

  return (
    <Tooltip content={tooltipContent} position="bottom">
      {badge}
    </Tooltip>
  );
}


/**
 * Compact inline EI indicator for use in lists or tight spaces.
 */
export function EIInline({ ei }: { ei: EIData }) {
  return (
    <span
      className="inline-flex items-center gap-0.5 text-xs cursor-help"
      title={`EI: ${ei.score} - ${ei.label}`}
    >
      <span>{ei.emoji}</span>
      <span className="font-mono font-medium">{ei.score}</span>
    </span>
  );
}

// Backward compatibility — re-export old name
export { EIInline as PulseInline };
