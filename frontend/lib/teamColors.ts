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
 * Darkens a team hex colour in RGB space when its WCAG contrast against the
 * `#FFFFFF` card surface falls below `minContrast` (default `4.5`, WCAG AA for
 * text), preserving hue/chroma for light golds, yellows, and pale blues (e.g.
 * New Orleans Saints `#D3BC8D` `1.91:1` -> `#786B50` `4.56:1`). Pure/near-white
 * team colours fall back to `#475569`.
 */
export function darkenTeamColorForCardText(
  hex: string | null | undefined,
  minContrast: number = 4.5,
): string {
  if (!hex) return "#475569";
  const rgbStr = hexToRgb(hex);
  if (!rgbStr) return "#475569";
  const [r, g, b] = rgbStr.split(" ").map(Number);
  const currentRatio = contrastVsCardSurface(hex);
  if (currentRatio !== null && currentRatio >= minContrast) {
    return ensureHash(hex);
  }
  const maxC = Math.max(r, g, b);
  const minC = Math.min(r, g, b);
  if (maxC >= 245 && maxC - minC <= 12) {
    return "#475569";
  }
  const targetRatio = minContrast + 0.05;
  let lo = 0;
  let hi = 1;
  for (let i = 0; i < 20; i++) {
    const mid = (lo + hi) / 2;
    const candHex =
      "#" +
      [Math.round(r * mid), Math.round(g * mid), Math.round(b * mid)]
        .map((v) => Math.max(0, Math.min(255, v)).toString(16).padStart(2, "0"))
        .join("");
    const ratio = contrastVsCardSurface(candHex) ?? 1;
    if (ratio >= targetRatio) {
      lo = mid;
    } else {
      hi = mid;
    }
  }
  return (
    "#" +
    [Math.round(r * lo), Math.round(g * lo), Math.round(b * lo)]
      .map((v) => Math.max(0, Math.min(255, v)).toString(16).padStart(2, "0"))
      .join("")
  );
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

/**
 * Canonical brand primary & secondary colours for major North American & European
 * clubs so surfaces whose brief omits opponent `TeamData` (such as `/api/teams/{slug}`
 * before the championship grid resolves) still render both teams' real colours with
 * Ruling 197 collision protection.
 */
const KNOWN_TEAM_COLORS: Record<string, { primary: string; secondary?: string }> = {
  // NFL (32)
  "arizona cardinals": { primary: "#97233F", secondary: "#000000" },
  "atlanta falcons": { primary: "#A71930", secondary: "#000000" },
  "baltimore ravens": { primary: "#241773", secondary: "#9E7C0C" },
  "buffalo bills": { primary: "#00338D", secondary: "#C60C30" },
  "carolina panthers": { primary: "#0085CA", secondary: "#101820" },
  "chicago bears": { primary: "#0B162A", secondary: "#C83803" },
  "cincinnati bengals": { primary: "#FB4F14", secondary: "#000000" },
  "cleveland browns": { primary: "#311D00", secondary: "#FF3C00" },
  "dallas cowboys": { primary: "#003594", secondary: "#869397" },
  "denver broncos": { primary: "#FB4F14", secondary: "#002244" },
  "detroit lions": { primary: "#0076B6", secondary: "#B0B7BC" },
  "green bay packers": { primary: "#203731", secondary: "#FFB612" },
  "houston texans": { primary: "#03202F", secondary: "#A71930" },
  "indianapolis colts": { primary: "#002C5F", secondary: "#A2AAAD" },
  "jacksonville jaguars": { primary: "#006778", secondary: "#9F792C" },
  "kansas city chiefs": { primary: "#E31837", secondary: "#FFB81C" },
  "las vegas raiders": { primary: "#000000", secondary: "#A5ACAF" },
  "los angeles chargers": { primary: "#0080C6", secondary: "#FFC20E" },
  "los angeles rams": { primary: "#003594", secondary: "#FFA300" },
  "miami dolphins": { primary: "#008E97", secondary: "#FC4C02" },
  "minnesota vikings": { primary: "#4F2683", secondary: "#FFC62F" },
  "new england patriots": { primary: "#002244", secondary: "#C60C30" },
  "new orleans saints": { primary: "#D3BC8D", secondary: "#101820" },
  "new york giants": { primary: "#0B2265", secondary: "#A71930" },
  "new york jets": { primary: "#125740", secondary: "#000000" },
  "philadelphia eagles": { primary: "#004C54", secondary: "#A5ACAF" },
  "pittsburgh steelers": { primary: "#101820", secondary: "#FFB612" },
  "san francisco 49ers": { primary: "#AA0000", secondary: "#B3995D" },
  "seattle seahawks": { primary: "#002244", secondary: "#69BE28" },
  "tampa bay buccaneers": { primary: "#D50A0A", secondary: "#34302B" },
  "tennessee titans": { primary: "#0C2340", secondary: "#C8102E" },
  "washington commanders": { primary: "#5A1414", secondary: "#FFB612" },
  // NBA (30)
  "atlanta hawks": { primary: "#E03A3E", secondary: "#C1D32F" },
  "boston celtics": { primary: "#007A33", secondary: "#BA9653" },
  "brooklyn nets": { primary: "#000000", secondary: "#777D84" },
  "charlotte hornets": { primary: "#1D1160", secondary: "#00788C" },
  "chicago bulls": { primary: "#CE1141", secondary: "#000000" },
  "cleveland cavaliers": { primary: "#860038", secondary: "#041E42" },
  "dallas mavericks": { primary: "#00538C", secondary: "#002B5E" },
  "denver nuggets": { primary: "#0E2240", secondary: "#FEC524" },
  "detroit pistons": { primary: "#C8102E", secondary: "#1D42BA" },
  "golden state warriors": { primary: "#1D428A", secondary: "#FFC72C" },
  "houston rockets": { primary: "#CE1141", secondary: "#000000" },
  "indiana pacers": { primary: "#002D62", secondary: "#FDBB30" },
  "la clippers": { primary: "#C8102E", secondary: "#1D428A" },
  "los angeles clippers": { primary: "#C8102E", secondary: "#1D428A" },
  "los angeles lakers": { primary: "#552583", secondary: "#FDB927" },
  "memphis grizzlies": { primary: "#5D76A9", secondary: "#12173F" },
  "miami heat": { primary: "#98002E", secondary: "#F9A01B" },
  "milwaukee bucks": { primary: "#00471B", secondary: "#EEE1C6" },
  "minnesota timberwolves": { primary: "#0C2340", secondary: "#236192" },
  "new orleans pelicans": { primary: "#0C2340", secondary: "#C8102E" },
  "new york knicks": { primary: "#006BB6", secondary: "#F58426" },
  "oklahoma city thunder": { primary: "#007AC1", secondary: "#EF3B24" },
  "orlando magic": { primary: "#0077C0", secondary: "#C4CED4" },
  "philadelphia 76ers": { primary: "#006BB6", secondary: "#ED174C" },
  "phoenix suns": { primary: "#1D1160", secondary: "#E56020" },
  "portland trail blazers": { primary: "#E03A3E", secondary: "#000000" },
  "sacramento kings": { primary: "#5A2D81", secondary: "#63727A" },
  "san antonio spurs": { primary: "#000000", secondary: "#C4CED4" },
  "toronto raptors": { primary: "#CE1141", secondary: "#000000" },
  "utah jazz": { primary: "#002B5C", secondary: "#F9A01B" },
  "washington wizards": { primary: "#002B5C", secondary: "#E31837" },
  // NHL (32)
  "anaheim ducks": { primary: "#F47A38", secondary: "#B9975B" },
  "boston bruins": { primary: "#FFB81C", secondary: "#000000" },
  "buffalo sabres": { primary: "#003087", secondary: "#FFB81C" },
  "calgary flames": { primary: "#D2001C", secondary: "#FAAF19" },
  "carolina hurricanes": { primary: "#CC0000", secondary: "#000000" },
  "chicago blackhawks": { primary: "#CF0A2C", secondary: "#000000" },
  "colorado avalanche": { primary: "#6F263D", secondary: "#236192" },
  "columbus blue jackets": { primary: "#002654", secondary: "#CE1126" },
  "dallas stars": { primary: "#006847", secondary: "#8F8F8C" },
  "detroit red wings": { primary: "#CE1126", secondary: "#000000" },
  "edmonton oilers": { primary: "#041E42", secondary: "#FF4C00" },
  "florida panthers": { primary: "#C8102E", secondary: "#041E42" },
  "los angeles kings": { primary: "#111111", secondary: "#A2AAAD" },
  "minnesota wild": { primary: "#154734", secondary: "#A6192E" },
  "montreal canadiens": { primary: "#AF1E2D", secondary: "#192168" },
  "nashville predators": { primary: "#FFB81C", secondary: "#041E42" },
  "new jersey devils": { primary: "#CE1126", secondary: "#000000" },
  "new york islanders": { primary: "#00539B", secondary: "#F47D30" },
  "new york rangers": { primary: "#0038A8", secondary: "#CE1126" },
  "ottawa senators": { primary: "#C52032", secondary: "#000000" },
  "philadelphia flyers": { primary: "#F74902", secondary: "#000000" },
  "pittsburgh penguins": { primary: "#000000", secondary: "#FCB514" },
  "san jose sharks": { primary: "#006D75", secondary: "#EA7200" },
  "seattle kraken": { primary: "#001628", secondary: "#355464" },
  "st. louis blues": { primary: "#002F87", secondary: "#FCB514" },
  "tampa bay lightning": { primary: "#002868", secondary: "#000000" },
  "toronto maple leafs": { primary: "#00205B", secondary: "#64748B" },
  "utah hockey club": { primary: "#010101", secondary: "#6CACE4" },
  "vancouver canucks": { primary: "#00205B", secondary: "#00843D" },
  "vegas golden knights": { primary: "#B4975A", secondary: "#333F42" },
  "washington capitals": { primary: "#C8102E", secondary: "#041E42" },
  "winnipeg jets": { primary: "#041E42", secondary: "#AC162C" },
  // MLB (30)
  "arizona diamondbacks": { primary: "#A71930", secondary: "#E3D4AD" },
  "atlanta braves": { primary: "#CE1141", secondary: "#13274F" },
  "baltimore orioles": { primary: "#DF4601", secondary: "#000000" },
  "boston red sox": { primary: "#BD3039", secondary: "#0C2340" },
  "chicago cubs": { primary: "#0E3386", secondary: "#CC3433" },
  "chicago white sox": { primary: "#27251F", secondary: "#C4CED4" },
  "cincinnati reds": { primary: "#C6011F", secondary: "#000000" },
  "cleveland guardians": { primary: "#00385D", secondary: "#E50022" },
  "colorado rockies": { primary: "#333366", secondary: "#C4CED4" },
  "detroit tigers": { primary: "#0C2340", secondary: "#FA4616" },
  "houston astros": { primary: "#002D62", secondary: "#EB6E1F" },
  "kansas city royals": { primary: "#004687", secondary: "#BD9B60" },
  "los angeles angels": { primary: "#BA0021", secondary: "#003263" },
  "los angeles dodgers": { primary: "#005A9C", secondary: "#EF3E42" },
  "miami marlins": { primary: "#00A3E0", secondary: "#EF3340" },
  "milwaukee brewers": { primary: "#12284B", secondary: "#FFC52F" },
  "minnesota twins": { primary: "#002B5C", secondary: "#D31145" },
  "new york mets": { primary: "#002D72", secondary: "#FF5910" },
  "new york yankees": { primary: "#003087", secondary: "#E4002C" },
  "oakland athletics": { primary: "#003831", secondary: "#EFB21E" },
  "athletics": { primary: "#003831", secondary: "#EFB21E" },
  "philadelphia phillies": { primary: "#E81828", secondary: "#002D72" },
  "pittsburgh pirates": { primary: "#27251F", secondary: "#FDB827" },
  "san diego padres": { primary: "#2F241D", secondary: "#FFC425" },
  "san francisco giants": { primary: "#FD5A1E", secondary: "#27251F" },
  "seattle mariners": { primary: "#0C2C56", secondary: "#005C5C" },
  "st. louis cardinals": { primary: "#C41E3A", secondary: "#0C2340" },
  "tampa bay rays": { primary: "#092C5C", secondary: "#8FBCE6" },
  "texas rangers": { primary: "#003278", secondary: "#C0111F" },
  "toronto blue jays": { primary: "#134A8E", secondary: "#E8291C" },
  "washington nationals": { primary: "#AB0003", secondary: "#14225A" },
  // Major European football & NCAA clubs
  "arsenal": { primary: "#EF0107", secondary: "#063672" },
  "aston villa": { primary: "#670E36", secondary: "#95BFE5" },
  "bournemouth": { primary: "#DA291C", secondary: "#64748B" },
  "afc bournemouth": { primary: "#DA291C", secondary: "#64748B" },
  "brentford": { primary: "#E30613", secondary: "#64748B" },
  "brighton": { primary: "#0057B8", secondary: "#FFCD00" },
  "brighton & hove albion": { primary: "#0057B8", secondary: "#FFCD00" },
  "chelsea": { primary: "#034694", secondary: "#DBA111" },
  "coventry city": { primary: "#87CCED", secondary: "#1E293B" },
  "crystal palace": { primary: "#1B458F", secondary: "#C4122E" },
  "everton": { primary: "#003399", secondary: "#64748B" },
  "fulham": { primary: "#FFFFFF", secondary: "#CC0000" },
  "ipswich town": { primary: "#3A64A3", secondary: "#DE2C37" },
  "leicester city": { primary: "#003090", secondary: "#FDBE11" },
  "liverpool": { primary: "#C8102E", secondary: "#00B2A9" },
  "manchester city": { primary: "#6CABDD", secondary: "#1C2C5B" },
  "manchester united": { primary: "#DA291C", secondary: "#000000" },
  "newcastle united": { primary: "#241F20", secondary: "#41B6E6" },
  "nottingham forest": { primary: "#DD0000", secondary: "#64748B" },
  "southampton": { primary: "#D71920", secondary: "#64748B" },
  "tottenham hotspur": { primary: "#132257", secondary: "#64748B" },
  "west ham united": { primary: "#7A263A", secondary: "#1BB1E7" },
  "wolverhampton wanderers": { primary: "#FDB913", secondary: "#231F20" },
  "wolves": { primary: "#FDB913", secondary: "#231F20" },
  "real madrid": { primary: "#1E293B", secondary: "#FEBE10" },
  "barcelona": { primary: "#A50044", secondary: "#004D98" },
  "bayern munich": { primary: "#DC052D", secondary: "#0066B2" },
  "duke blue devils": { primary: "#00539B", secondary: "#012169" },
  "gonzaga bulldogs": { primary: "#041E42", secondary: "#C8102E" },
  "kansas jayhawks": { primary: "#0051BA", secondary: "#E8000D" },
  "alabama crimson tide": { primary: "#9E1B32", secondary: "#828A8F" },
  "usc trojans": { primary: "#990000", secondary: "#FFC72C" },
};

export function lookupTeamColors(
  teamName: string | null | undefined,
): { primary: string; secondary?: string } | null {
  if (!teamName) return null;
  const norm = teamName.trim().toLowerCase();
  return KNOWN_TEAM_COLORS[norm] ?? null;
}

/**
 * Ruling 197 — resolves an away club's second colour for same-family disambiguation:
 * prefers our curated `KNOWN_TEAM_COLORS` secondary when recorded (e.g. Crystal Palace
 * `#C4122E` Eagle Red over ESPN's generic `#000000`), and ignores generic `#000000`
 * wire placeholders on uncurated clubs so Ruling 197 falls back to slate (`#64748B`)
 * rather than painting an unverified black line.
 */
export function effectiveAwaySecondaryColor(
  awayTeamName: string | null | undefined,
  wireSecondary: string | null | undefined,
): string | undefined {
  const trimmedWire = wireSecondary?.trim();
  if (trimmedWire && trimmedWire.toLowerCase() !== "#000000") {
    return trimmedWire;
  }
  const known = lookupTeamColors(awayTeamName);
  if (known?.secondary && known.secondary.toLowerCase() !== "#000000") {
    return known.secondary;
  }
  return undefined;
}
