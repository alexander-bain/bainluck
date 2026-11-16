/**
 * Team Color Theming Utility
 *
 * Applies team colors as CSS custom properties on container elements.
 * Child components automatically pick up --team-home-primary etc.
 *
 * Usage:
 *   <div style={teamColorStyle(homeTeam?.primary_color, awayTeam?.primary_color)}>
 *     {children}  ← will inherit team color CSS vars
 *   </div>
 */

import type { CSSProperties } from "react";

/**
 * Convert a hex color string to space-separated RGB values
 * for use in CSS custom properties (Tailwind-compatible).
 *
 * "#22C55E" → "34 197 94"
 * "22C55E"  → "34 197 94"
 * null      → undefined (use CSS fallback)
 */
export function hexToRgb(hex: string | null | undefined): string | undefined {
  if (!hex) return undefined;
  const clean = hex.replace(/^#/, "");
  if (clean.length !== 6) return undefined;
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  if (isNaN(r) || isNaN(g) || isNaN(b)) return undefined;
  return `${r} ${g} ${b}`;
}

/**
 * Returns a style object that sets team color CSS variables
 * on the element. Pass hex colors from the Team model
 * (team.primary_color, team.secondary_color).
 *
 * Ruling 197: when both teams carry visible colours in the same hue family (or
 * near-identical), the away team's `--team-away-primary` switches to its own
 * `secondary_color` (if readable and outside the home hue family) or slate grey
 * (`SLATE_TEAM_FALLBACK`).
 *
 * Missing colors fall through to the --team-home-primary etc.
 * defaults defined in design-tokens.css (gray).
 */
export function teamColorStyle(
  homeColor?: string | null,
  awayColor?: string | null,
  homeSecondary?: string | null,
  awaySecondary?: string | null
): CSSProperties {
  const style: Record<string, string> = {};
  const resolved = resolveMatchupTeamColors({
    homePrimary: homeColor,
    awayPrimary: awayColor,
    homeSecondary,
    awaySecondary,
  });

  const homeRgb = hexToRgb(resolved.home ?? homeColor);
  if (homeRgb) style["--team-home-primary"] = homeRgb;

  const awayRgb = hexToRgb(resolved.away ?? awayColor);
  if (awayRgb) style["--team-away-primary"] = awayRgb;

  const homeSecRgb = hexToRgb(homeSecondary);
  if (homeSecRgb) style["--team-home-secondary"] = homeSecRgb;

  const awaySecRgb = hexToRgb(awaySecondary);
  if (awaySecRgb) style["--team-away-secondary"] = awaySecRgb;

  return style as CSSProperties;
}

/**
 * Returns the hex color string with a # prefix.
 * Handles both "#FF0000" and "FF0000" inputs.
 */
export function ensureHash(color: string | null | undefined): string {
  if (!color) return "#6b7280"; // gray-500 fallback
  return color.startsWith("#") ? color : `#${color}`;
}

/**
 * #5165 — A BRAND COLOUR IS A FILL. IT IS NOT A TEXT COLOUR.
 *
 * `GamePlayCard` painted the score and the win probability in the team's own
 * `primary_color` with no floor, and the site is light-mode only with
 * `--surface-card: #FFFFFF`. Vancouver Whitecaps' stored primary is `#ffffff`,
 * so on `/events/15298474` a 3–0 win rendered as `- 0` and the winner's `100%`
 * was simply not there: white text on a white card.
 *
 * THE DEFECT IS INVISIBLE TO ALMOST EVERY TEST WE WRITE. Every character was in
 * the DOM, correct and in the right order. `toHaveTextContent("3")` passes, an
 * accessibility snapshot of text content passes, and the numbers are readable to
 * a screen reader. Only the pixels are wrong. That is why a guard for this class
 * has to assert the RESOLVED COLOUR, never the text.
 *
 * WHY A STANDARD RATHER THAN A TUNED CUTOFF. Measured over production `teams`
 * (1,452 rows carrying a colour, 644 distinct, untruncated): the contrast
 * distribution has no natural gap. It runs 1.00:1 (`#ffffff`, 26 teams) through
 * the yellows and golds (`#ffff00` 1.07, `#FACF08` 1.50, `#fdb927` 1.73) into the
 * pale blues and tans with nothing to cut on. Any hand-picked number would be a
 * number someone picked. So this uses WCAG's floor for UI text instead, and the
 * cost of each alternative was measured rather than guessed:
 *
 *     floor    teams recoloured    share
 *     1.5:1                  39     2.7%   (only the literally invisible)
 *     2.0:1                  83     5.7%
 *     3.0:1                 146    10.1%   ← chosen (WCAG UI/large-text minimum)
 *     4.5:1                 240    16.5%   (WCAG AA for small text)
 *
 * A recoloured team is not a degraded rendering: it falls back to
 * `--text-secondary`, which is exactly what a team with NO stored colour already
 * gets on the same card, so the result is the ordinary appearance rather than a
 * new one. Raising this to AA is a design decision with a measured price and one
 * line of code; it is deliberately not taken inside a bug fix.
 */
export const MIN_TEXT_CONTRAST_VS_SURFACE = 3;

/** WCAG relative luminance of a hex colour, or null when it cannot be parsed. */
export function relativeLuminance(hex: string | null | undefined): number | null {
  const rgb = hexToRgb(hex);
  if (!rgb) return null;
  const channel = (v: number) => {
    const c = v / 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  const [r, g, b] = rgb.split(" ").map(Number);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/**
 * The WCAG contrast ratio of a hex colour against the card surface
 * (`--surface-card`, `#FFFFFF` — the site is light-mode only), or null when the
 * colour cannot be parsed. 1 means identical to the surface: invisible.
 */
export function contrastVsCardSurface(hex: string | null | undefined): number | null {
  const l = relativeLuminance(hex);
  return l === null ? null : 1.05 / (l + 0.05);
}

/**
 * A team colour that is safe to render TEXT in, or the fallback.
 *
 * Returns `undefined` for an absent or unparseable colour so the caller's
 * existing `|| "var(--text-secondary)"` keeps its current meaning — this is a
 * floor added under existing behaviour, not a replacement for it.
 */
export function teamTextColor(hex: string | null | undefined): string | undefined {
  if (!hex) return undefined;
  const ratio = contrastVsCardSurface(hex);
  if (ratio === null) return undefined;
  return ratio >= MIN_TEXT_CONTRAST_VS_SURFACE ? hex : undefined;
}

/**
 * Returns a CSS rgba() string from a hex color with opacity.
 * Useful for team-colored backgrounds, borders, and shadows.
 *
 * teamColorWithOpacity("#22C55E", 0.15) → "rgba(34, 197, 94, 0.15)"
 */
export function teamColorWithOpacity(
  hex: string | null | undefined,
  opacity: number
): string {
  const rgb = hexToRgb(hex);
  if (!rgb) return `rgba(107, 114, 128, ${opacity})`; // gray-500 fallback
  const [r, g, b] = rgb.split(" ");
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

/**
 * Ruling 197 — slate grey fallback (`slate-500`, 4.76:1 vs `#FFFFFF`), matching
 * iOS `ProbabilityBarPalette.awayDefault` (`#64748B`).
 */
export const SLATE_TEAM_FALLBACK = "#64748B";

export type HueFamily =
  | "red"
  | "orange"
  | "yellow"
  | "green"
  | "teal"
  | "blue"
  | "purple"
  | "magenta";

function parseRgbTuple(hex: string | null | undefined): [number, number, number] | null {
  const rgb = hexToRgb(hex);
  if (!rgb) return null;
  const parts = rgb.split(" ").map(Number);
  if (parts.length !== 3 || parts.some((n) => !Number.isFinite(n))) return null;
  return [parts[0], parts[1], parts[2]];
}

function normalizeValidHex(hex: string | null | undefined): string | null {
  if (!hex || !parseRgbTuple(hex)) return null;
  const raw = hex.trim();
  return raw.startsWith("#") ? raw : `#${raw}`;
}

function rawRedmeanDistance(
  a: [number, number, number],
  b: [number, number, number]
): number {
  const rbar = (a[0] + b[0]) / 2;
  const dr = a[0] - b[0];
  const dg = a[1] - b[1];
  const db = a[2] - b[2];
  return Math.sqrt(
    (2 + rbar / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rbar) / 256) * db * db
  );
}

/**
 * Ruling 197 — chromatic hue family of a hex colour, or `null` when absent,
 * unparseable, or neutral/achromatic (`lightness < 6%`, `lightness > 94%`, or
 * `saturation < 22%`, covering blacks, whites, silvers, and slate greys such as
 * `#374151`, `#64748B`, and `#6B7280`).
 */
export function colorHueFamily(hex: string | null | undefined): HueFamily | null {
  const tuple = parseRgbTuple(hex);
  if (!tuple) return null;
  const r = tuple[0] / 255;
  const g = tuple[1] / 255;
  const b = tuple[2] / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  if (d === 0 || l < 0.06 || l > 0.94) return null;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  if (s < 0.22) return null;

  let h = 0;
  if (max === r) {
    h = ((g - b) / d + (g < b ? 6 : 0)) * 60;
  } else if (max === g) {
    h = ((b - r) / d + 2) * 60;
  } else {
    h = ((r - g) / d + 4) * 60;
  }

  if (h >= 335 || h < 15) return "red";
  if (h < 38) return "orange";
  if (h < 70) return "yellow";
  if (h < 168) return "green";
  if (h < 196) return "teal";
  if (h < 245) return "blue";
  if (h < 305) return "purple";
  return "magenta";
}

/**
 * Ruling 197 — true when two colours both belong to the same chromatic hue
 * family (for example Kansas `#0051ba` and Duke `#00539b`, or Gonzaga `#041e42`
 * and Duke `#00539b`, all in `"blue"`). Neutral greys/blacks return `false` and
 * continue to use the near-identical distance check.
 */
export function sameColorFamily(
  a: string | null | undefined,
  b: string | null | undefined
): boolean {
  const fa = colorHueFamily(a);
  const fb = colorHueFamily(b);
  return fa !== null && fa === fb;
}

export interface MatchupTeamColorInput {
  homePrimary?: string | null;
  awayPrimary?: string | null;
  homeSecondary?: string | null;
  awaySecondary?: string | null;
}

export interface ResolvedMatchupTeamColors {
  home: string | null;
  away: string | null;
  awaySwitched: boolean;
}

const MIN_VISIBLE_SURFACE_CONTRAST = 1.5;
const MIN_NEAR_IDENTICAL_DISTANCE = 80;
const SLATE_COLLISION_FALLBACK = "#111827";

/**
 * Ruling 197 (Alex, #12538): when both teams' main colours are near-identical
 * or share a chromatic hue family, the home team keeps its main colour and the
 * away team switches to its own `secondary_color` — provided we hold one that
 * clears the card text contrast floor (`3:1`), is not near-identical to home,
 * and is not in home's hue family. Otherwise the away team switches to slate
 * grey (`#64748B`, or `#111827` if home itself sits near `#64748B`).
 */
export function resolveMatchupTeamColors({
  homePrimary,
  awayPrimary,
  awaySecondary,
}: MatchupTeamColorInput): ResolvedMatchupTeamColors {
  const normHome = normalizeValidHex(homePrimary);
  const normAway = normalizeValidHex(awayPrimary);
  if (!normHome || !normAway) {
    return { home: normHome, away: normAway, awaySwitched: false };
  }

  const homeContrast = contrastVsCardSurface(normHome);
  const awayContrast = contrastVsCardSurface(normAway);
  if (
    homeContrast === null ||
    awayContrast === null ||
    homeContrast < MIN_VISIBLE_SURFACE_CONTRAST ||
    awayContrast < MIN_VISIBLE_SURFACE_CONTRAST
  ) {
    return { home: normHome, away: normAway, awaySwitched: false };
  }

  const homeRgb = parseRgbTuple(normHome)!;
  const awayRgb = parseRgbTuple(normAway)!;
  const nearIdentical =
    rawRedmeanDistance(awayRgb, homeRgb) < MIN_NEAR_IDENTICAL_DISTANCE;
  const sharedHue = sameColorFamily(normAway, normHome);

  if (!nearIdentical && !sharedHue) {
    return { home: normHome, away: normAway, awaySwitched: false };
  }

  const normAwaySec = normalizeValidHex(awaySecondary);
  if (normAwaySec && teamTextColor(normAwaySec)) {
    const secRgb = parseRgbTuple(normAwaySec)!;
    const secTooClose =
      rawRedmeanDistance(secRgb, homeRgb) < MIN_NEAR_IDENTICAL_DISTANCE;
    if (!secTooClose && !sameColorFamily(normAwaySec, normHome)) {
      return { home: normHome, away: normAwaySec, awaySwitched: true };
    }
  }

  const slateRgb = parseRgbTuple(SLATE_TEAM_FALLBACK)!;
  const fallbackAway =
    rawRedmeanDistance(slateRgb, homeRgb) >= MIN_NEAR_IDENTICAL_DISTANCE
      ? SLATE_TEAM_FALLBACK
      : SLATE_COLLISION_FALLBACK;
  return { home: normHome, away: fallbackAway, awaySwitched: true };
}
