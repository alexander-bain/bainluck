"use client";

import { motion } from "@/components/motion";
import { probabilityBarPair } from "@/lib/probabilityBarPair";

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
  /** Additional CSS class */
  className?: string;
}

const SIZE_TO_HEIGHT: Record<string, number> = {
  sm: 4,
  md: 6,
  lg: 8,
};

/**
 * The two halves are deliberately not equal: the favourite is full strength and
 * the underdog is dimmed, so the bar says who is ahead before it is read. That
 * is the design and this ship does not change it — it makes the COLOUR decision
 * aware of it, because a colour that survives at 1 can be invisible at 0.4.
 */
export const FAVORITE_OPACITY = 1;
export const UNDERDOG_OPACITY = 0.4;

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
  className,
}: ProbabilityBarProps) {
  const homeProb = homeProbability ?? 0.5;
  const awayProb = awayProbability ?? (1 - homeProb);
  const total = homeProb + awayProb;
  const homeWidth = total > 0 ? (homeProb / total) * 100 : 50;
  const awayWidth = 100 - homeWidth;

  const isFav = homeFavorite ?? homeWidth >= 50;
  const barHeight = height ?? SIZE_TO_HEIGHT[size] ?? 6;

  // Which half is dimmed. Derived once and then used BOTH to decide the colours
  // and to paint them — the two must not be computed separately, or the module
  // below rules on a pixel this component never draws.
  const homeOpacity = isFav ? FAVORITE_OPACITY : UNDERDOG_OPACITY;
  const awayOpacity = isFav ? UNDERDOG_OPACITY : FAVORITE_OPACITY;

  // Colours are decided as a PAIR, at the opacity each half is actually painted
  // at (#4470b, the shared-card sibling of #2962 and #4470).
  //
  // What this replaces: both halves read `rgb(var(--team-*-primary))`, i.e. the
  // raw `teams.primary_color` with no rule applied and a gray-500 token default.
  // A CSS variable cannot be reasoned about — the component could not tell
  // whether it was about to paint white on white, and for 22 teams carrying
  // `#ffffff` it was. Measured on production at 390px on 2026-09-09 across six
  // league pages: 36 of 220 segments (16.4%) composited below 1.5:1 against the
  // card, 26 of them at exactly 1.00 — Sevilla, Valencia, Leeds, Fulham, Real
  // Madrid, Augsburg, Eintracht Frankfurt among them. The bar did not show a
  // faint number; it showed no number at all, on the side the card is about.
  //
  // Passing real colours rather than variables is what makes the rule possible,
  // so `useCSSVars` is gone: a caller now says what the colours ARE.
  const pair = probabilityBarPair(awayColor, homeColor, {
    away: awayOpacity,
    home: homeOpacity,
  });
  const hColor = pair.home;
  const aColor = pair.away;

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
              opacity: homeOpacity,
              boxShadow: glowFor(hColor, isFav),
            }}
            animate={{ width: `${homeWidth}%` }}
            transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
          />
          <motion.div
            className="rounded-full"
            style={{
              backgroundColor: aColor,
              opacity: awayOpacity,
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
              opacity: homeOpacity,
              boxShadow: glowFor(hColor, isFav),
            }}
          />
          <div
            className="rounded-full transition-all duration-300"
            style={{
              width: `${awayWidth}%`,
              backgroundColor: aColor,
              opacity: awayOpacity,
              boxShadow: glowFor(aColor, !isFav),
            }}
          />
        </>
      )}
    </div>
  );
}
