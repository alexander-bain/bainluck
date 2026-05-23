"use client";

import { motion } from "framer-motion";

interface ProbabilityBarProps {
  /** Home team probability 0-1 */
  homeProbability: number | null | undefined;
  /** Away team probability 0-1 (if omitted, computed as 1 - homeProbability) */
  awayProbability?: number | null | undefined;
  /** Home team name (optional, for legacy compat — not rendered) */
  homeTeam?: string;
  /** Away team name (optional, for legacy compat — not rendered) */
  awayTeam?: string;
  /** Show labels above bar (legacy compat — ignored in new design) */
  showLabels?: boolean;
  /** Size preset (legacy compat — maps to height) */
  size?: "sm" | "md" | "lg";
  /** Whether game is live (legacy compat — unused in new design) */
  isLive?: boolean;
  /** Home team color — CSS color string or hex */
  homeColor?: string;
  /** Away team color — CSS color string or hex */
  awayColor?: string;
  /** Whether home team is the favorite (brighter segment) */
  homeFavorite?: boolean;
  /** Bar height in px (overrides size) */
  height?: number;
  /** Animate width transitions (default true) */
  animated?: boolean;
  /** Use CSS variable colors instead of props (default false) */
  useCSSVars?: boolean;
  /** Additional CSS class */
  className?: string;
}

const SIZE_TO_HEIGHT: Record<string, number> = {
  sm: 4,
  md: 6,
  lg: 8,
};

/**
 * Team-colored probability bar with animated segments, inner glow, and gap.
 *
 * Signature design element — two segments with rounded ends, a 1.5px gap,
 * and subtle inner glow on the favorite's segment.
 */
export default function ProbabilityBar({
  homeProbability,
  awayProbability,
  homeColor,
  awayColor,
  homeFavorite,
  height,
  size = "md",
  animated = true,
  useCSSVars = false,
  className,
}: ProbabilityBarProps) {
  const homeProb = homeProbability ?? 0.5;
  const awayProb = awayProbability ?? (1 - homeProb);
  const total = homeProb + awayProb;
  const homeWidth = total > 0 ? (homeProb / total) * 100 : 50;
  const awayWidth = 100 - homeWidth;

  const isFav = homeFavorite ?? homeWidth >= 50;
  const barHeight = height ?? SIZE_TO_HEIGHT[size] ?? 6;

  // Resolve colors
  const hColor = useCSSVars
    ? "rgb(var(--team-home-primary))"
    : homeColor || "rgb(var(--team-home-primary))";
  const aColor = useCSSVars
    ? "rgb(var(--team-away-primary))"
    : awayColor || "rgb(var(--team-away-primary))";

  // No data state
  if (homeProbability === null || homeProbability === undefined) {
    return (
      <div
        className={`w-full rounded-full bg-surface-border/30 ${className ?? ""}`}
        style={{ height: `${barHeight}px` }}
      />
    );
  }

  // Build inner glow shadow — subtle highlight on the favorite segment
  const glowFor = (color: string, isFavSide: boolean) => {
    if (!isFavSide) return undefined;
    return `inset 0 1px 2px rgba(0,0,0,0.1)`;
  };

  return (
    <div
      className={`flex w-full gap-[1.5px] ${className ?? ""}`}
      style={{ height: `${barHeight}px` }}
      role="meter"
      aria-valuenow={Math.round(homeProb * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Win probability"
    >
      {animated ? (
        <>
          <motion.div
            className="rounded-full"
            style={{
              backgroundColor: hColor,
              opacity: isFav ? 1 : 0.4,
              boxShadow: glowFor(hColor, isFav),
            }}
            animate={{ width: `${homeWidth}%` }}
            transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
          />
          <motion.div
            className="rounded-full"
            style={{
              backgroundColor: aColor,
              opacity: !isFav ? 1 : 0.4,
              boxShadow: glowFor(aColor, !isFav),
            }}
            animate={{ width: `${awayWidth}%` }}
            transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
          />
        </>
      ) : (
        <>
          <div
            className="rounded-full transition-all duration-300"
            style={{
              width: `${homeWidth}%`,
              backgroundColor: hColor,
              opacity: isFav ? 1 : 0.4,
              boxShadow: glowFor(hColor, isFav),
            }}
          />
          <div
            className="rounded-full transition-all duration-300"
            style={{
              width: `${awayWidth}%`,
              backgroundColor: aColor,
              opacity: !isFav ? 1 : 0.4,
              boxShadow: glowFor(aColor, !isFav),
            }}
          />
        </>
      )}
    </div>
  );
}
