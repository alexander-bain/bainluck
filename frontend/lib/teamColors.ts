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
