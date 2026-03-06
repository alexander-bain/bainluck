/**
 * Static data for March Madness pages.
 * Tournament dates, round info, region data for the 2026 NCAA tournaments.
 */

export const ROUND_ORDER = [
  "First Four",
  "Round of 64",
  "Round of 32",
  "Sweet 16",
  "Elite Eight",
  "Final Four",
  "Championship",
] as const;

export const ROUND_SHORT: Record<string, string> = {
  "First Four": "FF",
  "Round of 64": "R64",
  "Round of 32": "R32",
  "Sweet 16": "S16",
  "Elite Eight": "E8",
  "Final Four": "F4",
  Championship: "NC",
};

export const REGIONS = ["East", "West", "South", "Midwest"] as const;

export const TOURNAMENT_DATES_2026 = {
  selection_sunday: "2026-03-15",
  first_four: { start: "2026-03-17", end: "2026-03-18" },
  round_of_64: { start: "2026-03-19", end: "2026-03-20" },
  round_of_32: { start: "2026-03-21", end: "2026-03-22" },
  sweet_16: { start: "2026-03-26", end: "2026-03-27" },
  elite_eight: { start: "2026-03-28", end: "2026-03-29" },
  final_four: "2026-04-04",
  championship: "2026-04-06",
};

export const TOURNAMENT_TYPE_CONFIG = {
  mens: {
    label: "Men's Tournament",
    shortLabel: "Men's",
    emoji: "🏀",
    path: "/march-madness/mens",
    apiType: "mens" as const,
  },
  womens: {
    label: "Women's Tournament",
    shortLabel: "Women's",
    emoji: "🏀",
    path: "/march-madness/womens",
    apiType: "womens" as const,
  },
};

/** Get a human-readable countdown string from now to a target date */
export function getCountdown(targetDate: string): string {
  const target = new Date(targetDate);
  const now = new Date();
  const diff = target.getTime() - now.getTime();

  if (diff <= 0) return "Now";

  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));

  if (days > 0) return `${days}d ${hours}h`;
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  return `${hours}h ${minutes}m`;
}

/** Get the upset rarity description for UI badges */
export function getUpsetRarityLabel(seedWinner: number, seedLoser: number): string {
  const diff = seedWinner - seedLoser;
  if (diff >= 12) return "Historic";
  if (diff >= 8) return "Massive";
  if (diff >= 5) return "Major";
  if (diff >= 3) return "Notable";
  return "Upset";
}

/** Color for seed badges based on seed number */
export function getSeedColor(seed: number): string {
  if (seed <= 4) return "#8B4513";  // Dark wood
  if (seed <= 8) return "#A0522D";  // Sienna
  if (seed <= 12) return "#CD853F"; // Peru
  return "#D2691E";                 // Chocolate
}
