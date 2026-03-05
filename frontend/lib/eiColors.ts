/**
 * Excitement Index (EI) Color & Label Mapping
 *
 * Centralizes EI score → color/label/emoji logic that's currently
 * inline in EIBadge.tsx. Use this utility when you need EI styling
 * outside of the badge component (charts, cards, TV mode, etc.).
 *
 * Thresholds match CLAUDE.md and EIBadge.tsx:
 *   90+ Incredible, 80+ Must-Watch, 70+ Exciting, 60+ Engaging,
 *   50+ Competitive, 40+ Average, 25+ Quiet, <25 Flat
 */

export interface EILevel {
  /** Short display label */
  label: string;
  /** Emoji for badges */
  emoji: string;
  /** Tailwind bg class (with opacity) */
  bgClass: string;
  /** Tailwind text class */
  textClass: string;
  /** Hex color for charts and non-Tailwind contexts */
  hex: string;
  /** RGB string for CSS custom property usage: "239 68 68" */
  rgb: string;
}

const EI_LEVELS: { minScore: number; level: EILevel }[] = [
  {
    minScore: 90,
    level: {
      label: "Incredible",
      emoji: "\u{1F525}", // 🔥
      bgClass: "bg-red-500/15",
      textClass: "text-red-400",
      hex: "#ef4444",
      rgb: "239 68 68",
    },
  },
  {
    minScore: 80,
    level: {
      label: "Must-Watch",
      emoji: "\u26A1",  // ⚡
      bgClass: "bg-red-500/15",
      textClass: "text-red-400",
      hex: "#ef4444",
      rgb: "239 68 68",
    },
  },
  {
    minScore: 70,
    level: {
      label: "Exciting",
      emoji: "\u26A1",  // ⚡
      bgClass: "bg-orange-500/15",
      textClass: "text-orange-400",
      hex: "#f97316",
      rgb: "249 115 22",
    },
  },
  {
    minScore: 60,
    level: {
      label: "Engaging",
      emoji: "\u{1F3AF}", // 🎯
      bgClass: "bg-orange-500/15",
      textClass: "text-orange-400",
      hex: "#f97316",
      rgb: "249 115 22",
    },
  },
  {
    minScore: 50,
    level: {
      label: "Competitive",
      emoji: "\u{1F3C6}", // 🏆
      bgClass: "bg-amber-500/15",
      textClass: "text-amber-400",
      hex: "#eab308",
      rgb: "234 179 8",
    },
  },
  {
    minScore: 40,
    level: {
      label: "Average",
      emoji: "\u{1F44D}", // 👍
      bgClass: "bg-amber-500/15",
      textClass: "text-amber-400",
      hex: "#eab308",
      rgb: "234 179 8",
    },
  },
  {
    minScore: 25,
    level: {
      label: "Quiet",
      emoji: "\u{1F634}", // 😴
      bgClass: "bg-gray-500/15",
      textClass: "text-gray-400",
      hex: "#6b7280",
      rgb: "107 114 128",
    },
  },
  {
    minScore: 0,
    level: {
      label: "Flat",
      emoji: "\u{1F634}", // 😴
      bgClass: "bg-gray-500/15",
      textClass: "text-gray-500",
      hex: "#4b5563",
      rgb: "75 85 99",
    },
  },
];

/**
 * Get the EI level data for a given score.
 *
 * @param score - EI score (0-100)
 * @returns EILevel with label, emoji, colors, and Tailwind classes
 */
export function getEILevel(score: number): EILevel {
  for (const entry of EI_LEVELS) {
    if (score >= entry.minScore) return entry.level;
  }
  return EI_LEVELS[EI_LEVELS.length - 1].level;
}

/**
 * Get the hex color for a given EI score.
 * Convenience wrapper for chart rendering.
 */
export function getEIColor(score: number): string {
  return getEILevel(score).hex;
}

/**
 * Get the Tailwind background + text classes for a given EI score.
 * Returns a string like "bg-red-500/15 text-red-400".
 */
export function getEIClasses(score: number): string {
  const level = getEILevel(score);
  return `${level.bgClass} ${level.textClass}`;
}

/**
 * Get the label for a given EI score.
 */
export function getEILabel(score: number): string {
  return getEILevel(score).label;
}
