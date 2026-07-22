/**
 * sourceColors — the single source-color registry (L2-155, census class E).
 *
 * ONE canonical color per win-probability data source, used everywhere a source
 * identity is drawn: chart strokes, legend swatches, dots, badges, and text.
 * "Same source, same color, everywhere" is design-system law (see CLAUDE.md —
 * tokens are MANDATORY), not a per-component taste call.
 *
 * Before this file, FIVE+ near-identical palettes and THREE config maps each
 * hardcoded their own hexes, and the SAME source disagreed across components
 * (kalshi was green in charts, indigo in the aggregation block, blue in
 * calibration, red in the admin coverage chart). This registry replaces all of
 * them so the redesign inherits one map instead of eight drifting ones.
 *
 * Canonicalization rule (NOT taste): where hexes conflicted, the value used on
 * the FLAGSHIP surface (OddsChart) wins; globals.css has no per-source tokens,
 * so no design token overrode it. Faint/fg variants are the natural Tailwind
 * 50/700 tints of each hue — no new colors were invented.
 */

export interface SourceColor {
  /** Canonical solid hex — chart strokes, legend swatches, dots, colored text. */
  hex: string;
  /** Faint background tint — badges, chips, the "faint sources" treatment. */
  faint: string;
  /** Readable foreground (text on white or on the faint tint). */
  fg: string;
  /** Default human display name (consumers may still override contextually). */
  label: string;
}

/**
 * Canonical registry, keyed by canonical source key. Aliases (betting,
 * fangraphs, datagolf_model, bainluck, display-name spellings) resolve through
 * getSourceColor().
 */
export const SOURCE_COLORS: Record<string, SourceColor> = {
  // Prediction markets.
  kalshi: { hex: "#22c55e", faint: "#F0FDF4", fg: "#15803D", label: "Kalshi" },
  polymarket: { hex: "#3b82f6", faint: "#EFF6FF", fg: "#1D4ED8", label: "Polymarket" },

  // Sportsbooks (The Odds API). "betting" is the same source under a different
  // key on the flagship chart. Dark, high-contrast slate — the prominent
  // primary line in sportsbooks-only mode (L2-131).
  odds_api: { hex: "#0f172a", faint: "#F1F5F9", fg: "#334155", label: "Sportsbooks" },
  // Market-type breakdowns of odds_api used on the calibration page.
  odds_api_spreads: { hex: "#0d9488", faint: "#F0FDFA", fg: "#0F766E", label: "Spreads (Odds API)" },
  odds_api_totals: { hex: "#059669", faint: "#ECFDF5", fg: "#047857", label: "Totals (Odds API)" },
  odds_api_bookmaker: { hex: "#15803d", faint: "#F0FDF4", fg: "#166534", label: "Per-Bookmaker (Odds API)" },

  // Models / other sources.
  espn: { hex: "#f97316", faint: "#FFF7ED", fg: "#C2410C", label: "ESPN" },
  stat_model: { hex: "#8b5cf6", faint: "#F5F3FF", fg: "#6D28D9", label: "Bain Luck Model" },
  mlb: { hex: "#06b6d4", faint: "#ECFEFF", fg: "#0E7490", label: "MLB Model" },
  datagolf: { hex: "#f59e0b", faint: "#FFFBEB", fg: "#B45309", label: "DataGolf" },

  // The blend — the one aggregated Bain Luck line.
  blend: { hex: "#059669", faint: "#ECFDF5", fg: "#047857", label: "Bain Luck" },
};

/** Neutral fallback for an unknown source. */
export const DEFAULT_SOURCE_COLOR: SourceColor = {
  hex: "#6b7280",
  faint: "#F3F4F6",
  fg: "#4B5563",
  label: "Source",
};

/**
 * Alias table: maps alternate keys and display-name spellings to a canonical
 * registry key. Lookups are case-insensitive (see getSourceColor).
 */
const SOURCE_ALIASES: Record<string, string> = {
  betting: "odds_api",
  "odds api": "odds_api",
  sportsbooks: "odds_api",
  fangraphs: "mlb",
  "mlb model": "mlb",
  datagolf_model: "datagolf",
  "dg model": "datagolf",
  bainluck: "blend",
  "bain luck": "blend",
  "bain luck model": "stat_model",
  "espn wp": "espn",
};

/** Resolve any source key/alias/display-name to its canonical registry key. */
export function canonicalSourceKey(source: string): string {
  if (!source) return source;
  const raw = source.trim();
  if (SOURCE_COLORS[raw]) return raw;
  const lower = raw.toLowerCase();
  if (SOURCE_COLORS[lower]) return lower;
  if (SOURCE_ALIASES[lower]) return SOURCE_ALIASES[lower];
  return lower;
}

/**
 * The canonical color entry for a source (handles aliases + case). Returns the
 * neutral default for unknown sources so callers never render an undefined.
 */
export function getSourceColor(source: string): SourceColor {
  return SOURCE_COLORS[canonicalSourceKey(source)] ?? DEFAULT_SOURCE_COLOR;
}

/** Convenience: just the canonical solid hex for a source. */
export function sourceHex(source: string): string {
  return getSourceColor(source).hex;
}
