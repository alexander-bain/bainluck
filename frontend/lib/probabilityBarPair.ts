/**
 * The two segments of a game card's probability bar, decided TOGETHER.
 *
 * Why a pair and not two independent fallbacks (#2962):
 * `FeedCard` used to pick each segment on its own —
 *   away: `awayColor || "var(--color-text-muted)"`
 *   home: `homeColor || "var(--color-accent-brand)"`
 * Neither custom property has ever been defined (the real tokens are
 * `--text-muted` and `--accent-brand`, without the `color-` prefix, and we are
 * on Tailwind v3, which does not emit `--color-*` from the theme). A
 * `background-color: var(--undefined)` is invalid at computed-value time, so
 * the declaration is dropped and the segment paints nothing. Measured on
 * production at 390px on 2026-09-04: 7 of 7 bars, 14 of 14 segments, computed
 * to `rgba(0, 0, 0, 0)`. The fallback did not fall back — it deleted the bar.
 *
 * The obvious repair is to adopt the sibling convention: `ProbabilityBar.tsx`
 * and `EventCard.tsx` both read `rgb(var(--team-home-primary))`, which IS
 * defined (`design-tokens.css:43,45`). That is the wrong fix here, and the
 * reason is measurable: both of those variables default to the SAME gray-500,
 * so a card with no team colours would render two identical grey halves — a
 * flat block instead of a split. That is precisely the native sibling defect
 * (#2902), and because `/api/feed` and `/api/events` serialize
 * `home_team_data` on 0 of 37 and 0 of 86 rows respectively, it would land on
 * essentially every game card rather than on an edge case. Adopting the
 * sibling convention verbatim is counter-case (B) in this ship's guard.
 *
 * So the contract is a PAIR, mirroring the native lane's
 * `ProbabilityBarPalette.pair(awayHex:homeHex:)` (native/005, #2902):
 *
 *   1. Both segments always carry a real colour. Never a variable, never
 *      transparent, never an empty string.
 *   2. The two segments are never indistinguishable from each other.
 *   3. Neither segment is indistinguishable from the card it sits on.
 *
 * Clause 3 is an addition beyond what #2962 asks for, and it is not
 * hypothetical: 21 distinct team colours held by 60 teams — `#ffffff` alone is
 * 26 of them — composite to less than 1.5:1 against the white card, i.e. a
 * "real" team colour can reproduce the exact symptom this module exists to
 * fix. The site is light mode only, so the surface is a constant.
 *
 * Every threshold below was chosen by replaying the real palette (all 644
 * distinct `teams.primary_color` values, 1,445 teams), not by taste. See the
 * constants for the measurement that picked each one.
 */

import { hexToRgb } from "./teamColors";

/** The card the bar sits on. Light mode only — `--surface-card` in globals.css. */
export const CARD_SURFACE = "#FFFFFF";

/**
 * One opacity for BOTH segments.
 *
 * The old code used `awayColor ? 0.7 : 0.3` and `homeColor ? 0.7 : 0.5`, so the
 * two fallback halves were dimmed by different amounts. That is a second defect
 * in the same block and it is not cosmetic: at 0.3 the grey default composites
 * to 1.28:1 against the card, which is below the visibility floor below — so
 * even with the variable names fixed, the away half would have been barely
 * there. It also makes the pair's separation unmeasurable, because the number a
 * reader sees is the composited pixel, not the token. 0.7 is not a new value:
 * it is what this component already used whenever a team colour was present.
 *
 * It is `FeedCard`'s opacity, and it stays this module's default so that
 * caller's behaviour is untouched — but it is not universal. `probabilityBarPair`
 * takes the opacity as an argument (#4470), because the decision is about the
 * pixel a reader sees and a card that paints its bar opaque sees a different
 * pixel. Deciding an opaque bar with this value over-rescues: measured over the
 * 326 distinct team colours on events in the 7 days to 2026-09-09, nine of them
 * (25 events — Lakers gold `#fdb927` at 1.73:1 among them) are visible at full
 * opacity and rejected at 0.7, and "rescuing" those replaces a real brand colour
 * with a generic grey for no reader gain.
 */
export const SEGMENT_OPACITY = 0.7;

/**
 * A segment must reach this contrast against the card once composited.
 *
 * 1.5:1 is deliberately low — this is "visible at all", not WCAG text. Chosen
 * by replay, measured on the COMPOSITED pixel rather than the raw hex: at 1.5
 * the rule rescues 60 of 1,445 coloured teams (4.2%); at 3:1 it would override
 * 256 (17.7%), i.e. one team colour in six. The floor should correct
 * white-on-white, not re-brand the league.
 */
export const MIN_SURFACE_CONTRAST = 1.5;

/**
 * Two composited segments this close read as one block.
 *
 * Redmean distance, range 0..~765. Chosen by replay against real pairs: at 78
 * the palette gives `#8a2432` vs `#ac0d1e` (two dark reds) and `#002677` vs
 * `#313169` (two navies), which are genuinely one block in a 1.5px bar. The
 * defaults below sit at 167 composited, comfortably clear of it.
 */
export const MIN_PAIR_DISTANCE = 80;

/**
 * Ordered rescue ladder. The first two are the colours the broken code was
 * reaching for — this fix is, at its core, spelling those two tokens the way
 * they are actually defined. The last two exist only so that a real team colour
 * sitting on top of the first two still has somewhere to go.
 *
 * Proven sufficient rather than argued: over all 644 real team colours AND a
 * 4,096-point synthetic RGB grid, there is no colour for which every ladder
 * member is indistinguishable. The worst real case still leaves 3 of 4. Both
 * facts are assertions in the guard, not comments.
 */
export const AWAY_DEFAULT = "#9CA3AF"; // --text-muted
export const HOME_DEFAULT = "#10B981"; // --accent-brand
export const RESCUE_LADDER = [AWAY_DEFAULT, HOME_DEFAULT, "#4F46E5", "#111827"] as const;

export interface BarPair {
  /** Left segment. Always a real, paintable colour. */
  away: string;
  /** Right segment. Always a real, paintable colour. */
  home: string;
}

/** The opacity each segment is painted at, when the two differ. */
export interface SegmentOpacity {
  away: number;
  home: number;
}

type Rgb = readonly [number, number, number];

/**
 * Parse through `teamColors.hexToRgb` rather than a second parser, so that what
 * counts as a usable team colour cannot drift between this bar and the
 * `ProbabilityBar` / `EventCard` bars that already use that module. A guard
 * asserts the two agree.
 */
function toRgb(hex: string | null | undefined): Rgb | null {
  const rgb = hexToRgb(hex);
  if (!rgb) return null;
  const parts = rgb.split(" ").map(Number);
  if (parts.length !== 3 || parts.some((n) => !Number.isFinite(n))) return null;
  return [parts[0], parts[1], parts[2]] as const;
}

/** The pixel actually painted: the colour at `opacity` over the card. */
function composite(c: Rgb, opacity: number): Rgb {
  const s = toRgb(CARD_SURFACE);
  // CARD_SURFACE is a module constant and always parses; the branch is for the
  // type system, not for a case that can occur.
  const base: Rgb = s ?? [255, 255, 255];
  return [
    opacity * c[0] + (1 - opacity) * base[0],
    opacity * c[1] + (1 - opacity) * base[1],
    opacity * c[2] + (1 - opacity) * base[2],
  ] as const;
}

/** WCAG relative luminance. */
function luminance(c: Rgb): number {
  const f = (v: number) => {
    const x = v / 255;
    return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
}

export function contrastRatio(a: Rgb, b: Rgb): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/**
 * Redmean colour distance — the standard low-cost perceptual approximation.
 * Contrast ratio is the wrong instrument for this half: two mid-luminance hues
 * (a red and a green) have a poor contrast ratio and are trivially
 * distinguishable, so a contrast test would "rescue" pairs that were fine.
 */
export function colorDistance(a: Rgb, b: Rgb): number {
  const rbar = (a[0] + b[0]) / 2;
  const dr = a[0] - b[0];
  const dg = a[1] - b[1];
  const db = a[2] - b[2];
  return Math.sqrt(
    (2 + rbar / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rbar) / 256) * db * db
  );
}

/** Is this colour visible at all once painted on the card at `opacity`? */
function visibleOnCard(c: Rgb, opacity: number): boolean {
  const surface = toRgb(CARD_SURFACE) ?? ([255, 255, 255] as const);
  return contrastRatio(composite(c, opacity), surface) >= MIN_SURFACE_CONTRAST;
}

/**
 * Would these two read as one block?
 *
 * Each side is composited at ITS OWN opacity, because the reader compares the
 * two painted pixels and nothing else. On a bar that dims one half — the shared
 * `ProbabilityBar` paints the favourite at 1 and the underdog at 0.4 (#4470b) —
 * two identical hexes are genuinely distinguishable, and a single-opacity test
 * would "rescue" a pair that was never one block.
 */
function tooClose(a: Rgb, aOpacity: number, b: Rgb, bOpacity: number): boolean {
  return (
    colorDistance(composite(a, aOpacity), composite(b, bOpacity)) <
    MIN_PAIR_DISTANCE
  );
}

/**
 * A team colour is usable only if it parses AND survives the card. An
 * unusable one is treated exactly like an absent one — which is the whole
 * point: "we have a colour for this team" and "the user can see it" are
 * different claims, and only the second one matters here.
 */
function usable(hex: string | null | undefined, opacity: number): Rgb | null {
  const rgb = toRgb(hex);
  if (!rgb) return null;
  return visibleOnCard(rgb, opacity) ? rgb : null;
}

/**
 * First ladder colour that is visible and distinguishable from `other`.
 *
 * `opacity` is the opacity the RESCUED side is painted at; `otherOpacity` the
 * opacity its partner is painted at. On a bar with one dimmed half those two
 * differ, and using one for both would compare a pixel to a pixel that is never
 * on screen.
 */
function rescue(
  other: Rgb | null,
  otherOpacity: number,
  preferred: string,
  opacity: number
): string {
  const candidates = [preferred, ...RESCUE_LADDER];
  for (const hex of candidates) {
    const rgb = toRgb(hex);
    if (!rgb || !visibleOnCard(rgb, opacity)) continue;
    if (other && tooClose(rgb, opacity, other, otherOpacity)) continue;
    return hex;
  }
  // Unreachable over every real and synthetic colour tested; kept so the
  // function is total rather than throwing into a render path.
  return RESCUE_LADDER[RESCUE_LADDER.length - 1];
}

/**
 * Decide both segments of one bar.
 *
 * A real, visible team colour is always kept. Only the side that has nothing
 * usable moves, and it moves to the first ladder colour that the reader can
 * both see and tell apart from its partner. When neither side has a usable
 * colour the pair is the two defaults, which is what the broken code intended
 * all along.
 *
 * When BOTH sides carry usable colours that are too close to each other, the
 * away side is kept and the home side is rescued. That choice is arbitrary but
 * it must be deterministic, or the same fixture renders two ways.
 *
 * `opacity` is the opacity the CALLER paints these segments at, and every
 * threshold is applied to the pixel that produces. It defaults to
 * `SEGMENT_OPACITY` so `FeedCard` is unchanged; `discover/EventCard` paints an
 * opaque bar and passes `1` (#4470). Getting this wrong in either direction is
 * measurable, not theoretical — see the note on `SEGMENT_OPACITY`.
 *
 * It may also be a PAIR, because a bar is allowed to dim one half. The shared
 * `ProbabilityBar` (the /sports, league and search card) paints the favourite
 * at 1 and the underdog at 0.4, and the two are not interchangeable: measured
 * over the 324 distinct team colours on events in the 7 days to 2026-09-09,
 * 8 colours (33 teams, 85 events) fall below the floor at opacity 1 and 36
 * colours (64 teams, 176 events) fall below it at 0.4. Deciding a 0.4 segment
 * at 1 leaves it invisible; deciding a 1 segment at 0.4 re-brands a team that
 * was perfectly visible.
 */
export function probabilityBarPair(
  awayColor?: string | null,
  homeColor?: string | null,
  opacity: number | SegmentOpacity = SEGMENT_OPACITY
): BarPair {
  const { away: awayOpacity, home: homeOpacity } =
    typeof opacity === "number" ? { away: opacity, home: opacity } : opacity;

  const awayRgb = usable(awayColor, awayOpacity);
  const homeRgb = usable(homeColor, homeOpacity);

  if (awayRgb && homeRgb) {
    if (!tooClose(awayRgb, awayOpacity, homeRgb, homeOpacity)) {
      return { away: normalize(awayColor), home: normalize(homeColor) };
    }
    return {
      away: normalize(awayColor),
      home: rescue(awayRgb, awayOpacity, HOME_DEFAULT, homeOpacity),
    };
  }

  if (awayRgb) {
    return {
      away: normalize(awayColor),
      home: rescue(awayRgb, awayOpacity, HOME_DEFAULT, homeOpacity),
    };
  }

  if (homeRgb) {
    return {
      away: rescue(homeRgb, homeOpacity, AWAY_DEFAULT, awayOpacity),
      home: normalize(homeColor),
    };
  }

  // Neither side has a usable colour. The two defaults are the intended answer,
  // but they are not exempt from clause 3 and this is not hypothetical: at 0.7
  // they sit at 1.85:1 and 1.94:1, and at 0.4 — the opacity the shared card
  // dims its underdog to — they are 1.40:1 and 1.46:1, i.e. BELOW the floor this
  // module exists to enforce. Returning them unchecked would ship a bar that
  // fails its own contract on precisely the cards that have no team colours at
  // all, which is most of them. So the defaults walk the same ladder as any
  // other colour. At `SEGMENT_OPACITY` the ladder returns them untouched, so
  // `FeedCard` is bit-identical — a control arm asserts exactly that.
  const away = rescue(null, awayOpacity, AWAY_DEFAULT, awayOpacity);
  return {
    away,
    home: rescue(toRgb(away), awayOpacity, HOME_DEFAULT, homeOpacity),
  };
}

/**
 * Team colours arrive both with and without a leading `#`, and in both letter
 * cases — the palette contains `#002d62` and `#002D62` as separate rows. The
 * value handed to `backgroundColor` has to be a valid CSS colour either way.
 */
function normalize(hex: string | null | undefined): string {
  const raw = (hex ?? "").trim();
  return raw.startsWith("#") ? raw : `#${raw}`;
}
