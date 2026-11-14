/**
 * Feature flag and reason-line hygiene for the unified 183-A web game card (#12616).
 *
 * Strictly switched OFF by default (`NEXT_PUBLIC_GAME_CARD_183A !== "true"`).
 * Turning this flag on is reader-visible and requires Fable's explicit sign-off.
 */

const FILLER_REASON_PATTERNS: RegExp[] = [
  /^(?:trending|popular|featured|upcoming|live|recent|top)\s+(?:game|match|matchup|fixture|event)\.?$/i,
  /^see\s+(?:full|all|more)\b/i,
  /^follow\s+(?:live|the\s+action)\b/i,
  /^tap\s+to\s+view\b/i,
  /^(?:game|match)\s+of\s+the\s+(?:day|week)\.?$/i,
];

const FORBIDDEN_REASON_WORDS = /\b(?:questions?|stale|venues?|kalshi|polymarket|opened)\b/i;

export function isWebGameCard183AEnabled(override?: boolean): boolean {
  if (typeof override === "boolean") {
    return override;
  }
  return process.env.NEXT_PUBLIC_GAME_CARD_183A === "true";
}

/**
 * Ruling 190-C ("If a line reads like filler, leave it off"):
 * Only admit a Discover single-game reason line when it carries genuine
 * stakes (before), a wild swing (during), or what the result changed (after),
 * rather than echoing team names or generic filler.
 */
export function cleanDiscoverGameReason(
  rawReason: string | null | undefined,
  homeTeam: string,
  awayTeam: string,
): string | null {
  if (typeof rawReason !== "string") return null;
  const trimmed = rawReason.replace(/\s+/g, " ").trim();
  if (trimmed.length < 18) return null;
  if (FORBIDDEN_REASON_WORDS.test(trimmed)) return null;
  if (FILLER_REASON_PATTERNS.some((re) => re.test(trimmed))) return null;

  const lower = trimmed.toLowerCase();
  const bareAt = `${awayTeam} at ${homeTeam}`.toLowerCase();
  const bareVs = `${awayTeam} vs ${homeTeam}`.toLowerCase();
  const bareVsDot = `${awayTeam} vs. ${homeTeam}`.toLowerCase();
  if (lower === bareAt || lower === bareVs || lower === bareVsDot) {
    return null;
  }
  return trimmed;
}
