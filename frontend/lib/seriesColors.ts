/**
 * seriesColors — the single per-series (per-outcome/competitor) palette registry
 * (L2-157, census class E — the index/outcome-palette half; the source-color half
 * lives in sourceColors.ts / L2-155).
 *
 * These color CHART SERIES BY INDEX — the Nth competitor line in a field/race
 * chart, its legend swatch, and its leaderboard dot — NOT data sources. Before
 * this file, FIVE near-identical index palettes each hardcoded their own hexes
 * and drifted: `DEFAULT_COLORS`/`GOLD_COLORS`/`GREEN_COLORS` in FuturesChart and
 * two identical copies of `EVOLUTION_COLORS` (EvolutionView + EvolutionLeaderboard).
 * The generic index palette even disagreed with itself across surfaces (the field
 * kernel drew a blue-led rainbow while the evolution/race chart drew a crimson-led
 * one for the same "Nth competitor" role). This registry replaces all of them so
 * a line and its sidebar dot always match, and every field chart inherits one map.
 *
 * Canonicalization rule (NOT taste — same discipline as L2-155): where hexes
 * conflicted for the same role, the value used on the FLAGSHIP surface wins. The
 * flagship series surface is the shared FuturesChart field kernel (L2-149) — it
 * renders the event-page hero charts (RaceToTitle / WinnerEvolution / SettledPath)
 * and the most distinct surfaces — so its `DEFAULT_COLORS` become the canonical
 * SERIES_COLORS. The evolution/race chart adopts them (dropping its bespoke
 * crimson-led duplicate). No new colors were invented: SERIES_COLORS extends the
 * flagship's 8 with two hues already present in the old EVOLUTION palette
 * (`#92400e` brown, `#065f46` dark green) so a >8-competitor field keeps distinct
 * lines. GOLD/GREEN are distinct leader THEMES (no conflict) and keep their hexes.
 */

/**
 * Canonical index palette for competitor/outcome series (white-bg optimized).
 * Indices 0–7 are the flagship FuturesChart palette (unchanged); indices 8–9 add
 * headroom for many-competitor fields (e.g. a 10-golfer evolution board) using
 * hues that already existed in the old EVOLUTION_COLORS palette.
 */
export const SERIES_COLORS = [
  "#2563eb", // blue
  "#dc2626", // red
  "#16a34a", // green
  "#9333ea", // purple
  "#ea580c", // orange
  "#0891b2", // cyan
  "#be185d", // pink
  "#4f46e5", // indigo
  "#92400e", // brown  (headroom — reused from old EVOLUTION palette)
  "#065f46", // dark green (headroom — reused from old EVOLUTION palette)
];

/** Gold-leader theme: leader gold + descending grays. Used for a single-leader
 *  field where the frontrunner should read as "gold". Distinct role — kept as-is. */
export const SERIES_COLORS_GOLD = [
  "#D4AF37", // gold (leader)
  "#B8860B", // dark goldenrod
  "#6b7280", // gray-500
  "#9ca3af", // gray-400
  "#d1d5db", // gray-300
  "#6b7280",
  "#9ca3af",
  "#d1d5db",
];

/** Augusta-green leader theme (golf majors): Masters green + descending grays.
 *  Distinct role — kept as-is. */
export const SERIES_COLORS_GREEN = [
  "#006747", // Augusta green (leader)
  "#2d8659", // lighter green
  "#6b7280", // gray-500
  "#9ca3af", // gray-400
  "#d1d5db", // gray-300
  "#6b7280",
  "#9ca3af",
  "#d1d5db",
];

/** Eliminated-outcome line/dot color — a muted grey so a knocked-out contender
 *  stays visible for context without competing with the live field (L2-149). */
export const ELIMINATED_SERIES_COLOR = "#b5b9c3";

/** Combined-probability line color — the summed line reads as a dark neutral so
 *  it never masquerades as one of the contenders (L2-149). */
export const COMBINED_SERIES_COLOR = "#111827";
