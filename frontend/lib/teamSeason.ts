/**
 * Pure helpers for the team page's season-context chips (Queue L2-169).
 *
 * Queue #242 Item 1 added season truth to the team payload: a top-level
 * `SeasonDescriptor` ({league, season, phase, label}) plus a per-entry `season`
 * on each `championship_path` step. L2-164 had already built the season-chip UI
 * slot on the Division Race (fed by the grid endpoint's season); these helpers
 * bind the *team-payload* season fields to the Season Journey header and the
 * Championship Path chip, deriving one honest string or null (never a guess).
 *
 * Side-effect-free + SSR-safe so they are unit-testable with fixtures — the team
 * endpoint 500s under #1197, so the contract, not live data, is the source here.
 */
import type { ChampionshipPathEntry, SeasonDescriptor } from "./api";

/** Collapse blank/whitespace to null so a chip never renders an empty pill. */
function clean(s: string | null | undefined): string | null {
  return typeof s === "string" && s.trim() ? s.trim() : null;
}

/**
 * The season string for a section chip from the page's season descriptor
 * (e.g. "2026-27"), or null when the league carries no modeled season.
 */
export function seasonChipText(
  season: SeasonDescriptor | null | undefined,
): string | null {
  return clean(season?.season);
}

/**
 * The season a championship path describes. Each entry carries its own season
 * (a market's own season, falling back to the league's). We surface the single
 * common season when every present season agrees, otherwise null — mixed seasons
 * across the path would be a data artifact, and a chip must not assert one.
 */
export function pathSeason(
  entries: ChampionshipPathEntry[] | null | undefined,
): string | null {
  if (!entries || entries.length === 0) return null;
  const seasons = entries.map((e) => clean(e.season)).filter((s): s is string => s !== null);
  if (seasons.length === 0) return null;
  const first = seasons[0];
  return seasons.every((s) => s === first) ? first : null;
}

/**
 * The Season Journey chart header's range label. With a season it reads
 * "2026-27 · Opening day → today"; without one it degrades to the plain range.
 */
export function journeyRangeLabel(season: string | null | undefined): string {
  const s = clean(season);
  const range = "Opening day → today · fixed 0–100% scale (tap Zoom for detail)";
  return s ? `${s} · ${range}` : range;
}
