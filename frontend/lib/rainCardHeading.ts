/**
 * WHAT THE HEADING OVER THE DAILY NYC RAIN CARD IS ALLOWED TO PROMISE.
 *
 * ── THE DEFECT THIS EXISTS TO END (ux/1081, #3230) ───────────────────────────
 *
 * The card was headed `NYC · 7-day rain probability` as a literal, and rendered
 * its tiles into a grid declared `repeat(7, minmax(70px, 1fr))` — also a
 * literal. On production on Sat 2026-09-05 it rendered TWO tiles under that
 * heading, into seven tracks:
 *
 *   - 390px: two tiles left-aligned, about half the card empty beside them.
 *   - 1280px: two ~90px tiles and ~600px of trailing white space, which reads
 *     as content that failed to load rather than as an honest two-day answer.
 *
 * ── THE TWO IS CORRECT. THE SEVEN IS THE LIE ─────────────────────────────────
 *
 * Measured at the venue by series discovery, not from our tables (standing
 * notice 26a): `GET /trade-api/v2/markets?series_ticker=KXRAIN&status=open`
 * returned 44 open markets under exactly two event tickers, `KXRAIN-26SEP05`
 * and `KXRAIN-26SEP06`, 22 city outcomes each. Kalshi lists two days. We are
 * not dropping five, and after #3219 each probability sits under the day it
 * actually prices. The frame was the only untrue part of the card.
 *
 * This is the UX-P210 rule one card over: a heading is a claim about
 * everything underneath it, and "7-day" over two tiles leaves the reader
 * working out which five days we lost. `lib/hubUpcomingHeading.ts` answers the
 * same question for hub rails.
 *
 * ── WHY DERIVED, NOT NEUTRAL ─────────────────────────────────────────────────
 *
 * The neutral form — "NYC · daily rain probability", no number anywhere — is
 * true at every population, and it is what this file returns when there is
 * nothing to count. It is the wrong answer when there IS something to count:
 * the number of days priced is a fact the payload holds, it is the fact a
 * reader of this card wants, and withholding it is only correct when the
 * alternative is false. So the horizon is derived from the rows actually
 * rendered and the heading grows back to "7-day" by itself on the day the
 * venue lists seven.
 *
 * ── WHY THE TRACK COUNT MOVES WITH IT ────────────────────────────────────────
 *
 * A truthful heading over seven tracks holding two tiles still shows the
 * reader five empty columns, which is the same claim made in layout instead of
 * words. The tracks follow the same count, capped per tile so two days cannot
 * balloon into two 370px slabs, and centred when short so the remaining space
 * reads as deliberate rather than truncated.
 *
 * The invariant both halves pin, and the one the guards assert: the card never
 * frames a horizon longer than the tiles it is drawing.
 */

/** Heading used when there is no populated day to count. Carries no horizon. */
export const RAIN_HEADING_NO_COUNT = "NYC · daily rain probability";

/** The card's full-width layout: the most tracks it will ever lay down. */
export const RAIN_MAX_TRACKS = 7;

/** Widest a single day tile may grow when the row is short of full width. */
export const RAIN_TILE_MAX_PX = 150;

/** Gap between tiles, in px. Mirrors the grid's `gap-2` (0.5rem). */
export const RAIN_TILE_GAP_PX = 8;

/**
 * The heading to print over `dayCount` rendered day tiles.
 *
 * @param dayCount how many tiles are actually being drawn — not how many rows
 *   the payload holds, so a cap or a filter between the two cannot leave the
 *   heading describing days nobody can see.
 */
export function rainCardHeading(dayCount: number): string {
  if (!Number.isFinite(dayCount)) return RAIN_HEADING_NO_COUNT;
  const days = Math.floor(dayCount);
  if (days <= 0) return RAIN_HEADING_NO_COUNT;
  return `NYC · ${days}-day rain probability`;
}

export interface RainGridStyle {
  gridTemplateColumns: string;
  /** Unset at full width — the grid fills the card exactly as it always did. */
  maxWidth?: string;
  marginLeft?: string;
  marginRight?: string;
}

/**
 * The grid the day tiles are laid into, for `dayCount` tiles.
 *
 * At `RAIN_MAX_TRACKS` or more this is byte-for-byte the layout that shipped
 * before: seven `minmax(70px, 1fr)` tracks filling the card. Below it, the
 * track count follows the data and the row is capped and centred.
 */
export function rainGridStyle(dayCount: number): RainGridStyle {
  const days = Number.isFinite(dayCount) ? Math.floor(dayCount) : 0;
  const tracks = Math.min(Math.max(days, 1), RAIN_MAX_TRACKS);
  const columns = `repeat(${tracks}, minmax(70px, 1fr))`;

  if (tracks >= RAIN_MAX_TRACKS) return { gridTemplateColumns: columns };

  const widest = tracks * RAIN_TILE_MAX_PX + (tracks - 1) * RAIN_TILE_GAP_PX;
  return {
    gridTemplateColumns: columns,
    maxWidth: `${widest}px`,
    marginLeft: "auto",
    marginRight: "auto",
  };
}
