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

  const homeRgb = hexToRgb(homeColor);
  if (homeRgb) style["--team-home-primary"] = homeRgb;

  const awayRgb = hexToRgb(awayColor);
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
